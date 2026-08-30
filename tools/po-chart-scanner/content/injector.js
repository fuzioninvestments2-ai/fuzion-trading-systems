// ============================================================
// injector.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION (3 FASES + ESPERAR)
// Orquestador principal. Monta el panel PRO (sin interferir
// con v2.0.4) y conecta los 6 botones.
// v4.0 TIEMPO REAL (adios al DESFASE):
//   - MOTOR CONTINUO de 3 fases sobre el cierre de TU orden:
//     1) FOTO DE FONDO silenciosa cada ~2.5s: el archivo de
//        velas siempre esta FRESCO (el calculo no llega tarde).
//     2) AVISO PREVIO 5s ANTES del cierre: "PREPARATE: CALL/PUT"
//        con la vela al ~95% (margen para preparar la entrada).
//     3) SENAL FINAL instantanea +0.8s tras el cierre: la vela
//        ya cerro y el resultado se registra en el historial.
//   - La captura ya NO oculta el panel: se RECORTA la zona de
//     lectura para que el panel quede fuera (cero parpadeo).
//   - El overlay usa colores NEUTROS (cian/amarillo) que el
//     filtro de velas ignora: nunca se oculta, nunca contamina.
// ESCANEAR: Motor 1 canvas -> Motor 2 fotografia la ZONA EXACTA
//   del canvas del grafico con filtro de bandas anti-MACD.
// GRAFICO:  el usuario sombrea el area (modo manual, respaldo).
// v3.4.0:
//   - HISTORIAL UNIFICADO: manual y AUTO alimentan el MISMO
//     historial; una senal contraria cancela la pendiente.
//   - EXPIRACION CONSCIENTE: lee tu Time de PO y evalua el
//     WIN/LOSS cuando TU plazo vence (no en cualquier escaneo).
//   - ANTI-PARPADEO TOTAL: el overlay ya NO se borra al iniciar
//     el escaneo; panel+overlay se ocultan solo ~60ms para la
//     foto y se restauran INMEDIATO al recibirla.
// v3.5.0: cada escaneo ALIMENTA el archivo de velas (historial
//   profundo propio), la senal recibe CONTEXTO MULTI-TIMEFRAME
//   y el panel muestra el BACKTEST REAL de las senales.
// v3.5.1:
//   - AUTO SINCRONIZADO: un ticker de 500ms dispara el escaneo
//     ~3s ANTES de cada cierre de TU tiempo de orden (el "Time"
//     de PO), no en un intervalo fijo ajeno al grafico.
//   - WIN/LOSS con PRECIO REAL del eje (findCurrentPrice);
//     el eje-Y cambia con el zoom y daba el 0% falso.
//   - RESET limpia el APRENDIZAJE (historial + archivo de
//     velas) para borrar los datos contaminados.
// v3.5.2 PERFILADA:
//   - AUTO dispara ~1s DESPUES de cada cierre de tu orden: la
//     vela analizada YA CERRO (misma fuerza que un escaneo
//     manual; la v3.5.1 disparaba 3s antes con la vela al 90%).
//   - PISO DE CALIDAD: si la lectura trae pocas velas (area
//     manual chica o captura sucia) la senal se MUESTRA pero NO
//     se registra en el historial: estadisticas limpias.
//   - Evaluacion dual: precio REAL o escala unificada del
//     archivo; jamas pixeles-Y crudos (eso era el 3% falso).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('injector');

(() => {
  const P = POScannerPRO;
  const CFG = P.CONFIG;
  let autoTicker = null;      // ticker del modo AUTO
  let lastPreSlot = 0;        // ultimo aviso previo ya disparado
  let lastFinSlot = 0;        // ultimo cierre con senal final ya disparada
  let lastBgShot = 0;         // ultima foto silenciosa de fondo (ms)
  const readHist = [];        // ultimas lecturas (piso adaptativo v3.5.4)
  let scanning = false;   // candado: no solapar escaneos

  // Cargar ajustes guardados del usuario
  P.Settings.load();

  // PO es una SPA: esperar a que exista el body y montar el panel.
  const bootTimer = setInterval(() => {
    if (!document.body) return;
    clearInterval(bootTimer);
    init();
  }, 500);

  function init() {
    // v3.5.2: si ya hay OTRO panel PRO montado (por ejemplo la
    // v3.5.1 maestra activa a la vez), esta copia se queda
    // dormida: desactiva la otra version en chrome://extensions
    if (document.getElementById('po-pro-panel')) {
      console.warn('[PO PRO] Ya hay otro panel PRO activo. Desactiva la otra version.');
      return;
    }
    P.Panel.mount({
      scan:     () => runScan(null),              // null = rango automatico
      area:     () => selectArea(),
      auto:     () => toggleAuto(),
      history:  () => P.Panel.showHistory(),
      settings: () => P.Panel.set('status', 'AJUSTES: Fase 3 (umbrales e indicadores por timeframe)'),
      // v3.5.1: RESET limpia el APRENDIZAJE (historial de senales
      // + archivo de velas) y recarga. Borra los datos
      // contaminados por el bug del eje-Y (el 0% con 465L).
      reset:    () => {
        try { P.History.clear(); } catch (e) {}
        try { localStorage.removeItem('poscanner_pro_archive_v1'); } catch (e2) {}
        location.reload();
      }
    });
    // Autodiagnostico: verificar que los 15 modulos cargaron
    const NEED = ['config','canvasReader','indicators','patternDetector','supportResistance',
                  'trendAnalyzer','candleArchive','scoring','confirmators','adaptiveFormulas',
                  'areaSelector','chartOverlay','history','alerts','panel','injector',
                  'trapDetector','orderFlowDetector','crowdBehavior','contrarianScoring'];
    const have = P._mods || [];
    const missing = NEED.filter(n => have.indexOf(n) < 0);
    if (missing.length) {
      P.Panel.set('status', 'FALTAN MODULOS: ' + missing.join(', ') +
        ' (archivo corrupto al pegar: pide el mini-parche de ese archivo)');
    } else {
      P.Panel.set('status', 'PRO v' + CFG.VERSION + ' | Modulos 20/20 OK. Pulsa ESCANEAR.');
    }
    console.log('[PO PRO] Panel montado. Version', CFG.VERSION, '| modulos:', have.length);
  }

  // Resultado final: puntuar, mostrar, comentar en grafico y registrar.
  // UNIFICADO: manual, GRAFICO y AUTO pasan todos por AQUI.
  // v4.0: finish recibe el MODO del escaneo:
  //   'silent' -> foto de fondo: SOLO archiva y alimenta el piso
  //               adaptativo. Nada de UI, historial ni sonido.
  //   'pre'    -> aviso previo (5s antes del cierre): calcula y
  //               muestra TODO (panel, overlay, beep) pero NO
  //               registra en el historial (la vela aun no cierra).
  //   'final'  -> senal instantanea al cierre: pipeline completo.
  //   'manual' -> boton ESCANEAR / GRAFICO: pipeline completo.
  function finish(candles, engineInfo, mode) {
    mode = mode || 'manual';
    scanning = false;
    // v3.5.0: identificar activo+timeframe y ARCHIVAR las velas
    // (historial profundo propio que PO no exporta)
    const assetEl = document.querySelector('#po-pro-panel [data-f="asset"]');
    const asset = assetEl ? assetEl.textContent : '-';
    const tfSec = P.Panel.getTfSec ? P.Panel.getTfSec() : 60;
    let archN = 0;
    try { archN = P.CandleArchive.add(asset, tfSec, candles); }
    catch (e) { console.warn('[PO PRO] archivo:', e.message); }

    // PISO ADAPTATIVO: alimentar con TODA lectura (tambien las
    // silenciosas) para que la mediana refleje el ritmo real.
    readHist.push(candles.length);
    if (readHist.length > 12) readHist.shift();

    // FOTO DE FONDO: ya archivamos la serie fresca. Fin aqui.
    if (mode === 'silent') return;

    // Puntuar CON contexto multi-timeframe (fuente 12).
    // v4.2 SCORE ESTABLE: se puntua SOLO con velas CERRADAS. La
    // vela en formacion cambia en cada foto y hacia saltar el
    // score (50->80->100 sin que el mercado se moviera). Al
    // cerrar, la vela de la senal YA queda incluida: la senal al
    // cierre es identica a la que viste en el aviso previo.
    const cerradas = candles.length > (CFG.SCAN.MIN_CANDLES + 1)
      ? candles.slice(0, -1) : candles;
    const result = P.Scoring.evaluate(cerradas, { asset: asset, tfSec: tfSec });

    // BACKTEST REAL contra las velas archivadas (cache 10 min)
    try {
      const exp0 = P.Panel.expiryInfo ? P.Panel.expiryInfo() : { candles: 1 };
      result.backtest = P.CandleArchive.backtest(asset, tfSec, exp0.candles);
    } catch (e) { /* archivo insuficiente aun */ }

    // EXPIRACION CONSCIENTE DEL TIMEFRAME (v3.4.0):
    // tu Time de PO define el plazo real de la senal
    const exp = P.Panel.expiryInfo ? P.Panel.expiryInfo()
              : { text: '', candles: 1, deadlineMs: 60000 };

    // Mostrar en panel (showResult calcula y fija r.expiryText)
    P.Panel.showResult(result);

    // COMENTARIOS EN EL GRAFICO: redibujo atomico (sin parpadeo)
    try {
      const levels = P.SupportResistance.findLevels(candles);
      P.ChartOverlay.draw(candles, P.CanvasReader.lastStats.conv, levels, result);
    } catch (e) { console.warn('[PO PRO] overlay:', e.message); }

    // BEEP si la senal esta confirmada
    if (result.confirmed) {
      try { P.Alerts.beep(result.dir); } catch (e) { /* sin audio */ }
    }

    // PISO DE CALIDAD ADAPTATIVO (v3.5.4): la mediana de las
    // ultimas 12 lecturas marca el ritmo REAL de tu pantalla
    // (con indicadores de PO activos la zona de velas es mas
    // chica y llegan menos velas: el piso viejo, atado al mejor
    // recuerdo, bloqueaba senales CONFIRMADAS buenas). Solo se
    // rechaza lo claramente anormal para tu ritmo actual.
    // v4.0: el push a readHist ya se hizo arriba (todos los modos).
    const med = readHist.slice().sort((a, b) => a - b)[Math.floor(readHist.length / 2)];
    const floorN = Math.max(CFG.SCAN.WEAK_MIN || 18,
      Math.floor(med * (CFG.SCAN.WEAK_RATIO || 0.55)));
    const weak = candles.length < floorN;

    // HISTORIAL UNIFICADO: evaluar pendientes YA VENCIDOS y
    // registrar la nueva senal con su plazo.
    // v3.5.2 EVALUACION HONESTA: se pasa el PRECIO REAL (o null);
    // si no hay, history.js usa la escala unificada del archivo.
    // JAMAS pixeles-Y crudos: eso producia el 3% falso (3W/114L).
    // v4.0: el AVISO PREVIO evalua el historial vencido pero NO
    // registra la senal (la vela en formacion no es definitiva);
    // solo 'final' y 'manual' escriben en el historial.
    const domPrice = P.Panel.findCurrentPrice ? P.Panel.findCurrentPrice() : null;
    P.History.update(domPrice);
    if (mode !== 'pre' && result.confirmed && !weak) {
      P.History.add({
        asset: asset,
        dir: result.dir,
        score: result.score,
        quality: result.quality,
        refPrice: domPrice,             // precio REAL (o null)
        refReal: !!domPrice,            // true = comparacion directa
        refT: Date.now(),               // para la escala del archivo
        tfSec: tfSec,
        deadline: Date.now() + exp.deadlineMs,  // se evalua al vencer
        expiryText: result.expiryText || '',
        tag: result.contrarian ? 'CONTRARIAN' : 'NORMAL', // v4.3
        obvia: !!result.esObvia                           // v4.3
      });
    }

    // v4.0: prefijo del estado segun la fase del motor continuo
    const fase = mode === 'pre' ? 'PREPARATE: '
               : mode === 'final' ? 'SENAL AL CIERRE: ' : '';
    P.Panel.set('status',
      fase +
      (result.blocked
        ? 'ESPERAR: ' + result.dir + ' BLOQUEADA (' +
          (result.blockReason === 'masa' ? 'masa obvia + trampa' : 'contra estructura') +
          ', votacion ' + result.rawScore + '%)'
        : result.confirmed
        ? (mode === 'pre' ? result.dir + ' probable' :
           'Escenario ' + result.dir + ' confirmado') +
          ' (' + result.score + '/100) expira ' + (result.expiryText || '-')
        : 'Sin confirmacion (' + result.score + '%)') +
      (mode === 'pre' ? ' - la vela cierra en ~5s' : '') +
      ' | Motor: ' + engineInfo +
      (archN ? ' | Archivo: ' + archN + ' velas' : '') +
      (weak ? ' | LECTURA DEBIL (' + candles.length + ' velas): NO registrada' : '') +
      (!domPrice ? ' | precio: archivo' : ''));
  }

  // MODO AUTO v4.0: MOTOR CONTINUO DE 3 FASES (adios al desfase).
  // Un ticker de 250ms sincronizado con el cierre de TU orden:
  //   1) FOTO DE FONDO cada ~2.5s (silenciosa): el archivo de
  //      velas esta siempre FRESCO, el calculo nunca llega tarde.
  //   2) AVISO PREVIO 5s ANTES del cierre: calcula con la vela
  //      al ~95% y avisa "PREPARATE: CALL/PUT probable" + beep.
  //      Te da margen para preparar la entrada sin sorpresas.
  //   3) SENAL FINAL +0.8s tras el cierre: la vela YA cerro, se
  //      confirma o corrige el aviso y se registra al instante.
  // Con orden de 30s tienes ~29s para entrar: CERO desfase.
  // Si cambias tu orden a 1m o 5m, el ritmo se adapta solo.
  function toggleAuto() {
    if (autoTicker) {
      clearInterval(autoTicker);
      autoTicker = null;
      P.Panel.setAuto(false);
      P.Panel.set('status', 'AUTO desactivado. Las lineas quedan fijas.');
      return;
    }
    P.Panel.setAuto(true);
    P.Panel.set('status', 'AUTO v4.3: escaneo continuo + anti-manipulacion. Aviso 5s antes del cierre, senal al cerrar.');
    if (!scanning) runScan(null, { final: true }); // primer escaneo inmediato
    autoTicker = setInterval(() => {
      // Tiempo de orden leido de PO; respaldo: timeframe del grafico
      let ts = (P.Panel.getTradeSec && P.Panel.getTradeSec()) ||
               (P.Panel.getTfSec ? P.Panel.getTfSec() : 60);
      if (!ts || ts < 5) ts = 60;          // piso de seguridad
      const now = Date.now() / 1000;
      const close = Math.ceil(now / ts) * ts;      // proximo cierre
      const lastClose = Math.floor(now / ts) * ts; // cierre mas reciente
      const toClose = close - now;                 // seg. que faltan
      const since = now - lastClose;               // seg. desde el cierre

      // FASE 2 - AVISO PREVIO: ~5s ANTES del cierre
      const preS = CFG.SCAN.PRE_ALERT_S || 5;
      if (toClose <= preS && toClose > 0.5 && close !== lastPreSlot && !scanning) {
        lastPreSlot = close;
        runScan(null, { preAlert: true });
        return;                            // una fase por tick
      }

      // FASE 3 - SENAL FINAL: +0.8s tras el cierre (ventana 3s)
      const finS = CFG.SCAN.FINAL_AFTER_CLOSE_S || 0.8;
      if (since >= finS && since <= 3 && lastClose !== lastFinSlot && !scanning) {
        lastFinSlot = lastClose;
        runScan(null, { final: true });
        return;
      }

      // FASE 1 - FOTO DE FONDO: cada ~2.5s, silenciosa
      // (no cerca del aviso ni del cierre: ahi mandan las fases 2 y 3)
      const bgMs = CFG.SCAN.CONTINUOUS_BG_MS || 2500;
      if (toClose > preS + 1 && since > 3 &&
          Date.now() - lastBgShot >= bgMs && !scanning) {
        lastBgShot = Date.now();
        runScan(null, { silent: true });
      }
    }, 250);
  }

  // MODO ESCANEAR: Motor 1 (canvas) -> si falla, Motor 2 (captura)
  // rect null => Motor 2 fotografia la zona exacta del canvas
  // v4.0: opts { silent, preAlert, final } define la fase del
  // motor continuo. 'silent' no toca el panel (cero parpadeo).
  function runScan(rect, opts) {
    opts = opts || {};
    const mode = opts.silent ? 'silent' : opts.preAlert ? 'pre'
               : opts.final ? 'final' : 'manual';
    if (scanning) return;            // candado anti-solape
    scanning = true;
    const CR = P.CanvasReader;
    // v3.4.0: YA NO borramos el overlay aqui (eso causaba el
    // parpadeo de 60s). v4.0: ademas el overlay usa colores
    // NEUTROS (cian/amarillo) que el filtro ignora, asi que
    // NUNCA se oculta: cero parpadeo total.
    if (mode !== 'silent')
      P.Panel.set('status', 'Motor 1/2: leyendo canvas...');

    let candles = [];
    let err1 = '';
    try {
      candles = CR.readBest(rect || CR.defaultChartRect());
    } catch (e) {
      err1 = e.message;
    }
    const st = CR.lastStats;
    console.log('[PO PRO] Motor canvas:', candles.length, 'velas,', st.colored, 'px en', st.tried, 'canvas.', err1);

    if (candles.length >= CFG.SCAN.MIN_CANDLES) {
      try { finish(candles, 'canvas (' + candles.length + ' velas)', mode); }
      catch (e) { P.Panel.set('status', 'Error en analisis: ' + e.message); }
      return;
    }
    // Motor 1 insuficiente -> Motor 2: fotografiar la ZONA EXACTA
    // del canvas del grafico con filtro de bandas anti-MACD.
    let rect2 = rect, useBands = false;
    if (!rect2) {
      rect2 = CR.chartCanvasRect();  // null si no hay canvas -> full screen
      useBands = true;
    }
    captureFallback(rect2,
      'canvas: ' + candles.length + ' velas / ' + st.colored + ' px en ' + st.tried + ' canvas' +
      (err1 ? ' (' + err1 + ')' : ''), useBands, mode);
  }

  // MOTOR 2: foto de la pestana (la hace el service worker)
  // v4.0 ANTI-PARPADEO DEFINITIVO:
  //   - El OVERLAY ya NO se oculta NUNCA: sus colores neutros
  //     (cian/amarillo) no pasan el filtro de velas lima/rojo.
  //   - El PANEL ya NO se oculta: si esta encima de la zona,
  //     la zona se RECORTA por la izquierda del panel (el borde
  //     en vivo del grafico queda dentro igual). Asi el motor
  //     continuo puede fotografiar cada ~2.5s sin parpadeo.
  //   - Solo en el caso raro de que el panel tape CASI TODA la
  //     zona (ventana muy estrecha) se oculta como antes.
  function captureFallback(rect, prevInfo, useBands, mode) {
    mode = mode || 'manual';
    if (mode !== 'silent')
      P.Panel.set('status', 'Motor 2/2: captura de pantalla' +
        (rect ? (useBands ? ' (zona del grafico)...' : ' (area elegida)...')
             : ' (rango automatico)...'));
    let zone = rect ? { x: rect.x, y: rect.y, w: rect.w, h: rect.h }
                    : { x: 0, y: 0, w: innerWidth, h: innerHeight };
    const pEl = document.getElementById('po-pro-panel');
    let hidePanel = false;
    if (pEl) {
      const pr = pEl.getBoundingClientRect();
      const overlaps = !(pr.right < zone.x || pr.left > zone.x + zone.w ||
                         pr.bottom < zone.y || pr.top > zone.y + zone.h);
      if (overlaps) {
        // El panel es un panel lateral DERECHO: recortar la zona
        // hasta justo antes de su borde izquierdo (margen 6px).
        const cut = pr.left - zone.x - 6;
        if (cut >= zone.w * 0.6) { zone = { x: zone.x, y: zone.y, w: cut, h: zone.h }; }
        else { hidePanel = true; P.Panel.setVisible(false); } // panel gigante: plan B
      }
    }
    const delay = hidePanel ? (CFG.SCAN.CAPTURE_HIDE_MS || 60) : 0;
    setTimeout(() => {
      chrome.runtime.sendMessage({ type: 'PO_PRO_CAPTURE' }, (resp) => {
        // Restaurar YA: la foto ya esta tomada (solo si se oculto)
        if (hidePanel) P.Panel.setVisible(true);
        const lastErr = chrome.runtime.lastError;
        if (lastErr || !resp || !resp.ok) {
          scanning = false;
          if (mode !== 'silent')
            P.Panel.set('status', 'Captura fallo: ' +
              (lastErr ? lastErr.message : (resp && resp.error) ? resp.error : 'sin respuesta'));
          return;
        }
        P.CanvasReader.readFromDataUrl(resp.dataUrl, zone, useBands).then((r2) => {
          console.log('[PO PRO] Motor captura:', r2.candles.length, 'velas,', r2.colored, 'px [', mode, ']');
          if (r2.candles.length >= CFG.SCAN.MIN_CANDLES) {
            try { finish(r2.candles, 'captura' + (rect ? (useBands ? ' zona' : '') : ' auto') +
                        ' (' + r2.candles.length + ' velas)', mode); }
            catch (e) { P.Panel.set('status', 'Error en analisis: ' + e.message); }
          } else {
            scanning = false;
            if (mode !== 'silent')
              P.Panel.set('status', 'Sin velas suficientes. ' + prevInfo +
                ' | captura: ' + r2.candles.length + ' velas / ' + r2.colored +
                ' px. Prueba GRAFICO y sombrea solo las velas.');
          }
        }).catch((e2) => {
          scanning = false;
          if (mode !== 'silent')
            P.Panel.set('status', 'Error leyendo captura: ' + e2.message);
        });
      });
    }, delay);
  }

  // MODO GRAFICO: overlay para sombrear el area de velas
  function selectArea() {
    P.Panel.set('status', 'Selecciona solo el area de velas. Sin indicadores ni botones BUY/SELL.');
    const ov = document.createElement('div');
    ov.id = 'po-pro-overlay';
    const box = document.createElement('div');
    box.id = 'po-pro-selectbox';
    document.body.appendChild(ov);

    let x0, y0;
    ov.onmousedown = e => {
      x0 = e.clientX; y0 = e.clientY;
      ov.appendChild(box);
      box.style.cssText = 'left:' + x0 + 'px;top:' + y0 + 'px;width:0;height:0';
    };
    ov.onmousemove = e => {
      if (x0 === undefined) return;
      box.style.left = Math.min(x0, e.clientX) + 'px';
      box.style.top = Math.min(y0, e.clientY) + 'px';
      box.style.width = Math.abs(e.clientX - x0) + 'px';
      box.style.height = Math.abs(e.clientY - y0) + 'px';
    };
    ov.onmouseup = e => {
      const rect = {
        x: Math.min(x0, e.clientX), y: Math.min(y0, e.clientY),
        w: Math.abs(e.clientX - x0), h: Math.abs(e.clientY - y0)
      };
      ov.remove();
      if (rect.w > 40 && rect.h > 40) runScan(rect);
    };
  }
})();
// [PO-PRO-OK:injector]
