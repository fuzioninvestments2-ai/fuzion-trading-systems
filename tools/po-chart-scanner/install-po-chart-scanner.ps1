# ============================================================
# INSTALADOR - PO Chart Scanner PRO v4.4.0 OPTIMIZACION
# DE SCORING Y FILTRADO (OTC)
#
# USO (3 pasos):
#   1) Copia TODO este texto (Ctrl+A, Ctrl+C)
#   2) Abre PowerShell y pegalo (clic derecho), Enter
#   3) Chrome: chrome://extensions -> Cargar sin empaquetar ->
#      selecciona la carpeta creada en Documentos
#
# NO borra tus otras versiones: se crea una carpeta NUEVA.
#
# GENERADO AUTOMATICAMENTE por scripts/build_po_scanner_installer.py
# No lo edites a mano: edita tools/po-chart-scanner/ y regeneralo.
# ============================================================

$base = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'PO-Chart-Scanner-PRO-v4.4'
Write-Host 'Instalando en:' $base

$files = @{
  'background/service-worker.js' = @'
// ============================================================
// service-worker.js - PO Chart Scanner PRO v3.2.0
// FASE 1: lifecycle minimo + MOTOR 2: captura de pantalla.
// captureVisibleTab fotografia la pestana visible (funciona
// aunque el canvas sea WebGL o este protegido por CORS).
// ============================================================
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('[PO Scanner PRO] Instalado. Abre Pocket Option.');
  } else if (details.reason === 'update') {
    console.log('[PO Scanner PRO] Actualizado a v3.2.0');
  }
});

// MOTOR 2: el panel pide una captura de la pestana activa
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'PO_PRO_CAPTURE') return;
  const done = (resp) => { try { sendResponse(resp); } catch (e) { /* canal cerrado */ } };
  try {
    const winId = sender && sender.tab ? sender.tab.windowId : undefined;
    chrome.tabs.captureVisibleTab(winId, { format: 'png' }, (dataUrl) => {
      const err = chrome.runtime.lastError;
      if (err || !dataUrl) done({ ok: false, error: err ? err.message : 'sin imagen' });
      else done({ ok: true, dataUrl: dataUrl });
    });
  } catch (e) {
    done({ ok: false, error: e.message });
  }
  return true; // respuesta asincrona
});
// [PO-PRO-OK:service-worker]

'@
  'content/injector.js' = @'
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
    // v4.4.2 CADENA DE METODOS PARA EL PRECIO REAL:
    //   1) 'eje'     etiqueta resaltada del eje (lectura directa)
    //   2) 'escala'  calibrar el eje con sus etiquetas fijas y
    //                traducir el pixel de cierre de la ultima vela
    //   3) 'archivo' ultimo recurso: comparar en pixeles del
    //                archivo (history.js). NO es un precio: no se
    //                puede imprimir un numero, y por eso el panel
    //                dice "archivo" en vez de inventar uno.
    let domPrice = P.Panel.findCurrentPrice ? P.Panel.findCurrentPrice() : null;
    let priceSrc = domPrice != null ? 'eje' : 'archivo';
    if (domPrice == null && P.Panel.priceFromCandle) {
      const px = P.Panel.priceFromCandle(candles[candles.length - 1],
                                         P.CanvasReader.lastStats.conv);
      if (px != null) { domPrice = px; priceSrc = 'escala'; }
    }
    P.History.update(domPrice);
    if (mode !== 'pre' && result.confirmed && !weak) {
      P.History.add({
        asset: asset,
        dir: result.dir,
        score: result.score,
        quality: result.quality,
        refPrice: domPrice,             // precio REAL (o null)
        refReal: domPrice != null,      // true = comparacion directa
        refMethod: priceSrc,            // v4.4.2: eje | escala | archivo
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
      ' | precio: ' + (domPrice != null ? priceSrc + ' ' + domPrice : 'archivo'));
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

'@
  'content/panel.css' = @'
/* ============================================================
   panel.css - PRO v3.2.0
   Identidad visual PRO: verde neon (#00ff88), abajo-IZQUIERDA.
   IDs y clases con prefijo pop- : cero conflicto con v2.0.4.
   v3.2.0: rejilla 3x2 (con EJEC y ACIERTO), flash de botones,
   capa SVG de comentarios sobre el grafico.
   ============================================================ */
#po-pro-panel {
  position: fixed; left: 12px; bottom: 12px; width: 300px; z-index: 999999;
  background: #0a1410; border: 1px solid #00ff88; border-radius: 12px;
  color: #d8f5e5; font: 12px/1.4 system-ui, sans-serif; padding: 10px;
  box-shadow: 0 8px 30px rgba(0,255,136,.15);
}
.pop-header { display: flex; justify-content: space-between; color: #00ff88; font-weight: 700; }
.pop-close { cursor: pointer; color: #4b6b58; font-size: 16px; }
.pop-status { color: #7ea892; margin: 6px 0; }
.pop-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.pop-cell { background: #07100b; border: 1px solid #123324; border-radius: 8px; padding: 6px; }
.pop-cell label { color: #4b6b58; font-size: 10px; display: block; }
.pop-signal { display: flex; justify-content: space-between; align-items: center;
  background: #07100b; border: 1px solid #123324; border-radius: 8px;
  padding: 10px; margin: 8px 0 4px; }
.pop-dir { font-size: 26px; font-weight: 800; }
.pop-call { color: #00ff88; } .pop-put { color: #ff5c5c; }
/* v4.1: senal techada por el filtro estructural = AMARILLO alerta */
.pop-warn { color: #ffd23f !important; }
.pop-quality.pop-warn { color: #ffd23f; font-weight: 700; }
.pop-score { font-size: 20px; font-weight: 700; }
.pop-quality { text-align: right; color: #7ea892; font-size: 11px; margin-bottom: 6px; }
.pop-detail { white-space: pre-line; color: #7ea892; min-height: 48px; }
.pop-btns { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-top: 8px; }
.pop-btn { background: #123324; color: #d8f5e5; border: 0; border-radius: 8px;
  padding: 9px 4px; cursor: pointer; font-weight: 600; font-size: 11px;
  transition: filter .15s, transform .1s; }
.pop-btn:hover { filter: brightness(1.25); }
.pop-btn:active { transform: scale(.95); }
.pop-flash { filter: brightness(1.8); transform: scale(.95); }
.pop-green { background: #00c96b; color: #04150c; }
.pop-disclaimer { font-size: 9px; color: #33503f; margin-top: 8px; }
#po-pro-overlay { position: fixed; inset: 0; z-index: 999998;
  cursor: crosshair; background: rgba(0,0,0,.15); }
#po-pro-selectbox { position: fixed; border: 2px dashed #00ff88;
  background: rgba(0,255,136,.10); pointer-events: none; }
/* Capa de comentarios sobre el grafico (flechas, lineas S/R) */
#po-pro-chart-svg { position: fixed; inset: 0; z-index: 999997;
  pointer-events: none; }
/* v4.4: ETIQUETA DE ACCION por rango de score. Es la linea que
   decide por ti: verde brillante = operar, rojo = bloqueada. */
.pop-action { display: block; text-align: center; font-weight: 800;
  font-size: 13px; letter-spacing: .5px; border-radius: 8px;
  padding: 5px 4px; margin: 0 0 6px; border: 1px solid transparent; }
.pop-act-operar   { background: #00ff88; color: #04150c; border-color: #00ff88;
                    box-shadow: 0 0 12px rgba(0,255,136,.55); }
.pop-act-cond     { background: #0f3d28; color: #46e39b; border-color: #46e39b; }
.pop-act-medio    { background: #3a3312; color: #ffd23f; border-color: #ffd23f; }
.pop-act-no       { background: #3d2410; color: #ff9d3f; border-color: #ff9d3f; }
.pop-act-bloqueada{ background: #3d1414; color: #ff5c5c; border-color: #ff5c5c; }
/* v4.4: aviso de senal debil bajo la etiqueta */
.pop-weak { color: #ffd23f; font-size: 10px; text-align: center;
  margin: -2px 0 6px; }
/* v4.2: score de una senal BLOQUEADA (ESPERAR) se muestra tachado */
.pop-score.pop-blocked { text-decoration: line-through; color: #ffd23f; opacity: .8; }
/* [PO-PRO-OK:panel.css] */

'@
  'manifest.json' = @'
{
  "manifest_version": 3,
  "name": "PO Chart Scanner PRO v4.4 OPTIMIZACION DE SCORING Y FILTRADO",
  "version": "4.4.2",
  "description": "v4.4: setup CONTRARIAN PERFECTO (+15 y piso 90 con las 6 condiciones), umbral de confluencia 7/12 (6/12 si es perfecto), etiqueta de accion OPERAR/NO OPERAR por rango de score, sin flecha de entrada bajo 75 y backtest separado contrarian/normal/total. v4.3: CAPA CONTRARIAN ANTI-MANIPULACION para OTC - Trap Index (mechas largas), deteccion de FAKEOUT en S/R, reversal ratio, order flow inferido por rango (proxy de pixeles, sin volumen real), penalizacion por senal OBVIA (masa), bonus CONTRARIAN por fakeout a favor y BLOQUEO por masa obvia con trampa en contra; historial separado contrarian vs normal. Hereda v4.2: bloqueo total de contra-estructura (ESPERAR), regla de los 90, score con velas cerradas, backtest maduro (30+); v4.1: techos estructurales 60/55/45; v4.0: motor continuo de 3 fases. SIN auto-trading.",
  "permissions": [
    "storage",
    "activeTab",
    "scripting"
  ],
  "host_permissions": [
    "<all_urls>"
  ],
  "background": {
    "service_worker": "background/service-worker.js"
  },
  "content_scripts": [
    {
      "matches": [
        "https://pocketoption.com/*",
        "https://app.pocketoption.com/*"
      ],
      "js": [
        "src/config.js",
        "src/canvasReader.js",
        "src/indicators.js",
        "src/patternDetector.js",
        "src/supportResistance.js",
        "src/trendAnalyzer.js",
        "src/candleArchive.js",
        "src/trapDetector.js",
        "src/orderFlowDetector.js",
        "src/crowdBehavior.js",
        "src/contrarianScoring.js",
        "src/scoring.js",
        "src/confirmators.js",
        "src/adaptiveFormulas.js",
        "src/areaSelector.js",
        "src/chartOverlay.js",
        "src/history.js",
        "src/alerts.js",
        "src/panel.js",
        "content/injector.js"
      ],
      "css": [
        "content/panel.css"
      ],
      "run_at": "document_idle"
    }
  ],
  "action": {
    "default_title": "PO Chart Scanner PRO v4.4 OPTIMIZACION DE SCORING Y FILTRADO"
  }
}

'@
  'src/adaptiveFormulas.js' = @'
// ============================================================
// adaptiveFormulas.js - PRO v3.2.0  [STUB - Fase 3]
// Archivo creado y registrado. La logica llega en la Fase 3.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('adaptiveFormulas');
POScannerPRO.AdaptiveFormulas = { ready: false, note: 'Pendiente Fase 3: Formulas adaptativas por timeframe (5s a 1 dia)' };
// [PO-PRO-OK:adaptiveFormulas]

'@
  'src/alerts.js' = @'
// ============================================================
// alerts.js - PRO v3.2.0  [FASE 4 - ACTIVO]
// Alerta sonora con Web Audio API (sin archivos externos):
//   CALL -> dos tonos ascendentes (ding-ding)
//   PUT  -> dos tonos descendentes
// Solo suena tras un clic del usuario (politica de Chrome OK).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('alerts');

POScannerPRO.Alerts = (() => {
  let ctx = null;

  function ac() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function tone(freq, t0, dur, vol) {
    const c = ac(); if (!c) return;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = 'sine';
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, c.currentTime + t0);
    g.gain.exponentialRampToValueAtTime(vol, c.currentTime + t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + t0 + dur);
    o.connect(g); g.connect(c.destination);
    o.start(c.currentTime + t0);
    o.stop(c.currentTime + t0 + dur + 0.05);
  }

  // Beep de senal: CALL ascendente / PUT descendente
  function beep(dir) {
    const CFG = POScannerPRO.CONFIG;
    if (!CFG.ALERTS.SOUND) return;
    const v = CFG.ALERTS.VOLUME * 0.3;
    try {
      if (dir === 'CALL') { tone(660, 0, 0.12, v); tone(880, 0.14, 0.18, v); }
      else                { tone(880, 0, 0.12, v); tone(660, 0.14, 0.18, v); }
    } catch (e) { /* audio no disponible */ }
  }

  return { beep: beep, ready: true };
})();
// [PO-PRO-OK:alerts]

'@
  'src/areaSelector.js' = @'
// ============================================================
// areaSelector.js - PRO v3.2.0  [STUB - Fase 1]
// Archivo creado y registrado. La logica llega en la Fase 1.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('areaSelector');
POScannerPRO.AreaSelector = { ready: false, note: 'Pendiente Fase 1: Seleccion manual de area (logica en injector.js)' };
// [PO-PRO-OK:areaSelector]

'@
  'src/candleArchive.js' = @'
// ============================================================
// candleArchive.js - PRO v4.2.0  [ARCHIVO DE VELAS PROPIO]
// v3.5.6: timestamps a la rejilla de cierre (sin duplicados).
// El "historial profundo" que PO no exporta: cada escaneo
// guarda las velas leidas en localStorage (hasta MAX por
// activo+timeframe). Con los dias se acumula un historial
// REAL del par que operas (incluso OTC, que no existe en
// ninguna fuente externa) y se usa para:
//   1) CONTEXTO MULTI-TIMEFRAME: tendencia de timeframes
//      mayores (M1/M5/M15) archivados -> filtra la senal
//   2) BACKTESTING REAL: prueba la votacion del bot contra
//      las velas archivadas -> "Backtest: 68% en N senales"
// Velas en espacio-Y del reader (igual que TrendAnalyzer).
// v3.5.1: RE-ANCLAJE DE ESCALA. PO re-escala y desplaza el
//   grafico con el zoom/auto-scroll, asi que el eje-Y en
//   pixeles de hoy NO coincide con el de ayer. Al agregar un
//   tramo nuevo se ajusta a la escala del archivo por regresion
//   lineal sobre las velas compartidas (y_viejo = a*y_nuevo+b).
//   Sin esto, el archivo mezclaba escalas y el backtest/contexto
//   salian basura (junto al 0% falso de acierto).
// v3.5.2: closeAt()/lastClose() para evaluar WIN/LOSS en la
//   ESCALA UNIFICADA del archivo, y CONTEXTO MTF SINTETICO:
//   si no hay serie de un TF mayor, se DERIVA agrupando las
//   velas del timeframe actual (S30 x2 = M1, x10 = M5, ...).
// v3.5.3: LIMPIEZA POR CLUSTER. Si un escaneo venia contaminado
//   por los indicadores propios de PO (barras MACD leidas como
//   velas), las velas buenas forman UN cluster vertical denso y
//   la basura cae lejos: se conserva solo el cluster mayor.
//   Se aplica al tramo nuevo (add) y a lo ya guardado (load).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('candleArchive');

POScannerPRO.CandleArchive = (() => {
  const KEY = 'poscanner_pro_archive_v1';
  let db = {};
  load();

  function key(asset, tfSec) { return (asset || '-') + '|' + tfSec; }

  function load() {
    try { db = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { db = {}; }
    if (!db || typeof db !== 'object') db = {};
    // v3.5.3: limpiar series ya guardadas (versiones anteriores
    // pudieron archivar velas falsas de los paneles de indicadores)
    let dirty = false;
    for (const k in db) {
      if (db[k] && db[k].c && db[k].c.length) {
        let arr = cleanCluster(db[k].c);
        // v3.5.6: DEDUP POR REJILLA. Las series de la v3.5.5 y
        // anteriores guardaron la MISMA vela real muchas veces
        // con t ligeramente distintos (el "ahora" crudo de cada
        // escaneo). Se colapsa a un t por cierre de vela.
        const tfSec = parseInt((k.split('|')[1] || '0'), 10);
        if (tfSec > 0 && arr.length) {
          const grid = tfSec * 1000;
          const m = {};
          arr.forEach(c => { m[Math.round(c.t / grid) * grid] = c; });
          arr = Object.keys(m).map(g => m[g]).sort((a, b) => a.t - b.t);
        }
        if (arr.length !== db[k].c.length) { db[k].c = arr; dirty = true; }
      }
    }
    if (dirty) save();
  }

  // LIMPIEZA POR CLUSTER (v3.5.3): conserva el cluster vertical
  // mas grande de velas (por centro Y). La basura de indicadores
  // queda separada por un hueco grande y se descarta.
  function cleanCluster(candles) {
    if (!candles || candles.length < 12) return candles;
    const cy = c => (c.high + c.low) / 2;
    const sorted = candles.slice().sort((a, b) => cy(a) - cy(b));
    const avgH = sorted.reduce((s, c) => s + Math.abs(c.low - c.high), 0) / sorted.length;
    const maxJump = Math.max(60, avgH * 3);
    let best = [sorted[0]], cur = [sorted[0]];
    for (let i = 1; i < sorted.length; i++) {
      if (cy(sorted[i]) - cy(sorted[i - 1]) <= maxJump) {
        cur.push(sorted[i]);
      } else {
        if (cur.length > best.length) best = cur;
        cur = [sorted[i]];
      }
    }
    if (cur.length > best.length) best = cur;
    // Solo recorta si la basura es clara (al menos 5 velas y 8%)
    const dropped = candles.length - best.length;
    if (dropped >= 5 && dropped >= candles.length * 0.08) {
      console.log('[PO PRO] archivo: ' + dropped + ' velas contaminadas descartadas');
      return best.sort((a, b) => (a.t || 0) - (b.t || 0));
    }
    return candles;
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(db)); return; }
    catch (e) { /* cuota llena: recortar a la mitad y reintentar */ }
    const half = Math.floor((POScannerPRO.CONFIG.ARCHIVE.MAX || 3000) / 2);
    for (const k in db) if (db[k] && db[k].c) db[k].c = db[k].c.slice(-half);
    try { localStorage.setItem(KEY, JSON.stringify(db)); } catch (e2) { /* silencioso */ }
  }

  // Agregar velas de un escaneo. Timestamps APROXIMADOS hacia
  // atras desde ahora (vela i = ahora - (n-1-i)*tfSec).
  function add(asset, tfSec, candles) {
    if (!candles || !candles.length || !tfSec) return 0;
    // v3.5.3: nunca archivar basura de indicadores (cluster mayor)
    candles = cleanCluster(candles);
    const k = key(asset, tfSec);
    const now = Date.now();
    const n = candles.length;
    const map = {};
    const prev = db[k] && db[k].c ? db[k].c : [];

    // Tramo nuevo con sus timestamps A LA REJILLA DE CIERRE
    // (v3.5.6): se redondea cada vela al multiplo de tfSec mas
    // cercano. Antes se usaba "ahora" crudo: cada escaneo caia
    // unos segundos distinto y la MISMA vela real se guardaba
    // otra vez con otro t (archivo inflado con duplicados,
    // contexto MTF y backtest contaminados).
    const grid = tfSec * 1000;
    const nc = candles.map((c, i) => ({
      t: Math.round((now - (n - 1 - i) * grid) / grid) * grid,
      open: c.open, high: c.high, low: c.low, close: c.close, dir: c.dir
    }));

    // RE-ANCLAJE (v3.5.1): si el archivo ya tiene velas que se
    // SOLAPAN con el tramo nuevo, medir el cambio de escala/zoom
    // y transformar el tramo nuevo a la escala del archivo.
    // Sin solape suficiente se agrega tal cual (no queda otra).
    if (prev.length >= 8) {
      const tol = tfSec * 1000 / 2;      // tolerancia: media vela
      const pairs = [];
      nc.forEach(c => {
        let best = null, bestDt = tol + 1;
        for (let j = prev.length - 1; j >= 0; j--) {
          const dt = Math.abs(prev[j].t - c.t);
          if (dt < bestDt) { bestDt = dt; best = prev[j]; }
          if (prev[j].t < c.t - tol) break;   // mas viejas: lejos
        }
        if (best) pairs.push({ o: best.close, n: c.close });
      });
      if (pairs.length >= 8) {
        // Minimos cuadrados: y_viejo = a * y_nuevo + b
        let sx = 0, sy = 0, sxx = 0, sxy = 0;
        pairs.forEach(p => { sx += p.n; sy += p.o; sxx += p.n * p.n; sxy += p.n * p.o; });
        const m = pairs.length;
        const den = m * sxx - sx * sx;
        if (Math.abs(den) > 1e-9) {
          const a = (m * sxy - sx * sy) / den;
          const b = (sy - a * sx) / m;
          // factor de escala razonable (descartar ajustes absurdos)
          if (isFinite(a) && Math.abs(a) > 0.01 && Math.abs(a) < 100) {
            nc.forEach(c => {
              c.open  = a * c.open  + b;
              c.high  = a * c.high  + b;
              c.low   = a * c.low   + b;
              c.close = a * c.close + b;
            });
          }
        }
      }
    }

    prev.forEach(c => { map[c.t] = c; });
    nc.forEach(c => { map[c.t] = c; });
    let merged = Object.values(map).sort((a, b) => a.t - b.t);
    const MAX = POScannerPRO.CONFIG.ARCHIVE.MAX || 3000;
    if (merged.length > MAX) merged = merged.slice(-MAX);
    db[k] = { c: merged, updated: now };
    save();
    return merged.length;
  }

  // SINTESIS (v3.5.2): construir velas de un TF MAYOR agrupando
  // las velas archivadas del timeframe actual. Asi el contexto
  // MTF funciona aunque NUNCA cambies de timeframe en PO.
  // Espacio-Y: high = Y menor (techo), low = Y mayor (piso).
  function synth(asset, fromTf, toTf) {
    if (toTf % fromTf !== 0) return null;      // debe ser multiplo
    const e = db[key(asset, fromTf)];
    if (!e || !e.c || e.c.length < 40) return null;
    const span = toTf * 1000;
    const groups = {};
    e.c.forEach(c => {
      const g = Math.floor(c.t / span);
      const cur = groups[g];
      if (!cur) groups[g] = { open: c.open, high: c.high, low: c.low, close: c.close };
      else {
        cur.high = Math.min(cur.high, c.high);   // techo = Y menor
        cur.low  = Math.max(cur.low,  c.low);    // piso  = Y mayor
        cur.close = c.close;
      }
    });
    return Object.keys(groups).sort((a, b) => a - b).map(k => groups[k]);
  }

  // Tendencia de TIMEFRAMES MAYORES (contexto). Prioridad:
  // serie REAL archivada de ese TF; si no existe, SINTETICA
  // derivada del archivo del TF actual (marcada con *).
  // Cada TF mayor vota UP/DOWN (peso 2 si su tendencia es fuerte).
  function higherTrend(asset, tfSec) {
    const ORDER = [5, 15, 30, 60, 180, 300, 900, 1800, 3600, 14400, 86400];
    const NAMES = { 5:'S5', 15:'S15', 30:'S30', 60:'M1', 180:'M3', 300:'M5',
                    900:'M15', 1800:'M30', 3600:'H1', 14400:'H4', 86400:'D1' };
    let score = 0;
    const used = [];
    ORDER.forEach(s => {
      if (s <= tfSec) return;                     // solo TFs MAYORES
      let candles = null, syn = false;
      const e = db[key(asset, s)];
      if (e && e.c && e.c.length >= 40) candles = e.c;
      else { candles = synth(asset, tfSec, s); syn = !!candles; }
      if (!candles || candles.length < 20) return;
      const t = POScannerPRO.TrendAnalyzer.analyze(candles.slice(-60));
      const tag = NAMES[s] + (syn ? '*' : '');
      if (t.trend === 'UP')        { score += t.strength >= 50 ? 2 : 1; used.push(tag + ':ALCISTA'); }
      else if (t.trend === 'DOWN') { score -= t.strength >= 50 ? 2 : 1; used.push(tag + ':BAJISTA'); }
    });
    return {
      score: score,
      dir: score > 0 ? 'UP' : (score < 0 ? 'DOWN' : 'FLAT'),
      used: used
    };
  }

  // --- Soporte a la evaluacion HONESTA del historial (v3.5.2) ---
  // Cierre de la vela archivada mas cercana al instante t
  // (tolerancia: media vela). En la ESCALA UNIFICADA del archivo.
  function closeAt(asset, tfSec, t) {
    const e = db[key(asset, tfSec)];
    if (!e || !e.c || !e.c.length) return null;
    const tol = tfSec * 1000 / 2;
    let best = null, bd = tol + 1;
    e.c.forEach(c => {
      const d = Math.abs(c.t - t);
      if (d < bd) { bd = d; best = c; }
    });
    return best ? best.close : null;
  }

  // Cierre de la ultima vela archivada (= precio actual)
  function lastClose(asset, tfSec) {
    const e = db[key(asset, tfSec)];
    return e && e.c && e.c.length ? e.c[e.c.length - 1].close : null;
  }

  // BACKTESTING REAL (v3.5.0): corre la votacion ligera del bot
  // sobre las velas archivadas y mide acierto real de las
  // senales. Resultado en cache 10 min (es pesado).
  function backtest(asset, tfSec, expiryCandles) {
    const k = key(asset, tfSec);
    const e = db[k];
    const CFG = POScannerPRO.CONFIG.ARCHIVE;
    if (!e || !e.c || e.c.length < (CFG.BT_MIN || 80)) return { n: 0, acc: null };
    if (e.bt && Date.now() - e.bt.at < 600000) return { n: e.bt.n, acc: e.bt.acc };
    const c = e.c;
    const exp = Math.max(1, expiryCandles || 1);
    const W = 60;                        // ventana de analisis por punto
    const step = CFG.BT_STEP || 5;
    const span = Math.min(c.length - exp - 1, CFG.BT_WINDOW || 1200);
    let wins = 0, tot = 0;
    for (let i = Math.max(W, c.length - span); i < c.length - exp - 1; i += step) {
      const dir = POScannerPRO.Scoring.quickEvaluate(c.slice(i - W, i));
      if (!dir) continue;
      // Espacio-Y: precio sube = Y baja
      const win = dir === 'CALL' ? c[i + exp].close < c[i].close
                                 : c[i + exp].close > c[i].close;
      tot++; if (win) wins++;
    }
    const acc = tot ? Math.round(wins / tot * 100) : null;
    e.bt = { n: tot, acc: acc, at: Date.now() };
    save();
    return { n: tot, acc: acc };
  }

  // Tamano del archivo de un activo+TF (para el panel)
  function size(asset, tfSec) {
    const e = db[key(asset, tfSec)];
    return e && e.c ? e.c.length : 0;
  }

  return { add: add, higherTrend: higherTrend, backtest: backtest,
           size: size, closeAt: closeAt, lastClose: lastClose, ready: true };
})();
// [PO-PRO-OK:candleArchive]

'@
  'src/canvasReader.js' = @'
// ============================================================
// canvasReader.js - PRO v4.2.0 (TIEMPO REAL: cadena mas NUEVA)
// Convierte pixeles en velas con CUERPO Y MECHA exactos.
// MOTOR 1: copia del canvas a canvas propio (2D y WebGL).
// MOTOR 2: lectura desde captura de pantalla (readFromDataUrl).
//   - v3.5.5: se REVIERTE el tracking de v3.5.4 (su pista se
//     enganchaba a la linea continua de la Media Movil y leia
//     8-16 velas). Vuelve el tramo mas largo de la v3.5.3, con
//     bandas de margen mas fino y desempate a favor de la franja
//     SUPERIOR (el precio siempre esta encima del MACD).
//   - v3.5.3: tramos verticales, bandas por peso, recorte X.
//   - v3.2.0: si rect es null, escanea TODA la captura y se
//     queda con la banda horizontal con mas velas (rango auto).
//   - Filtro MAX_WIDTH_PX: ignora botones verdes/rojos de la
//     interfaz que parecen velas gigantes.
// lastStats: diagnostico + conv (conversion imagen -> viewport)
// para dibujar los comentarios en el grafico.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('canvasReader');

POScannerPRO.CanvasReader = (() => {
  const CFG = POScannerPRO.CONFIG;

  // Diagnostico de la ultima lectura (lo muestra el panel)
  const lastStats = { colored: 0, tried: 0, conv: null };

  // RGB -> HSV (h: 0-360, s/v: 0-1)
  function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const d = max - min;
    let h = 0;
    if (d !== 0) {
      if (max === r)      h = ((g - b) / d) % 6;
      else if (max === g) h = (b - r) / d + 2;
      else                h = (r - g) / d + 4;
      h *= 60;
      if (h < 0) h += 360;
    }
    const s = max === 0 ? 0 : d / max;
    return [h, s, max];
  }

  // Este pixel es vela verde, vela roja, o nada?
  function classifyPixel(r, g, b) {
    const hsv = rgbToHsv(r, g, b);
    const h = hsv[0], s = hsv[1], v = hsv[2];
    const G = CFG.COLOR.GREEN, R = CFG.COLOR.RED, R2 = CFG.COLOR.RED2;
    if (s >= G.sMin && v >= G.vMin && h >= G.hMin && h <= G.hMax) return 'CALL';
    if (s >= R.sMin && v >= R.vMin &&
        ((h >= R.hMin && h <= R.hMax) || (h >= R2.hMin && h <= R2.hMax))) return 'PUT';
    return null;
  }

  // NUCLEO: ImageData crudo -> array de velas (cuenta pixeles para diagnostico)
  function extractCandles(img, sw, sh) {
    const C = CFG.CANDLE;
    let colored = 0;

    // 1) Mapa de columnas: por cada x, TRAMOS VERTICALES contiguos.
    //    v3.5.5: vuelve el tramo MAS LARGO (la v3.5.4 probo seguir
    //    una "pista" por continuidad pero la semilla caia en la
    //    linea continua de la Media Movil y la seguia a ella:
    //    solo leia 8-16 velas). Una vela real es UN tramo continuo
    //    (cuerpo + mechas conectados); los indicadores de PO (MACD,
    //    RSI...) son tramos aparte en OTRA zona y se ignoran.
    //    El color se vota DENTRO del tramo ganador.
    const RUN_GAP = C.RUN_GAP_PX != null ? C.RUN_GAP_PX : 2;
    const columns = [];
    for (let x = 0; x < sw; x++) {
      // Recoger filas coloreadas con su color
      const pts = [];
      for (let y = 0; y < sh; y++) {
        const i = (y * sw + x) * 4;
        const dir = classifyPixel(img[i], img[i + 1], img[i + 2]);
        if (dir) pts.push({ y: y, dir: dir });
      }
      colored += pts.length;
      if (!pts.length) { columns.push(null); continue; }

      // Dividir en tramos contiguos (hueco > RUN_GAP = otro tramo)
      let best = null, curRun = [pts[0]];
      for (let k = 1; k <= pts.length; k++) {
        if (k < pts.length && pts[k].y - pts[k - 1].y <= RUN_GAP) {
          curRun.push(pts[k]);
        } else {
          if (!best || curRun.length > best.length) best = curRun;
          curRun = pts[k] ? [pts[k]] : [];
        }
      }
      // Votar color SOLO dentro del tramo ganador
      let vCall = 0, vPut = 0;
      best.forEach(p => { if (p.dir === 'CALL') vCall++; else vPut++; });
      const dir = vCall > vPut ? 'CALL' : (vPut > 0 ? 'PUT' : null);
      if (dir && best.length >= C.MIN_HEIGHT_PX) {
        columns.push({ x: x, dir: dir, rows: best.map(p => p.y) });
      } else {
        columns.push(null);
      }
    }
    lastStats.colored = Math.max(lastStats.colored, colored);

    // 2) Agrupar columnas contiguas en velas. v3.5.3: deben ser
    //    del mismo color Y de la MISMA ZONA VERTICAL. Si el tramo
    //    de una columna cae en otra zona (panel MACD/RSI debajo
    //    del grafico), se aparta a OTRO grupo: jamas se mezcla
    //    con la vela de precio (eso deformaba high/low/close).
    const groups = [];
    let cur = null, gap = 0;
    const flush = () => {
      if (cur && cur.cols.length >= C.MIN_WIDTH_PX &&
          cur.cols.length <= C.MAX_WIDTH_PX) {
        // v3.5.5: fragmentos de LINEA FINA (la Media Movil entre
        // vela y vela): 2-3px de alto Y 2-4px de ancho. Una vela
        // real, por pequena que sea, es mas ancha o mas alta.
        const hgt = cur.maxY - cur.minY + 1;
        if (!(hgt <= 3 && cur.cols.length <= 4)) groups.push(cur);
      }
      cur = null;
    };
    for (const col of columns) {
      if (col) {
        const cMin = col.rows[0], cMax = col.rows[col.rows.length - 1];
        if (cur) {
          const curH = Math.max(6, cur.maxY - cur.minY);
          const tol = Math.max(10, curH * 0.6);
          const mismaZona = cMin <= cur.maxY + tol && cMax >= cur.minY - tol;
          if (col.dir !== cur.dir || !mismaZona) flush();
        }
        if (!cur) cur = { dir: col.dir, cols: [], minY: cMin, maxY: cMax };
        cur.cols.push(col);
        if (cMin < cur.minY) cur.minY = cMin;
        if (cMax > cur.maxY) cur.maxY = cMax;
        gap = 0;
      } else if (cur && ++gap > C.MAX_GAP_PX) flush();
    }
    flush();

    // 3) Por cada vela: separar CUERPO de MECHAS por densidad de fila
    const candles = groups.map(g => {
      const width = g.cols.length;
      const allRows = g.cols.flatMap(c => c.rows);
      const minY = Math.min.apply(null, allRows);
      const maxY = Math.max.apply(null, allRows);

      // Densidad por fila: cuantas columnas de la vela tienen color en esa fila
      const need = Math.max(1, Math.ceil(width * C.BODY_DENSITY));
      const rowCount = {};
      g.cols.forEach(c => c.rows.forEach(y => { rowCount[y] = (rowCount[y] || 0) + 1; }));

      let bodyTop = minY, bodyBottom = maxY;
      for (let y = minY; y <= maxY; y++) {
        if ((rowCount[y] || 0) >= need) { bodyTop = y; break; }
      }
      for (let y = maxY; y >= minY; y--) {
        if ((rowCount[y] || 0) >= need) { bodyBottom = y; break; }
      }

      // OHLC en coordenadas Y (invertidas): verde abre abajo/cierra arriba
      const open  = g.dir === 'CALL' ? bodyBottom : bodyTop;
      const close = g.dir === 'CALL' ? bodyTop : bodyBottom;

      return {
        x: (g.cols[0].x + g.cols[g.cols.length - 1].x) / 2,
        width: width,
        dir: g.dir,
        high: minY,          // mecha superior (precio maximo)
        low: maxY,           // mecha inferior (precio minimo)
        open: open,
        close: close,
        bodyTop: bodyTop,
        bodyBottom: bodyBottom,
        bodySize: Math.abs(bodyBottom - bodyTop),
        wickUp: Math.abs(bodyTop - minY),     // mecha superior
        wickDown: Math.abs(maxY - bodyBottom) // mecha inferior
      };
    });
    // 4) RECORTE DE CADENA X (v3.5.3): la serie real de velas es una
    //    cadena densa de X; cualquier vela fantasma aislada muy lejos
    //    (basura de la interfaz a la derecha) se descarta.
    return trimChain(candles);
  }

  // v4.0 TIEMPO REAL: UNIR las cadenas solidas, no elegir una.
  // Antes ganaba la cadena mas larga y, si la lectura se rompia
  // cerca del borde en vivo (vela formandose de 1px, linea de
  // "ahora" de PO), las velas mas recientes se DESCARTABAN: el
  // analisis quedaba anclado ATRAS (el "desfase" del video 8).
  // La ruptura es un fallo de deteccion, no del precio: la serie
  // real continua al otro lado. Reglas:
  //   1) Cadenas SOLIDAS (>=8 velas) se conservan TODAS, unidas
  //      en orden X: historia completa HASTA el borde en vivo.
  //      (La basura aislada de botones/textos nunca junta 8 velas
  //      con paso de vela; y pickBand despues filtra por zona.)
  //   2) Fragmentos DIMINUTOS pegados al final (<=2px de alto: la
  //      vela naciendo o la linea de "ahora") se recortan: no son
  //      una vela util y deformarian el cierre.
  //   3) Si no hay cadena solida, la mas larga (mejor que nada).
  function trimChain(candles) {
    if (!candles || candles.length < 8) return candles;
    const sorted = candles.slice().sort((a, b) => a.x - b.x);
    const gaps = [];
    for (let i = 1; i < sorted.length; i++) gaps.push(sorted[i].x - sorted[i - 1].x);
    gaps.sort((a, b) => a - b);
    const med = gaps[Math.floor(gaps.length / 2)] || 1;
    const maxGap = Math.max(14, med * 2.5);
    const chains = [];
    let curC = [sorted[0]];
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].x - sorted[i - 1].x <= maxGap) {
        curC.push(sorted[i]);
      } else {
        chains.push(curC);
        curC = [sorted[i]];
      }
    }
    chains.push(curC);
    const solidas = chains.filter(c => c.length >= 8);
    if (!solidas.length) {
      chains.sort((a, b) => b.length - a.length);
      return chains[0];
    }
    // Principal = la mas larga. El resto se UNE solo si EXTIENDE la
    // serie sin solaparse en X (una linea paralela tipo Media Movil
    // corre en el MISMO rango X: solape total -> se descarta) y con
    // CONTINUIDAD VERTICAL (el precio no se teletransporta: digitos
    // del contador o barras del MACD estan en otra zona Y -> fuera).
    solidas.sort((a, b) => b.length - a.length);
    const centerY = c => (c.high + c.low) / 2;
    const avgY = arr => arr.reduce((s, c) => s + centerY(c), 0) / arr.length;
    const accepted = [solidas[0]];
    const rest = solidas.slice(1).sort((a, b) => a[0].x - b[0].x);
    rest.forEach(ch => {
      const x0 = ch[0].x, x1 = ch[ch.length - 1].x;
      const spanX = Math.max(1, x1 - x0);
      // solape X con cualquier aceptada
      const solapa = accepted.some(ac => {
        const a0 = ac[0].x, a1 = ac[ac.length - 1].x;
        const ov = Math.min(x1, a1) - Math.max(x0, a0);
        return ov > 0 && ov >= spanX * 0.5;
      });
      if (solapa) return;
      // continuidad vertical contra la aceptada mas cercana en X
      let nearest = accepted[0], bestD = Infinity;
      accepted.forEach(ac => {
        const d = Math.min(Math.abs(x0 - ac[ac.length - 1].x), Math.abs(ac[0].x - x1));
        if (d < bestD) { bestD = d; nearest = ac; }
      });
      const toRight = x0 >= nearest[nearest.length - 1].x;
      const refArr = toRight ? nearest.slice(-10) : nearest.slice(0, 10);
      const myArr = toRight ? ch.slice(0, 10) : ch.slice(-10);
      const hs = nearest.map(c => c.low - c.high).sort((a, b) => a - b);
      const medH = hs[Math.floor(hs.length / 2)] || 1;
      if (Math.abs(avgY(myArr) - avgY(refArr)) > Math.max(40, medH * 3)) return;
      // v4.0b: la cadena candidata debe estar hecha de VELAS, no de
      // linea fina: si su altura mediana es diminuta (la Media Movil
      // roja SI pasa el filtro de color y corre paralela al precio
      // formando "velas" de 3px), no es una cadena de velas: fuera.
      const chH = ch.map(c => c.low - c.high).sort((a, b) => a - b);
      const chMedH = chH[Math.floor(chH.length / 2)] || 1;
      if (chMedH < Math.max(4, medH * 0.4)) return;
      accepted.push(ch);
    });
    // Unir en orden X
    accepted.sort((a, b) => a[0].x - b[0].x);
    let out = [];
    accepted.forEach(c => { out = out.concat(c); });
    // Recortar cola DIMINUTA (vela naciendo / linea de "ahora"):
    // velas finales con alto <= 35% de la mediana (piso 3px)
    const allH = out.map(c => c.low - c.high).sort((a, b) => a - b);
    const mH = allH[Math.floor(allH.length / 2)] || 1;
    const minTail = Math.max(3, Math.floor(mH * 0.35));
    while (out.length > 8 && (out[out.length - 1].low - out[out.length - 1].high) <= minTail) {
      out.pop();
    }
    return out;
  }

  // Canvas principal (el de mayor area visible)
  function findChartCanvas() {
    let best = null, bestArea = 0;
    document.querySelectorAll('canvas').forEach(c => {
      const r = c.getBoundingClientRect();
      const area = r.width * r.height;
      if (area > bestArea && r.width > innerWidth * 0.4) {
        best = c; bestArea = area;
      }
    });
    return best;
  }

  // TODOS los canvas candidatos (PO puede usar varias capas)
  function findChartCanvases() {
    const list = [];
    document.querySelectorAll('canvas').forEach(c => {
      const r = c.getBoundingClientRect();
      if (r.width > innerWidth * 0.4 && r.height > innerHeight * 0.3) list.push(c);
    });
    return list;
  }

  // MOTOR 1: copia el canvas a uno propio y lee ahi.
  // rect viene en coordenadas de VIEWPORT (CSS px).
  function readRegion(canvas, rect) {
    const cr = canvas.getBoundingClientRect();
    const dpr = canvas.width / cr.width;
    let sx = Math.round((rect.x - cr.left) * dpr);
    let sy = Math.round((rect.y - cr.top) * dpr);
    let sw = Math.round(rect.w * dpr);
    let sh = Math.round(rect.h * dpr);
    if (sx < 0) { sw += sx; sx = 0; }
    if (sy < 0) { sh += sy; sy = 0; }
    if (sx + sw > canvas.width)  sw = canvas.width - sx;
    if (sy + sh > canvas.height) sh = canvas.height - sy;
    if (sw <= 4 || sh <= 4) return [];

    const off = document.createElement('canvas');
    off.width = sw; off.height = sh;
    const ctx = off.getContext('2d', { willReadFrequently: true });
    try {
      ctx.drawImage(canvas, sx, sy, sw, sh, 0, 0, sw, sh);
      const img = ctx.getImageData(0, 0, sw, sh);
      return extractCandles(img.data, sw, sh);
    } catch (e) {
      throw new Error('Canvas protegido (CORS): lectura de pixeles bloqueada');
    }
  }

  // Prueba TODOS los canvas candidatos y se queda con el mejor
  function readBest(rect) {
    const cands = findChartCanvases();
    lastStats.tried = cands.length;
    lastStats.colored = 0;
    let best = [], bestConv = null;
    for (const c of cands) {
      let candles = [];
      try { candles = readRegion(c, rect); } catch (e) { continue; }
      if (candles.length > best.length) {
        best = candles;
        const cr = c.getBoundingClientRect();
        const dpr = c.width / cr.width;
        // conversion imagen -> viewport para dibujar comentarios
        bestConv = { left: cr.left + (rect.x - cr.left), top: cr.top + (rect.y - cr.top),
                     sx: dpr, sy: dpr };
        // NOTA: las velas ya vienen en coords del recorte; el origen del
        // recorte en viewport es (rect.x, rect.y):
        bestConv = { left: rect.x, top: rect.y, sx: dpr, sy: dpr };
      }
    }
    lastStats.conv = bestConv;
    return best;
  }

  // v3.2.2 - FILTRO DE BANDAS MEJORADO:
  // PO dibuja indicadores (MACD, RSI) DEBAJO del grafico de precio,
  // con los mismos colores. Reglas:
  //   1) Agrupar velas en bandas verticales solapadas (tolerancia amplia)
  //   2) Descartar bandas con pocas velas o poco ancho horizontal
  //      (textos verdes/rojos de la interfaz forman bandas enanas)
  //   3) Gana la banda MAS ALTA que cumpla (el precio siempre esta arriba)
  // v3.5.3: filtra las velas que NO pertenecen a la franja del
  // precio (paneles de indicadores de PO: MACD/RSI/Estocastico).
  // Se agrupan por cercania vertical y gana la franja con mas
  // PESO (velas x altura media): las velas de precio son altas;
  // una linea fina tipo RSI forma muchas "velas" bajitas y pierde.
  function pickBand(candles, scanW) {
    if (!candles.length) return candles;
    const sorted = candles.slice().sort((a, b) => a.high - b.high);
    const avgH = candles.reduce((s, cd) => s + (cd.low - cd.high), 0) / candles.length;
    // Margen de union estrecho (v3.5.5: tope 18px): si el margen
    // PUENTEA el hueco entre el grafico y el panel MACD, ambos se
    // fusionan en una franja contaminada y la ENTRADA cae abajo.
    const margin = Math.max(10, Math.min(18, avgH * 0.5));
    const bands = [];
    let cur = { top: sorted[0].high, bottom: sorted[0].low, items: [sorted[0]] };
    for (let i = 1; i < sorted.length; i++) {
      const cd = sorted[i];
      if (cd.high <= cur.bottom + margin) {
        cur.items.push(cd);
        cur.bottom = Math.max(cur.bottom, cd.low);
      } else {
        bands.push(cur);
        cur = { top: cd.high, bottom: cd.low, items: [cd] };
      }
    }
    bands.push(cur);
    // Reglas de calidad: minimo 8 velas y al menos 25% del ancho escaneado
    const ok = bands.filter(b => {
      if (b.items.length < 8) return false;
      const xs = b.items.map(cd => cd.x);
      return (Math.max.apply(null, xs) - Math.min.apply(null, xs)) >= scanW * 0.25;
    });
    if (!ok.length) return candles.slice().sort((a, b) => a.x - b.x);
    // PESO = velas x altura media de la franja. v3.5.5: entre las
    // franjas con peso parecido (>= 60% del maximo) gana la MAS
    // ALTA: en PO el precio siempre esta encima de los indicadores.
    ok.forEach(b => {
      b.avgH = b.items.reduce((s, cd) => s + (cd.low - cd.high), 0) / b.items.length;
      b.weight = b.items.length * b.avgH;
    });
    const maxW = Math.max.apply(null, ok.map(b => b.weight));
    const top = ok.filter(b => b.weight >= maxW * 0.6);
    top.sort((a, b) => a.top - b.top);
    const items = top[0].items.sort((a, b) => a.x - b.x);
    // v3.5.5b: quita fragmentos de LINEA pegados a los bordes de la
    // franja (trozo de Media Movil antes de la 1a vela o despues de
    // la ultima). Son PLANOS (<=3px de alto) y mucho mas ANCHOS que
    // una vela normal de esta franja (mediana de anchos como escala).
    const ws = items.map(cd => cd.width || 0).sort((a, b) => a - b);
    const medW = ws[Math.floor(ws.length / 2)] || 0;
    return items.filter(cd =>
      !((cd.low - cd.high) <= 3 && (cd.width || 0) >= medW * 1.8));
  }

  // MOTOR 2: lee velas desde la captura de pantalla (dataUrl PNG).
  // rect=null -> RANGO AUTOMATICO: recorre toda la captura y elige
  // la franja con mas velas (ya no depende de donde este el grafico).
  function readFromDataUrl(dataUrl, rect, useBands) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        try {
          const scX = img.width / innerWidth;
          const scY = img.height / innerHeight;

          const leer = (sx, sy, sw, sh, convLeft, convTop) => {
            const off = document.createElement('canvas');
            off.width = sw; off.height = sh;
            const ctx = off.getContext('2d', { willReadFrequently: true });
            ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
            const data = ctx.getImageData(0, 0, sw, sh);
            const candles = extractCandles(data.data, sw, sh);
            return { candles: candles,
                     conv: { left: convLeft, top: convTop, sx: scX, sy: scY } };
          };

          let out;
          if (!rect) {
            // ---- RANGO AUTOMATICO: toda la captura + filtro de bandas ----
            lastStats.colored = 0;
            out = leer(0, 0, img.width, img.height, 0, 0);
            out.candles = pickBand(out.candles, img.width);
          } else {
            let sx = Math.round(rect.x * scX);
            let sy = Math.round(rect.y * scY);
            let sw = Math.round(rect.w * scX);
            let sh = Math.round(rect.h * scY);
            if (sx < 0) { sw += sx; sx = 0; }
            if (sy < 0) { sh += sy; sy = 0; }
            if (sx + sw > img.width)  sw = img.width - sx;
            if (sy + sh > img.height) sh = img.height - sy;
            if (sw <= 4 || sh <= 4) return resolve({ candles: [], colored: 0 });
            lastStats.colored = 0;
            out = leer(sx, sy, sw, sh, sx / scX, sy / scY);
            // v3.2.2: si el rect viene del canvas del grafico, tambien
            // filtramos bandas (ese canvas incluye los paneles MACD/RSI)
            if (useBands) out.candles = pickBand(out.candles, sw);
          }
          lastStats.conv = out.conv;
          resolve({ candles: out.candles, colored: lastStats.colored });
        } catch (e) { reject(e); }
      };
      img.onerror = () => reject(new Error('no se pudo decodificar la captura'));
      img.src = dataUrl;
    });
  }

  // v3.2.2: rectangulo EXACTO del canvas del grafico (coordenadas viewport).
  // Aunque no podamos leer sus pixeles (WebGL), si sabemos DONDE esta:
  // el Motor 2 fotografia justo esa zona en vez de toda la pantalla.
  function chartCanvasRect() {
    const c = findChartCanvas();
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return {
      x: Math.max(0, r.left + r.width * 0.01),
      y: Math.max(0, r.top + r.height * 0.02),
      w: r.width * 0.96,
      h: r.height * 0.94
    };
  }

  // Rectangulo por defecto: area del grafico (sin ejes) o viewport
  function defaultChartRect() {
    const c = findChartCanvas();
    if (c) {
      const r = c.getBoundingClientRect();
      return {
        x: r.left + r.width * 0.02,
        y: r.top + r.height * 0.05,
        w: r.width * 0.90,
        h: r.height * 0.85
      };
    }
    return {
      x: innerWidth * 0.04,
      y: innerHeight * 0.10,
      w: innerWidth * 0.78,
      h: innerHeight * 0.75
    };
  }

  return {
    findChartCanvas: findChartCanvas,
    findChartCanvases: findChartCanvases,
    chartCanvasRect: chartCanvasRect,
    readRegion: readRegion,
    readBest: readBest,
    readFromDataUrl: readFromDataUrl,
    defaultChartRect: defaultChartRect,
    classifyPixel: classifyPixel,
    extractCandles: extractCandles,
    lastStats: lastStats
  };
})();
// [PO-PRO-OK:canvasReader]

'@
  'src/chartOverlay.js' = @'
// ============================================================
// chartOverlay.js - PRO v4.1.0  [COMENTARIOS EN GRAFICO]
// Dibuja SOBRE el grafico de PO (SVG flotante, no molesta clics):
//   - Lineas de SOPORTE (cian) y RESISTENCIA (amarilla) con toques
//   - LINEA DE ENTRADA: nivel del cierre actual con la senal y
//     la EXPIRACION sugerida (ej: "ENTRADA CALL 72% | 1m")
//   - Flecha CALL/PUT con score junto a la ultima vela
//   - Comentario: patrones + tendencia con amplitud + REVERSION
// v4.0: COLORES NEUTROS (cian/amarillo/blanco). Antes eran
//   verde/rojo: el bot SE LEIA A SI MISMO en la foto de pantalla
//   y habia que ocultar las lineas en cada escaneo (parpadeo).
//   Con neutros la lectura continua es posible y las lineas
//   quedan SIEMPRE visibles.
// v3.5.3: las lineas S/R se LIMITAN al rango vertical visible de
// las velas leidas (un nivel lejano del archivo ya no puede caer
// dibujado sobre los paneles de indicadores de PO).
// v3.4.0: ANTI-PARPADEO - redibujo ATOMICO (no se borra antes
// de tiempo) y setVisible() para ocultarse durante la foto.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('chartOverlay');

POScannerPRO.ChartOverlay = (() => {
  const SVGNS = 'http://www.w3.org/2000/svg';
  let svg = null, timer = null;

  function ensure() {
    if (svg && document.body.contains(svg)) return svg;
    svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('id', 'po-pro-chart-svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    document.body.appendChild(svg);
    return svg;
  }

  function el(name, attrs) {
    const n = document.createElementNS(SVGNS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  function clear() {
    if (svg) svg.remove();
    svg = null;
    if (timer) { clearTimeout(timer); timer = null; }
  }

  // Ocultar/mostrar sin destruir (el Motor 2 lo usa en la foto)
  function setVisible(v) {
    if (svg) svg.style.visibility = v ? 'visible' : 'hidden';
  }

  // candles: coords de imagen; conv: {left,top,sx,sy} imagen->viewport
  // srLevels: niveles de SupportResistance.findLevels
  // result: salida de Scoring.evaluate (+ expiryText opcional)
  function draw(candles, conv, srLevels, result) {
    const CFG = POScannerPRO.CONFIG;
    if (!CFG.OVERLAY.ENABLED || !candles || !candles.length || !conv) return;
    clear();   // atomico: borra y redibuja en el mismo instante
    const s = ensure();
    const X = x => conv.left + x / conv.sx;   // imagen -> viewport X
    const Y = y => conv.top  + y / conv.sy;   // imagen -> viewport Y
    const x0 = X(candles[0].x);
    const x1 = X(candles[candles.length - 1].x);
    const last = candles[candles.length - 1];
    const isCall = result.dir === 'CALL';
    // v4.0: CIAN para entrada/soportes, AMARILLO para resistencias.
    // Ninguno pasa el filtro de velas (lima/rojo): cero auto-lectura.
    const color = '#22d3ee';        // cian (entrada, ambas dirs)
    const COL_S = '#22d3ee';        // cian = soporte
    const COL_R = '#ffd23f';        // amarillo = resistencia

    // --- 1) Lineas de SOPORTE / RESISTENCIA (max 4, mas tocadas) ---
    // v3.5.4: solo niveles DENTRO del rango vertical visible de las
    // velas (+10% de margen). Mas margen filtraba soportes sobre
    // el panel del MACD (se veia en la v3.5.3).
    let yTop = Infinity, yBot = -Infinity;
    candles.forEach(c => {
      if (c.high < yTop) yTop = c.high;
      if (c.low > yBot) yBot = c.low;
    });
    const padY = (yBot - yTop) * 0.10 + 10;
    (srLevels || []).slice(0, 4).forEach(l => {
      if (l.y < yTop - padY || l.y > yBot + padY) return;  // fuera de zona
      const y = Y(l.y);
      const lc = l.type === 'S' ? COL_S : COL_R;
      s.appendChild(el('line', {
        x1: x0, y1: y, x2: x1 + 60, y2: y,
        stroke: lc, 'stroke-width': 2, 'stroke-dasharray': '8 5', opacity: 0.9
      }));
      const t = el('text', {
        x: x0 + 4, y: y - 5, fill: lc, 'font-size': 12, 'font-weight': 'bold',
        stroke: '#04150c', 'stroke-width': 0.4
      });
      t.textContent = (l.type === 'S' ? 'SOPORTE' : 'RESISTENCIA') + ' x' + l.touches;
      s.appendChild(t);
    });

    // --- 2) LINEA DE ENTRADA + 3) FLECHA ---
    // v4.2: si la senal esta BLOQUEADA (contra estructura) NO se
    // dibuja entrada ni flecha: solo el aviso ESPERAR en amarillo.
    // v4.4: lo mismo si el score no llega a FILTER.ENTRY_MIN.
    const cx = X(last.x);
    // v4.4: la flecha de entrada solo se dibuja si el score llega
    // a FILTER.ENTRY_MIN. Una senal debil ya no invita a entrar
    // desde el grafico: se anota en amarillo y se queda ahi.
    const F = CFG.FILTER || {};
    const entryMin = F.ENTRY_MIN != null ? F.ENTRY_MIN : 75;
    const sinEntrada = result.blocked || result.score < entryMin;
    if (sinEntrada) {
      const tb = el('text', {
        x: cx - 12, y: Y(last.high) - 36, fill: '#ffd23f',
        'font-size': 13, 'font-weight': 'bold', 'text-anchor': 'end',
        stroke: '#04150c', 'stroke-width': 0.4
      });
      tb.textContent = !result.blocked
        ? 'SIN ENTRADA: ' + result.dir + ' ' + result.score + '% (minimo ' +
          entryMin + ') - senal debil, esperar mejor setup'
        : result.blockReason === 'masa'
        ? 'ESPERAR: ' + result.dir + ' BLOQUEADO - masa obvia + trampa (' +
          result.rawScore + '% bloqueada)'
        : result.blockReason === 'confluencia'
        ? 'ESPERAR: ' + result.dir + ' BLOQUEADO - confluencia insuficiente (' +
          (result.detail ? result.detail.confluencia : '-') + ')'
        : 'ESPERAR: ' + result.dir + ' contra estructura (' +
          result.rawScore + '% bloqueada)';
      s.appendChild(tb);
    } else {
      // v3.5.5: LIMITADA a la zona visible de las velas (red de
      // seguridad: si una lectura rara cuela la ultima vela en la
      // zona del MACD, la linea se dibuja en el borde del precio,
      // nunca sobre los paneles de indicadores).
      const ycRaw = last.close;
      const ycClamped = Math.max(yTop - padY, Math.min(yBot + padY, ycRaw));
      const yc = Y(ycClamped);
      s.appendChild(el('line', {
        x1: x1 - 30, y1: yc, x2: x1 + 90, y2: yc,
        stroke: color, 'stroke-width': 2.5, opacity: 0.95
      }));
      const te = el('text', {
        x: x1 + 8, y: yc - 6, fill: color, 'font-size': 12, 'font-weight': 'bold',
        stroke: '#04150c', 'stroke-width': 0.4
      });
      te.textContent = 'ENTRADA ' + result.dir + ' ' + result.score + '%' +
        (result.perfecto ? ' [PERFECTO]' : result.contrarian ? ' [CONTRARIAN]' : '') +
        (result.expiryText ? ' | ' + result.expiryText : '');
      s.appendChild(te);

      // --- 3) Flecha de senal sobre la ultima vela ---
      const baseY = isCall ? Y(last.low) + 26 : Y(last.high) - 26;
      const tipY  = isCall ? baseY - 16 : baseY + 16;
      s.appendChild(el('polygon', {
        points: cx + ',' + tipY + ' ' + (cx - 8) + ',' + baseY + ' ' + (cx + 8) + ',' + baseY,
        fill: color, stroke: '#04150c', 'stroke-width': 1
      }));
    }

    // --- 4) Comentario: patrones + tendencia + REVERSION + S/R ---
    const d = result.detail || {};
    const notas = [];
    if (d.reversion) notas.push('REVERSION ' + d.reversion);
    if (d.patterns && d.patterns.length) notas.push('Patron: ' + d.patterns.join(', '));
    if (d.trend && d.trend !== 'FLAT') {
      notas.push('Tendencia: ' + (d.trend === 'UP' ? 'ALCISTA' : 'BAJISTA') +
                 ' (amplitud ' + (d.trendStrength || 0) + '%)');
    }
    if (d.srNear && d.srNear !== '-') notas.push('Cerca de ' + d.srNear);
    if (notas.length) {
      const nt = el('text', {
        x: cx - 12, y: (isCall ? Y(last.high) - 36 : Y(last.low) + 46),
        fill: '#ffd76a', 'font-size': 12, 'font-weight': 'bold', 'text-anchor': 'end',
        stroke: '#04150c', 'stroke-width': 0.4
      });
      nt.textContent = notas.join(' | ');
      s.appendChild(nt);
    }

    // --- Persistencia: solo autolimpiar si TTL_MS > 0 ---
    if (CFG.OVERLAY.TTL_MS > 0) timer = setTimeout(clear, CFG.OVERLAY.TTL_MS);
  }

  return { draw: draw, clear: clear, setVisible: setVisible, ready: true };
})();
// [PO-PRO-OK:chartOverlay]

'@
  'src/config.js' = @'
// ============================================================
// config.js - PO Chart Scanner PRO v4.3 CONTRARIAN ANTI-MANIPULACION
// Configuracion avanzada + persistencia en localStorage.
// NAMESPACE PROPIO: window.POScannerPRO (no choca con v2.0.4)
// v3.5.2 PERFILADA: evaluacion WIN/LOSS honesta, AUTO tras el
//   cierre, piso de calidad, anti-cuenta-regresiva, MTF sintetico.
// v3.5.3 PRECISION: tramos verticales (inmune a indicadores PO).
// v3.5.5 RECTIFICADA: lector de tramo mas largo + bandas.
// v3.5.6 COLOR REAL: verde LIMA de las velas PO + archivo sin
//   duplicados.
// v4.0 TIEMPO REAL (fin del DESFASE, verificado en video 8):
//   - MOTOR CONTINUO: foto silenciosa cada ~2.5s. La serie de
//     velas y TODOS los indicadores quedan PRE-CALCULADOS.
//   - AVISO PREVIO 5s ANTES del cierre ("PREPARATE CALL/PUT")
//     y SENAL INSTANTANEA al cerrar (+0.8s): entras con los
//     30s COMPLETOS de tu orden (antes la senal salia 3-10s
//     tarde y la entrada quedaba desfasada).
//   - CADENA NUEVA: si la lectura se rompe cerca del borde en
//     vivo, gana el tramo que llega a la ULTIMA vela (antes
//     ganaba el tramo mas largo y el analisis se anclaba atras).
//   - OVERLAY NEUTRO (cian/amarillo): las lineas del bot ya no
//     contaminan la foto (no hay que ocultarlas = sin parpadeo
//     y lectura continua posible).
// v4.1 FILTRO ESTRUCTURAL (videos 10-12: el bot daba CALL 97%
//   con el precio cayendo): la votacion mide impulso local; la
//   nueva capa STRUCT techa la senal que va contra tendencia
//   fuerte / S-R / MTF (60/55/45), con excepcion de ruptura
//   confirmada. Panel amarillo de advertencia.
// v4.2 BLOQUEO INTELIGENTE (video P1 del usuario):
//   - BLOQUEO TOTAL: la senal techada ya NO se muestra como
//     entrada. Panel = ESPERAR, overlay sin flecha, historial
//     no la registra. Antes se mostraba CALL 55 y el usuario
//     la podia tomar igual.
//   - REGLA DE LOS 90: un 90+ exige confluencia 5+ Y un aliado
//     estructural (tendencia/S-R/patron/MTF a favor). Si falta,
//     se queda en 89 (buena, no impecable).
//   - SCORE ESTABLE: se puntua SOLO con velas CERRADAS; la vela
//     en formacion hacia saltar el score en cada foto.
//   - BACKTEST MADURO: el % se muestra solo con 30+ senales de
//     muestra (BT_MIN_SHOW); antes decia "100% en 4 senales".
// v4.3 CONTRARIAN ANTI-MANIPULACION (doctorado OTC del usuario):
//   - TRAP INDEX: % de velas con mechas largas (barrido de stops).
//   - FAKEOUT en S/R: mecha pincha el nivel y cierra dentro =
//     ruptura falsa. A favor = bonus CONTRARIAN; en contra =
//     castigo (y con masa obvia = BLOQUEO total).
//   - MASA OBVIA: senal con confluencia 6+ en nivel claro = la
//     que todos ven (y el broker tambien): penalizada.
//   - ORDER FLOW inferido por RANGO de vela (proxy honesto: el
//     bot lee pixeles, NO hay volumen real en la pantalla).
//   - Historial etiquetado CONTRARIAN/NORMAL + obvia (crowd
//     loss rate real con muestra).
// v4.3.1 FIX (videos del usuario): los avisos contrarian ya NO
//   se mezclan en warning (una senal CONTRARIAN buena salia
//   etiquetada "CONTRA-ESTRUCTURA - Riesgo Alto"); y las
//   senales ya bloqueadas no reciben castigos dobles.
// v4.4.0 OPTIMIZACION DE SCORING Y FILTRADO:
//   - SETUP CONTRARIAN PERFECTO: si se cumplen las 6 condiciones
//     del doctorado (nivel x3+, fakeout, contrarian, confluencia
//     8/12, backtest contrarian >65% con muestra, trap <70%) el
//     score recibe +15 y un piso de 90. El panel dice que
//     condicion falta cuando no llega.
//   - UMBRAL DE CONFLUENCIA: menos de 7/12 fuentes = BLOQUEADA
//     (6/12 si el setup contrarian es perfecto).
//   - ETIQUETA DE ACCION por rango de score: OPERAR / OPERAR SI
//     CONTRARIAN / RIESGO MEDIO / NO OPERAR / BLOQUEADO. Debajo
//     de ENTRY_MIN el grafico NO dibuja flecha de entrada.
//   - BACKTEST SEPARADO: contrarian / normal / total.
//   OJO: subir el score de un setup no lo hace mas acertado.
//   Lo que cambia el resultado es operar menos y mejor: mide
//   el backtest CONTRARIAN antes de dar por buena la mejora.
// v4.4.1 PRECIO REAL: findCurrentPrice() se reescribe. En vivo
//   devolvia null (el panel decia "precio: archivo") y todo el
//   WIN/LOSS se juzgaba en pixeles del archivo, con EMPATE para
//   cualquier movimiento < 0.5 px: de ahi los empates de mas.
//   Ahora acepta el digito animado en un span hijo, el fondo
//   pintado en el padre, la coma decimal y toda la mitad
//   derecha de la pantalla; y elige la etiqueta MAS A LA
//   DERECHA en vez de la ultima del DOM. Diagnostico desde la
//   consola: POScannerPRO.Panel.diagPrice()
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('config');

POScannerPRO.CONFIG = {
  VERSION: '4.4.2',

  // --- Deteccion de color de velas (HSV, robusto a temas) ---
  // v3.5.6: verde LIMA real de las velas PO (medido en video:
  // cuerpo solido h~105-120; la Media Movil lima es h~85-95
  // y QUEDA FUERA a proposito).
  COLOR: {
    GREEN: { hMin: 100, hMax: 175, sMin: 0.40, vMin: 0.30 },  // lima PO
    RED:   { hMin: 335, hMax: 360, sMin: 0.50, vMin: 0.40 },  // rojo PO
    RED2:  { hMin: 0,   hMax: 15,  sMin: 0.50, vMin: 0.40 }
  },

  // --- Geometria de velas ---
  CANDLE: {
    MIN_WIDTH_PX: 2,
    MAX_WIDTH_PX: 30,   // una vela real nunca supera ~30px; mas ancho = boton/banner
    MIN_HEIGHT_PX: 2,
    MAX_GAP_PX: 2,
    RUN_GAP_PX: 2,      // hueco max dentro de un tramo vertical
    BODY_DENSITY: 0.6   // % de columnas ocupadas para considerar "cuerpo" (vs mecha)
  },

  // --- Duracion en segundos de cada timeframe de PO ---
  TF_SECONDS: { S5:5, S15:15, S30:30, M1:60, M3:180, M5:300,
                M15:900, M30:1800, H1:3600, H4:14400, D1:86400 },

  // --- Umbrales de senal (ajustables por el usuario) ---
  SCAN: {
    MIN_CANDLES: 15,      // cantidad minima de velas para analizar
    SCORE_MIN_SIGNAL: 65, // por debajo -> NO CONFIRMADO
    SCORE_HIGH: 85,       // por encima -> Calidad HIGH
    AUTO_INTERVAL_MS: 60000, // (legado v3.5.1; v3.5.2 usa cierre+retraso)
    CAPTURE_HIDE_MS: 60,  // anti-parpadeo: pausa minima antes de la foto
    AUTO_AFTER_CLOSE_S: 1,   // (legado v3.5.2-3.5.6)
    AUTO_WINDOW_S: 8,        // (legado v3.5.2-3.5.6)
    // --- v4.0 TIEMPO REAL ---
    PRE_ALERT_S: 5,          // aviso "PREPARATE" 5s ANTES del cierre
    FINAL_AFTER_CLOSE_S: 0.8,// senal FINAL instantanea al cerrar
    CONTINUOUS_BG_MS: 2500,  // foto silenciosa de fondo (serie fresca)
    WEAK_MIN: 18,            // v3.5.4: piso absoluto de velas para registrar
    WEAK_RATIO: 0.55,        // y al menos el 55% de la MEDIANA de las
                             // ultimas 12 lecturas (piso adaptativo v3.5.4)
    SCORE_IMPECCABLE: 90     // v4.2: 90+ solo con alineacion total
  },

  // --- Historial (v3.5.2: evaluacion honesta) ---
  HISTORY: {
    GRACE_MS: 300000    // si no hay precio confiable en 5 min -> SIN DATO
  },

  // --- v4.1 FILTRO ESTRUCTURAL (techos de seguridad) ---
  // La votacion mide IMPULSO local; estos techos castigan la
  // senal que va CONTRA la estructura del mercado. Bajalos si
  // quieres un bot aun mas conservador, subelos para mas riesgo.
  STRUCT: {
    CAP_COUNTER_TREND: 60,   // contra tendencia fuerte (>=50%)
    CAP_COUNTER_SR: 60,      // CALL bajo resistencia / PUT sobre soporte
    CAP_COUNTER_SR_STRONG: 55, // nivel con 3+ toques (mas respetado)
    CAP_COUNTER_MTF: 55,     // contra la tendencia de TFs mayores
    CAP_ALL: 45,             // las tres estructuras en contra a la vez
    BREAKOUT_CANDLES: 3      // cierres mas alla del nivel = ruptura
  },

  // --- v4.3 CONTRARIAN ANTI-MANIPULACION ---
  // Umbrales de la capa anti-trampas. Todo se calcula de la
  // GEOMETRIA de las velas (pixeles): no hay volumen real ni
  // % de traders, asi que se usan proxies honestos.
  CONTRARIAN: {
    ENABLED: true,
    TRAP_WINDOW: 10,       // velas para el Trap Index
    TRAP_WICK_RATIO: 1.0,  // mecha larga = mechas >= cuerpo*1.0
    TRAP_BLOCK: 70,        // Trap Index >= 70% = alta manipulacion
    TRAP_PENALTY: 15,      // castigo por trampa / trap alto
    FAKEOUT_BONUS: 10,     // bonus contrarian (fakeout a favor)
    OBVIO_CONFLUENCIA: 6,  // confluencia >= 6 = senal que todos ven
    OBVIO_PENALTY: 12,     // castigo por senal obvia (masa)
    MASA_BLOCK: true,      // bloquear masa obvia + trampa en contra
    FLOW_PENALTY: 8        // order flow inferido en contra
  },

  // --- v4.4 FILTRADO AUTOMATICO POR SCORE ---
  // Rangos de la etiqueta de accion que pinta el panel. Cambia
  // los numeros si quieres ser mas o menos exigente.
  FILTER: {
    OPERAR: 90,              // 90-100: OPERAR (verde brillante)
    OPERAR_CONTRARIAN: 85,   // 85-89: OPERAR SI CONTRARIAN (verde)
    RIESGO_MEDIO: 75,        // 75-84: RIESGO MEDIO (amarillo)
    NO_OPERAR: 60,           // 60-74: NO OPERAR (naranja); <60 rojo
    ENTRY_MIN: 75,           // debajo: el grafico NO dibuja entrada
    WEAK_WARN: 85,           // debajo: aviso "senal debil"
    MIN_CONFLUENCIA: 6,      // <6/12 fuentes = BLOQUEADA (v4.4.2: era 7,
                             // dejaba fuera senales validas de 6/12)
    MIN_CONFLUENCIA_PERFECTO: 5  // excepcion para contrarian perfecto
  },

  // --- v4.4 SETUP CONTRARIAN PERFECTO (regla del doctorado) ---
  // Las 6 condiciones deben cumplirse TODAS. La del backtest usa
  // el acierto real de TUS senales CONTRARIAN pasadas (history):
  // no existe un backtest por patron, y inventarlo seria mentir.
  // Pon REQUIRE_BACKTEST en false si prefieres no exigirla
  // mientras acumulas muestra.
  PERFECT: {
    ENABLED: true,
    SR_TOUCHES: 3,           // nivel del fakeout con 3+ toques
    CONFLUENCIA: 8,          // 8/12 fuentes de voto
    TRAP_MAX: 70,            // trap index por debajo de 70%
    BONUS: 15,               // puntos extra si se cumple todo
    MIN_SCORE: 90,           // y piso de 90
    REQUIRE_BACKTEST: true,  // exigir la condicion del backtest
    BACKTEST_MIN_N: 5,       // v4.4.2: muestra minima (era 10)
    BACKTEST_MIN_ACC: 55     // v4.4.2: acierto minimo % (era 65)
  },

  // --- Indicadores activos (toggles) ---
  INDICATORS: {
    RSI: true, STOCH: true, MOMENTUM: true,
    MACD: true,       // v3.4.0: MACD completo (linea/senal/histograma)
    EMA_CROSS: true,  // v3.4.0: cruce EMA 9 / SMA 10
    REVERSAL: true    // v3.4.0: detector de reversion fuerte
  },

  // --- Parametros de los nuevos indicadores ---
  STOCH: { K: 14, SLOWING: 3, D: 3 },  // Estocastico 14,3,3 (como en PO)
  CROSS: { EMA_FAST: 9, SMA_SLOW: 10 },// cruce EMA 9 / SMA 10

  // --- Archivo de velas (historial profundo propio) ---
  ARCHIVE: {
    MAX: 3000,        // velas max por activo+timeframe
    BT_WINDOW: 1200,  // backtesting: cuantas velas hacia atras
    BT_STEP: 5,       // backtesting: paso entre puntos de prueba
    BT_MIN: 80,       // minimo de velas archivadas para backtest
    BT_MIN_SHOW: 30   // v4.2: no mostrar % de backtest hasta tener
                      // 30 senales de muestra (4-5 no dicen nada)
  },

  // --- Modulos de analisis avanzado ---
  MODULES: { PATTERNS: true, SR: true, TREND: true },

  // --- Alertas ---
  ALERTS: { SOUND: true, VOLUME: 0.5 },

  // --- Comentarios sobre el grafico ---
  // TTL_MS 0 = las lineas NO se borran solas; se renuevan con cada
  // escaneo de forma ATOMICA (sin parpadeo)
  OVERLAY: { ENABLED: true, TTL_MS: 0 },

  // --- Auto-trading: SIEMPRE desactivado ---
  AUTOTRADE: { ENABLED: false }
};

// --- Trampa global de errores: muestra cualquier fallo en el panel ---
window.addEventListener('error', function(e) {
  var el = document.querySelector('#po-pro-panel [data-f="status"]');
  if (el && e && e.message) {
    var f = (e.filename || '').split('/').pop();
    el.textContent = 'ERROR: ' + e.message + ' (' + f + ':' + e.lineno + ')';
  }
});

// --- Persistencia: guardar/cargar ajustes del usuario ---
POScannerPRO.Settings = {
  KEY: 'poscanner_pro_settings_v3',
  load() {
    try {
      const raw = localStorage.getItem(this.KEY);
      if (raw) Object.assign(POScannerPRO.CONFIG.SCAN, JSON.parse(raw).SCAN || {});
    } catch (e) { /* localStorage no disponible: usar defaults */ }
  },
  save() {
    try {
      localStorage.setItem(this.KEY, JSON.stringify({ SCAN: POScannerPRO.CONFIG.SCAN }));
    } catch (e) { /* silencioso */ }
  }
};
// [PO-PRO-OK:config]

'@
  'src/confirmators.js' = @'
// ============================================================
// confirmators.js - PRO v3.2.0  [STUB - Fase 3]
// Archivo creado y registrado. La logica llega en la Fase 3.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('confirmators');
POScannerPRO.Confirmators = { ready: false, note: 'Pendiente Fase 3: Sistema de confirmacion Nivel 1/2/3' };
// [PO-PRO-OK:confirmators]

'@
  'src/contrarianScoring.js' = @'
// ============================================================
// contrarianScoring.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Capa de score ANTI-MANIPULACION (orquesta los otros 3
// modulos). Adaptacion del "calcularScoreAvanzado" del curso
// a la votacion real del bot: en vez de reconstruir el score
// desde 50, AJUSTA el score que ya calculo scoring.js:
//   PENALIZACIONES:
//   - Trap Index alto (>= TRAP_BLOCK): -TRAP_PENALTY
//     (mercado muy barrido, el broker esta activo).
//   - Fakeout EN CONTRA de la senal: -TRAP_PENALTY y aviso
//     (ej: senal CALL pero hubo fakeout alcista en resistencia).
//   - Senal OBVIA (masa): -OBVIO_PENALTY (lo que todos ven es
//     lo que el broker prepara para revertir).
//   - Order flow en contra: -FLOW_PENALTY.
//   BONUS:
//   - Fakeout A FAVOR de la senal: +FAKEOUT_BONUS y etiqueta
//     CONTRARIAN (ej: fakeout bajista en soporte + senal CALL =
//     operar contra la ruptura falsa, como el CASO 2 del examen).
//   BLOQUEO:
//   - MASA OBVIA + fakeout en contra = trampa de masa probable:
//     se bloquea igual que una contra-estructura (ESPERAR).
// NUNCA inventa datos: todo sale de la geometria de velas.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('contrarianScoring');

POScannerPRO.ContrarianScoring = (() => {
  const CFG = POScannerPRO.CONFIG;

  function adjust(o) {
    const C = CFG.CONTRARIAN || {};
    const P = POScannerPRO;
    const TRAP_BLOCK = C.TRAP_BLOCK != null ? C.TRAP_BLOCK : 70;
    const TRAP_PEN   = C.TRAP_PENALTY != null ? C.TRAP_PENALTY : 15;
    const OBVIO_PEN  = C.OBVIO_PENALTY != null ? C.OBVIO_PENALTY : 12;
    const FLOW_PEN   = C.FLOW_PENALTY != null ? C.FLOW_PENALTY : 8;
    const FK_BONUS   = C.FAKEOUT_BONUS != null ? C.FAKEOUT_BONUS : 10;

    // Sub-analisis (con guardas: si un modulo falta, no rompe nada)
    const trap = P.TrapDetector ? P.TrapDetector.analyze(o.candles, o.sr)
               : { trapIndex: 0, fakeout: null, reversalRatio: null };
    const flow = P.OrderFlowDetector ? P.OrderFlowDetector.analyze(o.candles)
               : { interpretacion: 'EQUILIBRIO', actividad: '-', actividadPct: 0 };
    const crowd = P.CrowdBehavior ? P.CrowdBehavior.analizar(
                    o.candles, o.dir, o.agree, o.sr, o.trend, o.patterns)
               : { esObvia: false, extendido: false, razon: '-' };

    let score = o.score;
    let contrarian = false;
    let bloqueoMasa = false;
    const lines = [];
    const yaBloqueada = !!o.blocked;   // v4.3.1: senal muerta, no tocar

    // 1) TRAP INDEX alto: mercado barrido, castigo general.
    // v4.3.1: si la senal YA esta bloqueada por estructura, no
    // se aplica ningun castigo ni bonus (solo se reportan las
    // metricas). Castigar una senal muerta es ruido doble.
    if (!yaBloqueada && trap.trapIndex >= TRAP_BLOCK) {
      score -= TRAP_PEN;
      lines.push('Trap Index ' + trap.trapIndex + '% (ALTA manipulacion): -' +
                 TRAP_PEN + ' pts');
    }

    // 2) FAKEOUT: trampa de nivel en la ultima vela cerrada
    if (trap.fakeout && !yaBloqueada) {
      if (trap.fakeout.dir === o.dir) {
        // La trampa va A FAVOR: el broker barrio y el precio
        // volvio = oportunidad contrarian (CASO 2 del examen)
        score += FK_BONUS;
        contrarian = true;
        lines.push('SENAL CONTRARIAN: ' + trap.fakeout.tipo +
                   ' a favor (operar contra la ruptura falsa): +' + FK_BONUS);
      } else {
        // La trampa va EN CONTRA: tu senal cayo en la trampa
        score -= TRAP_PEN;
        lines.push('TRAMPA EN CONTRA: ' + trap.fakeout.tipo +
                   ' contra tu ' + o.dir + ': -' + TRAP_PEN + ' pts');
        // 3) MASA OBVIA + trampa en contra = bloqueo total
        if (crowd.esObvia && C.MASA_BLOCK !== false) {
          bloqueoMasa = true;
          lines.push('BLOQUEADO: MASA OBVIA (' + crowd.razon +
                     ') con trampa del broker en contra');
        }
      }
    } else if (crowd.esObvia && !yaBloqueada) {
      // 4) Senal obvia sin trampa clara: castigo moderado
      score -= OBVIO_PEN;
      lines.push('Senal OBVIA (' + crowd.razon + '): la masa ya entro, -' +
                 OBVIO_PEN + ' pts');
    }

    // 5) ORDER FLOW en contra de la direccion
    if (flow.interpretacion === 'MAYORIA VENDEDORA' && o.dir === 'CALL') {
      score -= FLOW_PEN;
      lines.push('Order flow en contra (mayoria vendedora): -' + FLOW_PEN);
    } else if (flow.interpretacion === 'MAYORIA COMPRADORA' && o.dir === 'PUT') {
      score -= FLOW_PEN;
      lines.push('Order flow en contra (mayoria compradora): -' + FLOW_PEN);
    }

    // ========================================================
    // v4.4 SETUP CONTRARIAN PERFECTO (regla del doctorado).
    // Las 6 condiciones deben cumplirse TODAS. Si se cumplen,
    // +BONUS puntos y piso MIN_SCORE (90). Si no, se reporta
    // QUE condicion falta para que sea auditable en el panel.
    // La condicion del backtest usa el acierto real de TUS
    // senales CONTRARIAN pasadas: no existe backtest por patron.
    // ========================================================
    const PF = CFG.PERFECT || {};
    let perfecto = false;
    const faltan = [];
    if (PF.ENABLED !== false && !yaBloqueada) {
      const nivel = trap.fakeout ? trap.fakeout.level : null;
      const bt = perfBacktest(PF);
      const cond = [
        ['nivel S/R x' + (PF.SR_TOUCHES || 3) + '+',
          !!(nivel && nivel.touches >= (PF.SR_TOUCHES || 3))],
        ['fakeout detectado', !!trap.fakeout],
        ['senal contrarian (contra la masa)', contrarian],
        ['confluencia ' + (PF.CONFLUENCIA || 8) + '/12',
          o.agree >= (PF.CONFLUENCIA || 8)],
        ['backtest contrarian >' + (PF.BACKTEST_MIN_ACC || 65) + '%' + bt.nota,
          bt.ok],
        ['trap index <' + (PF.TRAP_MAX || 70) + '%',
          trap.trapIndex < (PF.TRAP_MAX || 70)]
      ];
      cond.forEach(c => { if (!c[1]) faltan.push(c[0]); });
      if (!faltan.length) {
        perfecto = true;
        score = Math.max(score + (PF.BONUS != null ? PF.BONUS : 15),
                         PF.MIN_SCORE != null ? PF.MIN_SCORE : 90);
        lines.push('SETUP CONTRARIAN PERFECTO: las 6 condiciones se cumplen, ' +
                   '+' + (PF.BONUS != null ? PF.BONUS : 15) + ' y piso ' +
                   (PF.MIN_SCORE != null ? PF.MIN_SCORE : 90));
      } else if (contrarian) {
        // Solo se explica cuando ya hay algo contrarian en juego:
        // en una senal normal esta lista seria ruido constante.
        lines.push('Para PERFECTO (90+) falta: ' + faltan.join(', '));
      }
    }

    score = Math.max(0, Math.min(97, score));
    return {
      score: score,
      perfecto: perfecto,
      faltanPerfecto: faltan,
      contrarian: contrarian,
      bloqueoMasa: bloqueoMasa,
      trapIndex: trap.trapIndex,
      reversalRatio: trap.reversalRatio,
      fakeout: trap.fakeout ? trap.fakeout.tipo : null,
      actividad: flow.actividad,
      esObvia: crowd.esObvia,
      lines: lines
    };
  }

  // Condicion de backtest del setup contrarian. Usa el acierto
  // REAL de las senales CONTRARIAN ya vencidas de este bot.
  // Sin muestra suficiente la condicion NO se da por cumplida
  // (afirmar un 65% con 2 senales seria inventar); pon
  // PERFECT.REQUIRE_BACKTEST en false para no exigirla.
  function perfBacktest(PF) {
    if (PF.REQUIRE_BACKTEST === false) return { ok: true, nota: ' (no exigido)' };
    const minN = PF.BACKTEST_MIN_N != null ? PF.BACKTEST_MIN_N : 10;
    const minAcc = PF.BACKTEST_MIN_ACC != null ? PF.BACKTEST_MIN_ACC : 65;
    try {
      const H = POScannerPRO.History;
      const t = H && H.byTag ? H.byTag('CONTRARIAN') : { n: 0, acc: null };
      if (t.n < minN) {
        return { ok: false, nota: ' (muestra ' + t.n + '/' + minN + ')' };
      }
      return { ok: t.acc > minAcc, nota: ' (' + t.acc + '% en ' + t.n + ')' };
    } catch (e) { return { ok: false, nota: ' (sin historial)' }; }
  }

  return { adjust: adjust };
})();
// [PO-PRO-OK:contrarianScoring]

'@
  'src/crowdBehavior.js' = @'
// ============================================================
// crowdBehavior.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Deteccion de "MASA" (crowd behavior). ADAPTACION HONESTA:
// el bot NO puede leer el % real de traders de PO desde los
// pixeles de las velas, asi que la masa se INFIERE asi:
//   - SENAL OBVIA = la que "todos ven": confluencia muy alta
//     (6+ fuentes de voto) en un nivel claro (S/R con 2+
//     toques) o con patron fuerte. Si es obvia para el bot,
//     es obvia para la masa... y para el broker.
//   - MOVIMIENTO EXTENDIDO: el precio ya recorrio mucho en la
//     direccion de la senal (la masa entra tarde, por FOMO).
//   - CROWD LOSS RATE: se calcula de verdad con el HISTORIAL
//     del propio bot: % de senales OBVIAS archivadas que
//     perdieron. >60% = ir contra la masa tiene ventaja aqui.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('crowdBehavior');

POScannerPRO.CrowdBehavior = (() => {
  const CFG = POScannerPRO.CONFIG;

  // Movimiento neto reciente en "cuerpos" (cuanto recorrio ya)
  function extension(candles) {
    const last = candles.slice(-12);
    if (last.length < 3) return 0;
    const avgBody = candles.slice(-20).reduce((a, c) =>
      a + Math.abs(c.close - c.open), 0) / Math.min(20, candles.length) || 1;
    const neto = last[0].close - last[last.length - 1].close; // Y invertida:
    return neto / avgBody; // >0 = subio (Y baja), en unidades de cuerpo
  }

  // La senal es OBVIA (la ve todo el mundo)?
  // dir = direccion de la senal del bot; agree = confluencia (0-12)
  function analizar(candles, dir, agree, sr, trend, patterns) {
    const C = CFG.CONTRARIAN || {};
    const MIN_CONF = C.OBVIO_CONFLUENCIA || 6;
    const nivelClaro = !!(sr && sr.near && sr.near.touches >= 2);
    const patronFuerte = (patterns || []).some(p =>
      dir === 'CALL' ? p.bias > 0 : p.bias < 0);
    const ext = extension(candles);
    // La masa entra tarde: movimiento ya extendido (3+ cuerpos)
    // en la direccion de la senal.
    const extendido = (dir === 'CALL' && ext >= 3) || (dir === 'PUT' && ext <= -3);
    const esObvia = agree >= MIN_CONF && (nivelClaro || patronFuerte);
    const razones = [];
    if (agree >= MIN_CONF) razones.push('confluencia ' + agree + '/12');
    if (nivelClaro) razones.push('nivel claro x' + sr.near.touches);
    if (patronFuerte) razones.push('patron a favor');
    if (extendido) razones.push('movimiento ya extendido');
    return {
      esObvia: esObvia,
      extendido: extendido,
      direccionMasa: esObvia ? dir : null,  // la masa sigue lo obvio
      razon: razones.join(' + ') || 'senal no masiva'
    };
  }

  // CROWD LOSS RATE real: % de senales OBVIAS pasadas que perdieron
  // (usa el historial del propio bot; necesita muestra 10+)
  function crowdLossRate() {
    try {
      const H = POScannerPRO.History;
      if (!H || !H.lastItems) return { rate: null, n: 0 };
      const items = H.lastItems(100).filter(i =>
        i.obvia && (i.result === 'WIN' || i.result === 'LOSS'));
      const losses = items.filter(i => i.result === 'LOSS').length;
      if (items.length < 10) return { rate: null, n: items.length };
      return { rate: Math.round(losses / items.length * 100), n: items.length };
    } catch (e) { return { rate: null, n: 0 }; }
  }

  return { analizar: analizar, crowdLossRate: crowdLossRate,
           extension: extension };
})();
// [PO-PRO-OK:crowdBehavior]

'@
  'src/history.js' = @'
// ============================================================
// history.js - PRO v4.3.0 CONTRARIAN  [FASE 4 - ACTIVO]
// Historial REAL de senales con estadisticas de acierto:
//   - Senal confirmada se guarda con precio de referencia Y
//     PLAZO (deadline = tu tiempo de expiracion de PO)
//   - WIN/LOSS solo se evalua cuando el plazo YA vencio
//   - UNIFICADO (manual + AUTO): una senal contraria cancela
//     la pendiente (no se contradicen)
// v3.5.2 - EVALUACION HONESTA (adios al 3% falso):
//   La v3.5.1 caia al respaldo de pixeles-Y cuando no leia el
//   precio del eje; como PO mantiene el precio actual siempre
//   en la misma zona vertical de pantalla, el "precio" apenas
//   cambiaba entre escaneos -> la comparacion estricta marcaba
//   LOSS casi siempre (3W/114L). Ahora:
//   1) Si hay precio REAL (DOM) en ambos lados: comparacion
//      directa; si no se movio -> EMPATE (PO devuelve la apuesta)
//   2) Si no hay precio real: comparar en la ESCALA UNIFICADA
//      del archivo de velas (mismo activo+TF, re-anclada):
//      cierre de la vela del momento de la senal vs cierre
//      de la vela actual. Y baja = precio sube.
//   3) Si ninguna fuente es confiable: la senal espera; pasado
//      el tiempo de gracia se marca SIN DATO (no cuenta).
//   JAMAS se evalua con pixeles-Y crudos de pantalla.
// v4.4: backtests() devuelve el acierto REAL separado en tres
//   categorias (contrarian / normal / total): el promedio unico
//   escondia que las NORMAL arrastran a las CONTRARIAN.
// v4.3: cada senal se etiqueta tag='CONTRARIAN'|'NORMAL' y con
//   obvia=true/false (senal de masa) -> estadisticas separadas
//   (byTag) y crowd loss rate real (crowdBehavior).
// Persistencia: localStorage (sobrevive a F5 y a reinicios).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('history');

POScannerPRO.History = (() => {
  const KEY = 'poscanner_pro_history_v3';
  const MAX_ITEMS = 100; // rotacion: conserva las ultimas 100 senales
  let items = [];
  load();

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      items = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(items)) items = [];
      // v4.4.2: las senales guardadas ANTES de que el precio real
      // funcionara se juzgaron comparando pixeles del archivo, con
      // EMPATE para cualquier movimiento menor de medio pixel. Esa
      // medicion no es recuperable (PO no da el precio pasado), asi
      // que se marcan 'legacy' y quedan FUERA de las estadisticas
      // nuevas en vez de contaminarlas.
      let migradas = 0;
      items.forEach(i => {
        if (!i.refMethod) { i.refMethod = 'legacy'; migradas++; }
      });
      if (migradas) {
        console.log('[PO PRO] historial: ' + migradas + ' senales antiguas ' +
          'marcadas legacy (medidas en pixeles, no cuentan en el backtest)');
        save();
      }
    } catch (e) { items = []; }
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(items.slice(-MAX_ITEMS))); }
    catch (e) { /* silencioso */ }
  }

  // Registrar una senal confirmada (manual o AUTO: mismo camino)
  function add(signal) {
    // UNIFICACION: cancelar pendientes CONTRARIAS del mismo activo
    let cancelled = false;
    items.forEach(it => {
      if (it.result === 'PENDING' && it.dir !== signal.dir &&
          it.asset === (signal.asset || '-')) {
        it.result = 'CANCELLED';
        cancelled = true;
      }
    });
    // No duplicar: si la ultima senal es igual y esta pendiente, ignorar
    const last = items[items.length - 1];
    if (!cancelled && last && last.result === 'PENDING' &&
        last.dir === signal.dir && last.asset === (signal.asset || '-')) return;
    items.push({
      time: new Date().toLocaleTimeString(),
      asset: signal.asset || '-',
      dir: signal.dir,               // CALL o PUT
      score: signal.score,
      quality: signal.quality,
      refPrice: signal.refPrice,     // precio REAL (o null si no se leyo)
      refReal: !!signal.refReal,     // v3.5.2: true = refPrice es real
      refT: signal.refT || Date.now(), // momento de la senal (ms)
      tfSec: signal.tfSec || 0,      // timeframe del grafico
      deadline: signal.deadline || 0,// plazo de expiracion (ms)
      expiryText: signal.expiryText || '',
      tag: signal.tag || 'NORMAL',   // v4.3: CONTRARIAN o NORMAL
      refMethod: signal.refMethod || 'archivo', // v4.4.2: como se midio
      obvia: !!signal.obvia,         // v4.3: senal de masa (obvia)
      result: 'PENDING'
    });
    save();
  }

  // Decidir WIN/LOSS/EMPATE/SIN DATO de una senal vencida.
  // Devuelve null si aun no hay datos confiables (sigue PENDING).
  function judge(it, realPrice, now) {
    // 1) PRECIO REAL en ambos extremos: comparacion directa
    if (it.refReal && realPrice != null && typeof it.refPrice === 'number') {
      const d = realPrice - it.refPrice;
      const eps = Math.abs(it.refPrice) * 1e-9;
      if (Math.abs(d) <= eps) return 'EMPATE';
      if (it.dir === 'CALL') return d > 0 ? 'WIN' : 'LOSS';
      return d < 0 ? 'WIN' : 'LOSS';
    }
    // 2) ESCALA UNIFICADA del archivo de velas (espacio-Y):
    //    cierre de la vela de la senal vs cierre de la vela actual
    try {
      const A = POScannerPRO.CandleArchive;
      if (A && it.refT && it.tfSec) {
        const refC = A.closeAt(it.asset, it.tfSec, it.refT);
        const curC = A.lastClose(it.asset, it.tfSec);
        if (refC != null && curC != null) {
          const dy = curC - refC;          // Y: bajar = precio SUBE
          if (Math.abs(dy) < 0.5) return 'EMPATE';   // no se movio
          if (it.dir === 'CALL') return dy < 0 ? 'WIN' : 'LOSS';
          return dy > 0 ? 'WIN' : 'LOSS';
        }
      }
    } catch (e) { /* archivo no disponible */ }
    // 3) Sin datos confiables: esperar hasta agotar la gracia
    const GRACE = (POScannerPRO.CONFIG.HISTORY &&
                   POScannerPRO.CONFIG.HISTORY.GRACE_MS) || 300000;
    if (it.deadline && now - it.deadline > GRACE) return 'SIN DATO';
    return null;
  }

  // Evaluar pendientes YA VENCIDOS. realPrice = precio real del
  // eje (o null si no se pudo leer en este escaneo).
  function update(realPrice) {
    const now = Date.now();
    let changed = false;
    items.forEach(it => {
      if (it.result !== 'PENDING') return;
      if (it.deadline && now < it.deadline) return; // aun no expira
      const r = judge(it, realPrice, now);
      if (r) { it.result = r; changed = true; }
    });
    if (changed) save();
    return changed;
  }

  function stats() {
    const wins   = items.filter(i => i.result === 'WIN').length;
    const losses = items.filter(i => i.result === 'LOSS').length;
    const ties   = items.filter(i => i.result === 'EMPATE').length;
    const pend   = items.filter(i => i.result === 'PENDING').length;
    const canc   = items.filter(i => i.result === 'CANCELLED').length;
    const done = wins + losses;
    return {
      total: wins + losses + pend, wins: wins, losses: losses,
      ties: ties, pending: pend, cancelled: canc,
      acc: done ? Math.round(wins / done * 100) : 0
    };
  }

  // Acierto historico FILTRADO por calidad (HIGH/MEDIUM/LOW)
  // v4.4.2: 'legacy' = medida con el metodo viejo, no cuenta
  function vale(i) { return i.refMethod !== 'legacy'; }

  function byQuality(q) {
    const its = items.filter(i => vale(i) && i.quality === q &&
      (i.result === 'WIN' || i.result === 'LOSS'));
    const w = its.filter(i => i.result === 'WIN').length;
    return { n: its.length, acc: its.length ? Math.round(w / its.length * 100) : null };
  }

  // v4.3: acierto FILTRADO por tipo (CONTRARIAN vs NORMAL)
  function byTag(tag) {
    const its = items.filter(i => vale(i) && (i.tag || 'NORMAL') === tag &&
      (i.result === 'WIN' || i.result === 'LOSS'));
    const w = its.filter(i => i.result === 'WIN').length;
    return { n: its.length, acc: its.length ? Math.round(w / its.length * 100) : null };
  }

  // v4.4: BACKTEST SEPARADO en tres categorias. "Backtest" aqui
  // significa el acierto REAL de las senales que este bot emitio
  // y que ya vencieron; no es una simulacion sobre el archivo de
  // velas (eso lo hace CandleArchive.backtest). Separarlos importa
  // porque el promedio total lo arrastran las senales NORMAL.
  function backtests() {
    const c = byTag('CONTRARIAN');
    const n = byTag('NORMAL');
    const cerrada = i => i.result === 'WIN' || i.result === 'LOSS';
    const done = items.filter(i => vale(i) && cerrada(i));
    const w = done.filter(i => i.result === 'WIN').length;
    const old = items.filter(i => !vale(i) && cerrada(i));
    const ow = old.filter(i => i.result === 'WIN').length;
    return {
      contrarian: c,
      normal: n,
      total: { n: done.length,
               acc: done.length ? Math.round(w / done.length * 100) : null },
      // Aparte y solo informativo: no se puede recuperar el precio
      // real de aquellos momentos, asi que no se recalcula.
      legacy: { n: old.length,
                acc: old.length ? Math.round(ow / old.length * 100) : null,
                empates: items.filter(i => !vale(i) && i.result === 'EMPATE').length }
    };
  }

  function clear() { items = []; save(); }

  function lastItems(n) { return items.slice(-(n || 8)).reverse(); }

  return { add: add, update: update, stats: stats, byQuality: byQuality,
           byTag: byTag, backtests: backtests,
           clear: clear, lastItems: lastItems, ready: true };
})();
// [PO-PRO-OK:history]

'@
  'src/indicators.js' = @'
// ============================================================
// indicators.js - PRO v3.4.0
// RSI, Estocastico 14,3,3 COMPLETO (%K/%D con cruces), Momentum,
// MACD completo (linea/senal/histograma) y cruce EMA9/SMA10.
// Usan el CIERRE real de cada vela (borde del cuerpo).
// Coordenada Y invertida: negamos para tratar como "precio".
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('indicators');

POScannerPRO.Indicators = (() => {

  const closes = candles => candles.map(c => -c.close);
  const highs  = candles => candles.map(c => -c.high);
  const lows   = candles => candles.map(c => -c.low);

  function rsi(candles, period) {
    period = period || 14;
    const c = closes(candles);
    if (c.length < period + 1) return 50;
    let gains = 0, losses = 0;
    for (let i = c.length - period; i < c.length; i++) {
      const d = c[i] - c[i - 1];
      if (d > 0) gains += d; else losses -= d;
    }
    if (losses === 0) return 100;
    return 100 - 100 / (1 + gains / losses);
  }

  // SMA de los ultimos "period" valores de un arreglo
  function sma(values, period) {
    if (values.length < period) period = values.length;
    if (!period) return 0;
    let s = 0;
    for (let i = values.length - period; i < values.length; i++) s += values[i];
    return s / period;
  }

  // Estocastico SIMPLE (compatibilidad): %K sin suavizar
  function stochastic(candles, period) {
    period = period || 14;
    const win = candles.slice(-period);
    if (!win.length) return 50;
    const hh = Math.max.apply(null, highs(win));
    const ll = Math.min.apply(null, lows(win));
    const last = -win[win.length - 1].close;
    if (hh === ll) return 50;
    return (last - ll) / (hh - ll) * 100;
  }

  // ESTOCASTICO COMPLETO 14,3,3 (v3.4.0):
  //   %K crudo de cada cierre -> %K suavizado (SMA de "slowing")
  //   -> %D = SMA de "dP" del %K suavizado. Devuelve valor actual
  //   y anterior para detectar CRUCES %K/%D (como en tu grafico PO).
  function stochasticFull(candles, kP, slowing, dP) {
    kP = kP || 14; slowing = slowing || 3; dP = dP || 3;
    const n = candles.length;
    if (n < kP + slowing + dP) return { k: 50, d: 50, prevK: 50, prevD: 50 };
    // 1) %K crudo para cada posicion final posible
    const raw = [];
    for (let end = kP; end <= n; end++) {
      const win = candles.slice(end - kP, end);
      const hh = Math.max.apply(null, highs(win));
      const ll = Math.min.apply(null, lows(win));
      const last = -win[win.length - 1].close;
      raw.push(hh === ll ? 50 : (last - ll) / (hh - ll) * 100);
    }
    // 2) %K suavizado = SMA de los ultimos "slowing" crudos
    const ks = [];
    for (let i = slowing; i <= raw.length; i++) ks.push(sma(raw.slice(0, i), slowing));
    // 3) %D = SMA de los ultimos "dP" %K suavizados
    const ds = [];
    for (let i = dP; i <= ks.length; i++) ds.push(sma(ks.slice(0, i), dP));
    return {
      k: ks[ks.length - 1], d: ds[ds.length - 1],
      prevK: ks[ks.length - 2], prevD: ds[ds.length - 2]
    };
  }

  function momentum(candles, period) {
    period = period || 10;
    const c = closes(candles);
    if (c.length < period + 1) return 0;
    return c[c.length - 1] - c[c.length - 1 - period];
  }

  // EMA simple (base del MACD)
  function ema(values, period) {
    const k = 2 / (period + 1);
    let e = values[0];
    for (let i = 1; i < values.length; i++) e = values[i] * k + e * (1 - k);
    return e;
  }

  // Serie EMA completa (para MACD y cruces)
  function emaSeries(values, period) {
    const k = 2 / (period + 1);
    const out = [values[0]];
    for (let i = 1; i < values.length; i++) out.push(values[i] * k + out[i - 1] * (1 - k));
    return out;
  }

  // MACD simple (compatibilidad): EMA12 - EMA26
  function macd(candles) {
    const c = closes(candles);
    if (c.length < 27) return 0;
    return ema(c.slice(-26), 12) - ema(c, 26);
  }

  // MACD COMPLETO (v3.4.0): linea MACD, linea de senal (EMA9)
  // e HISTOGRAMA con deteccion de cruce y de giro (reversion).
  function macdFull(candles) {
    const c = closes(candles);
    if (c.length < 35) return null;
    const e12 = emaSeries(c, 12), e26 = emaSeries(c, 26);
    const line = [];
    for (let i = 0; i < c.length; i++) line.push(e12[i] - e26[i]);
    const sig = emaSeries(line.slice(26), 9); // senal sobre la linea
    const m = line[line.length - 1], pm = line[line.length - 2];
    const s = sig[sig.length - 1], ps = sig[sig.length - 2];
    const h = m - s, ph = pm - ps;
    return {
      line: m, signal: s, hist: h, prevHist: ph,
      rising: h > ph,                      // histograma creciendo
      crossUp: pm <= ps && m > s,          // cruce alcista reciente
      crossDown: pm >= ps && m < s         // cruce bajista reciente
    };
  }

  // CRUCE EMA 9 / SMA 10 (v3.4.0): el par que activaste en PO.
  // Devuelve estado (quien va arriba) y si hubo cruce en la ultima vela.
  function emaSmaCross(candles, fastP, slowP) {
    fastP = fastP || 9; slowP = slowP || 10;
    const c = closes(candles);
    if (c.length < slowP + 2) return { state: 'FLAT', crossed: null };
    const eNow = ema(c, fastP), ePrev = ema(c.slice(0, -1), fastP);
    const sNow = sma(c, slowP), sPrev = sma(c.slice(0, -1), slowP);
    const dNow = eNow - sNow, dPrev = ePrev - sPrev;
    let crossed = null;
    if (dPrev <= 0 && dNow > 0) crossed = 'CALL';  // EMA9 cruzo ARRIBA de SMA10
    if (dPrev >= 0 && dNow < 0) crossed = 'PUT';   // EMA9 cruzo ABAJO de SMA10
    return { state: dNow > 0 ? 'UP' : (dNow < 0 ? 'DOWN' : 'FLAT'), crossed: crossed };
  }

  // Conteo alcistas/bajistas en la ventana
  function votes(candles) {
    const call = candles.filter(c => c.dir === 'CALL').length;
    return { call: call, put: candles.length - call, total: candles.length };
  }

  return { rsi: rsi, sma: sma, stochastic: stochastic, stochasticFull: stochasticFull,
           momentum: momentum, ema: ema, macd: macd, macdFull: macdFull,
           emaSmaCross: emaSmaCross, votes: votes };
})();
// [PO-PRO-OK:indicators]

'@
  'src/orderFlowDetector.js' = @'
// ============================================================
// orderFlowDetector.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Inferencia de ORDER FLOW (presion compra/venta). ADAPTACION
// HONESTA: el bot lee PIXELES, no existe vela.volumen real en
// OTC de pantalla. El "volumen relativo" del doctorado se
// aproxima con el RANGO de la vela (high-low): una vela con
// rango 2x el promedio movio mucho precio = actividad alta.
//   - presionCompra/presionVenta: mismo algoritmo del curso,
//     usando rangoRelativo en vez de volumenRelativo.
//   - actividad (ALTA/MEDIA/BAJA): rango medio de las ultimas
//     5 velas vs las 15 anteriores (proxy de volumen anomalo).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('orderFlowDetector');

POScannerPRO.OrderFlowDetector = (() => {

  function rango(c) { return Math.max(1, c.low - c.high); } // px (Y invertida)

  // Presion de compra/venta inferida (proxy por rango)
  function inferirOrderFlow(candles) {
    const last = candles.slice(-10);
    if (last.length < 3) {
      return { presionCompra: 0, presionVenta: 0, ratio: 1,
               interpretacion: 'EQUILIBRIO' };
    }
    const prom = last.reduce((a, c) => a + rango(c), 0) / last.length || 1;
    let presionCompra = 0, presionVenta = 0;
    last.forEach(v => {
      const rel = rango(v) / prom;   // proxy de volumenRelativo
      if (v.dir === 'CALL') {        // vela alcista
        presionCompra += rel > 1.5 ? rel * 2 : 1;
      } else if (v.dir === 'PUT') {  // vela bajista
        presionVenta += rel > 1.5 ? rel * 2 : 1;
      }
    });
    const ratio = presionVenta > 0 ? presionCompra / presionVenta
                                   : (presionCompra > 0 ? 99 : 1);
    return {
      presionCompra: Math.round(presionCompra * 10) / 10,
      presionVenta: Math.round(presionVenta * 10) / 10,
      ratio: Math.round(ratio * 100) / 100,
      interpretacion: ratio > 1.5 ? 'MAYORIA COMPRADORA' :
                      ratio < 0.67 ? 'MAYORIA VENDEDORA' : 'EQUILIBRIO'
    };
  }

  // ACTIVIDAD (proxy de volumen): rango reciente vs rango previo
  function actividad(candles) {
    if (candles.length < 20) return { nivel: 'MEDIA', pct: 100 };
    const rec = candles.slice(-5).reduce((a, c) => a + rango(c), 0) / 5;
    const ant = candles.slice(-20, -5).reduce((a, c) => a + rango(c), 0) / 15 || 1;
    const pct = Math.round(rec / ant * 100);
    return { nivel: pct > 140 ? 'ALTA' : pct < 70 ? 'BAJA' : 'MEDIA', pct: pct };
  }

  function analyze(candles) {
    const flow = inferirOrderFlow(candles);
    const act = actividad(candles);
    return {
      presionCompra: flow.presionCompra,
      presionVenta: flow.presionVenta,
      ratio: flow.ratio,
      interpretacion: flow.interpretacion,
      actividad: act.nivel,        // ALTA / MEDIA / BAJA
      actividadPct: act.pct,
      proxy: true                  // recordatorio: sin volumen real
    };
  }

  return { analyze: analyze, inferirOrderFlow: inferirOrderFlow,
           actividad: actividad };
})();
// [PO-PRO-OK:orderFlowDetector]

'@
  'src/panel.js' = @'
// ============================================================
// panel.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Panel flotante PRO: ID unico (#po-pro-panel), posicion
// abajo-IZQUIERDA y color verde neon (diferente al v2.0.4).
// v3.4.0:
//   - PAYOUT corregido: lee el de la pestana/panel ACTIVO (+92%)
//     ya no el de pestanas inactivas.
//   - LEE TU "TIME" DE PO (00:01:00): la expiracion sugerida
//     respeta TU tiempo de entrada, expresado en velas del
//     timeframe del grafico (ej: 1m = 2 velas de S30).
//   - Detalle: Estocastico %K/%D, cruce EMA9/SMA10, REVERSION.
// v3.5.0: linea CONTEXTO MTF (tendencia de TFs mayores del
//   archivo de velas) + BACKTEST REAL ("Backtest: 68% en N").
//   - Confluencia sobre 12 fuentes.
// v3.5.1:
//   - TIME ROBUSTO: el tiempo de TU orden se lee ANCLADO a la
//     etiqueta "Time" del panel de PO (ya no "el reloj mas alto
//     de la derecha", que era fragil). Respaldo: metodo viejo.
//   - Celda TIMEFRAME muestra "S30 / 1m" = grafico / tu orden.
//   - findCurrentPrice(): precio REAL de la etiqueta resaltada
//     del eje derecho, para evaluar WIN/LOSS con precios reales
//     (los pixeles-Y cambian con el zoom: daban el 0% falso).
// v3.5.2:
//   - findCurrentPrice v2: el fondo pintado de la etiqueta del
//     precio suele estar en el CONTENEDOR PADRE, no en el span
//     del texto (por eso la v3.5.1 no lo encontraba y caia al
//     respaldo-Y -> el 3% falso). Ahora sube hasta 3 niveles.
//   - ANTI-CUENTA-REGRESIVA: con una operacion abierta, PO
//     muestra un countdown junto al Time; si el valor baja
//     justo lo que paso de tiempo, NO es tu Time configurado:
//     se ignora y se conserva el ultimo valor valido.
//   - ACIERTO muestra empates: "52% (30W/28L/2E)".
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('panel');

POScannerPRO.Panel = (() => {
  const CFG = POScannerPRO.CONFIG;
  let root = null;
  let tfSec = 60;          // timeframe del grafico en segundos
  let tradeSec = 0;        // TU tiempo de entrada en PO (0 = no leido)
  let lastTT = 0;          // ultimo Time leido (anti-countdown)
  let lastTTAt = 0;        // momento de esa lectura
  const on = {};

  function html() {
    return '' +
    '<div class="pop-header">' +
      '<span>PO Chart Scanner <b>PRO v' + CFG.VERSION + '</b></span>' +
      '<span class="pop-close" data-act="close">x</span>' +
    '</div>' +
    '<div class="pop-status" data-f="status">Listo</div>' +
    '<div class="pop-grid">' +
      '<div class="pop-cell"><label>ACTIVO</label><b data-f="asset">-</b></div>' +
      '<div class="pop-cell"><label>PAYOUT</label><b data-f="payout">-</b></div>' +
      '<div class="pop-cell"><label>TIMEFRAME</label><b data-f="time">-</b></div>' +
      '<div class="pop-cell"><label>EJEC</label><b data-f="exec">--:--</b></div>' +
      '<div class="pop-cell"><label>VELAS</label><b data-f="candles">0</b></div>' +
      '<div class="pop-cell"><label>ACIERTO</label><b data-f="acc">-</b></div>' +
    '</div>' +
    '<div class="pop-signal">' +
      '<span class="pop-dir" data-f="dir">-</span>' +
      '<span class="pop-score" data-f="score">-/100</span>' +
    '</div>' +
    '<div class="pop-action" data-f="action"></div>' +
    '<div class="pop-weak" data-f="weak"></div>' +
    '<div class="pop-quality" data-f="quality"></div>' +
    '<div class="pop-detail" data-f="detail">Pulsa ESCANEAR para analizar el grafico.</div>' +
    '<div class="pop-btns">' +
      '<button class="pop-btn pop-green" data-act="scan">ESCANEAR</button>' +
      '<button class="pop-btn" data-act="area">GRAFICO</button>' +
      '<button class="pop-btn" data-act="auto">AUTO</button>' +
      '<button class="pop-btn" data-act="history">HISTORIAL</button>' +
      '<button class="pop-btn" data-act="settings">AJUSTES</button>' +
      '<button class="pop-btn" data-act="reset">RESET</button>' +
    '</div>' +
    '<div class="pop-disclaimer">' +
      'Herramienta educativa. No garantiza resultados. Alto riesgo de perdida.' +
    '</div>';
  }

  function mount(callbacks) {
    Object.assign(on, callbacks);
    if (document.getElementById('po-pro-panel')) return; // no duplicar
    root = document.createElement('div');
    root.id = 'po-pro-panel';
    root.innerHTML = html();
    document.body.appendChild(root);

    root.addEventListener('click', function(e) {
      const act = e.target.dataset && e.target.dataset.act;
      if (act === 'close') { root.remove(); return; }
      if (act && on[act]) {
        e.target.classList.add('pop-flash');
        setTimeout(() => e.target.classList.remove('pop-flash'), 300);
        set('status', 'Procesando: ' + act.toUpperCase() + '...');
        on[act]();
      }
    });
    makeDraggable(root, root.querySelector('.pop-header'));
    refreshDOM();
    setInterval(refreshDOM, 3000);
    setInterval(tickClock, 1000);   // cuenta regresiva de la vela
    tickClock();
  }

  // Cuenta regresiva de la vela actual segun el timeframe detectado
  function tickClock() {
    const now = Math.floor(Date.now() / 1000);
    const left = tfSec - (now % tfSec);
    const mm = Math.floor(left / 60), ss = left % 60;
    set('exec', (mm < 10 ? '0' + mm : mm) + ':' + (ss < 10 ? '0' + ss : ss));
  }

  // Activo REAL del grafico: el par con la fuente mas grande
  function findActivePair() {
    let best = null, bestSize = 0;
    document.querySelectorAll('span, div, a, button').forEach(el => {
      const t = (el.textContent || '').trim();
      if (t.length > 14) return;
      if (!/^[A-Z]{3}\/[A-Z]{3}( OTC)?$/.test(t)) return;
      if (el.children.length > 2) return;
      const size = parseFloat(getComputedStyle(el).fontSize) || 0;
      if (size > bestSize) { bestSize = size; best = t; }
    });
    return best;
  }

  // PAYOUT CORREGIDO (v3.4.0): prefiere "+NN%" del panel de
  // operacion (lado derecho, fuente grande) = el de TU activo.
  function findPayout() {
    let best = null, bestSize = 0;
    document.querySelectorAll('span, div').forEach(el => {
      if (el.closest && el.closest('#po-pro-panel')) return; // no leernos
      const t = (el.textContent || '').trim();
      if (!/^\+\d{1,3}%$/.test(t)) return;
      const r = el.getBoundingClientRect();
      if (r.left < innerWidth * 0.55) return;   // solo lado derecho
      const size = parseFloat(getComputedStyle(el).fontSize) || 0;
      if (size > bestSize) { bestSize = size; best = t.replace('+', ''); }
    });
    if (best) return best;
    const m = document.body.innerText.match(/\+\s?(\d{2})\s?%/);
    return m ? m[1] + '%' : null;
  }

  // LEE TU "TIME" DE PO - ROBUSTO (v3.5.1):
  // 1) ANCLADO: localiza la etiqueta "Time" del panel de
  //    operacion (lado derecho), sube a su contenedor y lee el
  //    valor HH:MM:SS que PO pone junto a ella = el tiempo de
  //    TU orden (el que puedes cambiar a 30s, 1m, 5m...).
  // 2) RESPALDO (v3.4.0): el reloj mas alto del lado derecho.
  function findTradeTime() {
    // --- Metodo ANCLADO a la etiqueta "Time" ---
    let label = null;
    document.querySelectorAll('span, div, label, p').forEach(el => {
      if (label) return;
      if (el.closest && el.closest('#po-pro-panel')) return;
      if (el.children.length) return;                 // solo hojas
      const t = (el.textContent || '').trim();
      if (!/^(time|tiempo)$/i.test(t)) return;
      const r = el.getBoundingClientRect();
      if (r.left < innerWidth * 0.5 || r.top > innerHeight * 0.7) return;
      label = el;
    });
    if (label) {
      let box = label;
      for (let up = 0; up < 4 && box; up++) {
        box = box.parentElement;
        if (!box) break;
        // v3.5.2: recolectar TODOS los candidatos y preferir el
        // campo INPUT (el Time configurado de PO es un input con
        // flechas; el countdown de una operacion abierta es texto)
        let candInput = 0, candText = 0;
        box.querySelectorAll('span, div, input').forEach(el => {
          if (el === label || el.contains(label)) return;
          if (el.children.length > 1) return;
          const t = ((el.value !== undefined ? el.value : el.textContent) || '').trim();
          const m = t.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
          if (!m) return;
          const sec = m[3] !== undefined
            ? (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3])
            : (+m[1]) * 60 + (+m[2]);
          if (el.tagName === 'INPUT') { if (!candInput) candInput = sec; }
          else if (!candText) candText = sec;
        });
        const found = candInput || candText;
        if (found > 0) return found;
      }
    }
    // --- RESPALDO: reloj mas alto del lado derecho (v3.4.0) ---
    let best = 0, bestTop = 1e9;
    document.querySelectorAll('span, div, input').forEach(el => {
      if (el.closest && el.closest('#po-pro-panel')) return;
      const t = ((el.value !== undefined ? el.value : el.textContent) || '').trim();
      const m = t.match(/^(\d{2}):(\d{2})(?::(\d{2}))?$/);
      if (!m) return;
      const r = el.getBoundingClientRect();
      if (r.left < innerWidth * 0.55) return;          // lado derecho
      if (r.top > innerHeight * 0.6 || r.top < 0) return; // zona superior
      if (el.children.length > 2) return;
      if (r.top < bestTop) {
        bestTop = r.top;
        // HH:MM:SS o MM:SS -> segundos
        best = m[3] !== undefined
          ? (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3])
          : (+m[1]) * 60 + (+m[2]);
      }
    });
    return best;
  }

  // ============================================================
  // PRECIO REAL del eje - v4.4.1 ROBUSTO
  // PO dibuja el precio actual en una etiqueta RESALTADA (con
  // fondo pintado) pegada al eje derecho. Ese numero es la unica
  // fuente de verdad para el WIN/LOSS: los pixeles-Y se re-escalan
  // con el zoom y el auto-scroll.
  //
  // Si esto devuelve null, el panel avisa "precio: archivo" y el
  // historial pasa a comparar cierres en la escala del archivo,
  // que es MUCHO menos fiable (de ahi los empates de mas).
  //
  // La v3.5.2 fallaba por cuatro motivos, corregidos aqui:
  //   1) exigia el nodo SIN hijos; PO envuelve digitos en spans
  //      para animar el ultimo decimal -> se permite 1 hijo y se
  //      lee tambien el texto propio del nodo.
  //   2) solo miraba de 0.55 a 0.95 del ancho; con el panel
  //      movido o pantallas anchas el eje cae fuera -> 0.5 a 1.0.
  //   3) se quedaba con el ULTIMO que casara en orden de DOM
  //      (arbitrario) -> ahora gana el mas a la DERECHA, que es
  //      el del eje de precio.
  //   4) 'rgba(x,y,z,0)' es transparente pero no era descartado.
  // Se sigue EXIGIENDO el fondo pintado: sin el no se distingue
  // el precio actual de una etiqueta fija del eje, y devolver una
  // fija seria peor que devolver null (mediria siempre lo mismo).
  // ============================================================
  const PRICE_RE = /^\d{1,7}[.,]\d{2,6}$/;

  function bgPintado(el) {
    let node = el;
    for (let up = 0; up < 4 && node; up++) {
      let b = '';
      try { b = getComputedStyle(node).backgroundColor || ''; } catch (e) { b = ''; }
      const transparente = !b || b === 'transparent' ||
        /^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0\s*\)$/.test(b);
      if (!transparente) return { bg: b, depth: up };
      node = node.parentElement;
    }
    return { bg: '', depth: -1 };
  }

  // Todos los nodos que parecen un precio, con sus coordenadas.
  // Expuesto para diagnosticar desde la consola:
  //   POScannerPRO.Panel.priceCandidates()
  function priceCandidates() {
    const out = [];
    document.querySelectorAll('span, div, td, b').forEach(el => {
      if (el.closest && el.closest('#po-pro-panel')) return;
      if (el.children.length > 1) return;         // 1 hijo: digito animado
      const t = (el.textContent || '').trim();
      if (!PRICE_RE.test(t)) return;
      let r;
      try { r = el.getBoundingClientRect(); } catch (e) { return; }
      if (!r || r.width <= 0 || r.height <= 0) return;
      const p = bgPintado(el);
      const dec = (t.split(/[.,]/)[1] || '').length;
      out.push({
        text: t, value: parseFloat(t.replace(',', '.')),
        x: Math.round(r.left), y: Math.round(r.top),
        cy: r.top + r.height / 2,          // centro vertical (calibracion)
        w: Math.round(r.width), h: Math.round(r.height),
        dec: dec, bg: p.bg, depth: p.depth,
        enBanda: r.left >= innerWidth * 0.5
      });
    });
    return out.sort((a, b) => b.x - a.x);
  }

  function findCurrentPrice() {
    const cands = priceCandidates().filter(c => c.enBanda && c.bg);
    return cands.length ? cands[0].value : null;   // el mas a la derecha
  }

  // ============================================================
  // METODO 2 (v4.4.2): CALIBRAR LA ESCALA DEL EJE.
  // Cuando la etiqueta resaltada no se encuentra, el eje de precio
  // sigue ahi con sus etiquetas fijas. Cada una es un par
  // (pixel Y, precio): con tres o mas se ajusta por minimos
  // cuadrados la recta  precio = a * y + b  y con ella se traduce
  // CUALQUIER pixel a precio real, incluida la ultima vela leida.
  //
  // Esto no es una estimacion vaga: la escala de un grafico es
  // lineal por construccion, asi que el ajuste es exacto salvo
  // error de redondeo de las etiquetas. Se exige R2 >= 0.995 y
  // pendiente negativa (en pantalla, bajar de Y = subir de precio);
  // si el ajuste no cumple, se devuelve null en vez de un numero
  // inventado.
  // ============================================================
  function axisScale() {
    const c = priceCandidates().filter(p => p.enBanda);
    if (c.length < 3) return null;
    // Agrupar por columna: el eje es una columna de etiquetas
    const cols = [];
    c.forEach(p => {
      const col = cols.find(k => Math.abs(k.x - p.x) <= 40);
      if (col) { col.items.push(p); col.x = Math.max(col.x, p.x); }
      else cols.push({ x: p.x, items: [p] });
    });
    cols.sort((a, b) => b.x - a.x);          // la mas a la derecha primero
    for (let i = 0; i < cols.length; i++) {
      const pts = [];
      cols[i].items.forEach(p => {
        if (!pts.some(q => q.value === p.value)) pts.push(p);
      });
      if (pts.length < 3) continue;
      let sx = 0, sy = 0, sxx = 0, sxy = 0;
      const n = pts.length;
      pts.forEach(p => { sx += p.cy; sy += p.value; sxx += p.cy * p.cy; sxy += p.cy * p.value; });
      const den = n * sxx - sx * sx;
      if (Math.abs(den) < 1e-9) continue;
      const a = (n * sxy - sx * sy) / den;
      const b = (sy - a * sx) / n;
      if (!isFinite(a) || a >= 0) continue;   // Y baja = precio sube
      const media = sy / n;
      let ssRes = 0, ssTot = 0;
      pts.forEach(p => {
        const pred = a * p.cy + b;
        ssRes += (p.value - pred) * (p.value - pred);
        ssTot += (p.value - media) * (p.value - media);
      });
      const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 0;
      if (r2 < 0.995) continue;               // eje mal leido: no forzar
      const dec = Math.max.apply(null, pts.map(p => p.dec));
      return { a: a, b: b, n: n, r2: r2, x: cols[i].x, dec: dec };
    }
    return null;
  }

  // Pixel Y del viewport -> precio real, usando la escala del eje
  function priceFromY(yViewport) {
    const s = axisScale();
    if (!s) return null;
    const v = s.a * yViewport + s.b;
    if (!isFinite(v)) return null;
    return parseFloat(v.toFixed(Math.min(8, s.dec + 1)));
  }

  // Precio de una vela leida. candle viene en coordenadas de
  // IMAGEN; conv (de CanvasReader.lastStats) las lleva al viewport.
  function priceFromCandle(candle, conv) {
    if (!candle || !conv || !conv.sy) return null;
    return priceFromY(conv.top + candle.close / conv.sy);
  }

  // Diagnostico para la consola: por que no encuentra el precio.
  //   POScannerPRO.Panel.diagPrice()
  function diagPrice() {
    const todos = priceCandidates();
    const enBanda = todos.filter(c => c.enBanda);
    const conFondo = enBanda.filter(c => c.bg);
    console.log('[PO PRO] precio: ' + todos.length + ' nodos con formato de precio, ' +
      enBanda.length + ' en la banda derecha (x >= ' + Math.round(innerWidth * 0.5) +
      '), ' + conFondo.length + ' con fondo pintado.');
    console.log('[PO PRO] findCurrentPrice() =', findCurrentPrice());
    const s = axisScale();
    if (s) {
      console.log('[PO PRO] escala del eje calibrada con ' + s.n + ' etiquetas, ' +
        'R2=' + s.r2.toFixed(5) + ' -> precio = ' + s.a.toExponential(3) +
        ' * y + ' + s.b.toFixed(s.dec));
    } else {
      console.log('[PO PRO] escala del eje NO calibrada: hacen falta 3+ ' +
        'etiquetas de precio alineadas en la misma columna.');
    }
    if (todos.length) console.table(todos.slice(0, 25));
    else console.log('[PO PRO] Ningun nodo casa con ' + PRICE_RE +
      '. Puede que PO parta el precio en varios elementos.');
    return { total: todos.length, enBanda: enBanda.length,
             conFondo: conFondo.length, escala: s,
             candidatos: todos.slice(0, 25) };
  }

  // Lee activo, payout, timeframe y tu Time del DOM de PO
  function refreshDOM() {
    const bodyText = document.body.innerText;
    const pair = findActivePair() ||
      (bodyText.match(/[A-Z]{3}\/[A-Z]{3}\s*OTC?/) || [null])[0];
    const payout = findPayout();
    const tf = (bodyText.match(/\b(S5|S15|S30|M1|M3|M5|M15|M30|H1|H4|D1)\b/) || [null])[0];
    const tt = findTradeTime();
    // v3.5.2 ANTI-CUENTA-REGRESIVA: si el valor leido baja justo
    // lo que paso de tiempo real, es el countdown de una operacion
    // abierta, NO tu Time configurado: ignorarlo y conservar el
    // ultimo valor valido. Un cambio tuyo (5m->1m) es un salto
    // grande y si pasa.
    if (tt > 0) {
      const nowMs = Date.now();
      const elapsed = (nowMs - lastTTAt) / 1000;
      const looksCountdown = lastTT > 0 && tt < lastTT &&
        (lastTT - tt) <= elapsed + 1.5 && elapsed <= 30;
      if (!looksCountdown) tradeSec = tt;
      lastTT = tt; lastTTAt = nowMs;
    }
    set('asset', pair || '-');
    set('payout', payout || '-');
    // mostrar "S30 / 1m" = timeframe del grafico / tu orden VALIDADA
    set('time', (tf || '-') + (tradeSec > 0 ? ' / ' + fmtSec(tradeSec) : ''));
    if (tf && CFG.TF_SECONDS[tf]) tfSec = CFG.TF_SECONDS[tf];
  }

  // Formatea segundos como "30s", "1m", "5m"
  function fmtSec(s) {
    if (s % 3600 === 0) return (s / 3600) + 'h';
    if (s % 60 === 0) return (s / 60) + 'm';
    return s + 's';
  }

  function set(field, value) {
    const el = root && root.querySelector('[data-f="' + field + '"]');
    if (el) el.textContent = value;
  }

  // Ocultar/mostrar el panel (el Motor 2 lo oculta durante la foto)
  function setVisible(v) {
    if (root) root.style.visibility = v ? 'visible' : 'hidden';
  }

  // Texto de expiracion CONSCIENTE DEL TIMEFRAME (v3.4.0):
  // respeta tu Time de PO y lo traduce a velas del grafico.
  function expiryInfo() {
    if (!tradeSec) {
      return { text: '1 vela (' + fmtSec(tfSec) + ')', candles: 1,
               warn: '', deadlineMs: tfSec * 1000 };
    }
    const n = Math.max(1, Math.round(tradeSec / tfSec));
    const warn = tradeSec < tfSec
      ? '\nOJO: tu tiempo (' + fmtSec(tradeSec) + ') es MENOR que 1 vela (' +
        fmtSec(tfSec) + '): la senal es menos fiable'
      : '';
    return {
      text: fmtSec(tradeSec) + ' (= ' + n + ' vela' + (n > 1 ? 's' : '') +
            ' de ' + fmtSec(tfSec) + ')',
      candles: n, warn: warn, deadlineMs: tradeSec * 1000
    };
  }

  // v4.4 ETIQUETA DE ACCION: traduce el score a una orden clara
  // para no tener que decidirlo mentalmente. Una senal bloqueada
  // es BLOQUEADA sea cual sea su puntaje.
  function actionLabel(r) {
    const F = CFG.FILTER || {};
    const OP = F.OPERAR != null ? F.OPERAR : 90;
    const OPC = F.OPERAR_CONTRARIAN != null ? F.OPERAR_CONTRARIAN : 85;
    const MED = F.RIESGO_MEDIO != null ? F.RIESGO_MEDIO : 75;
    const NO = F.NO_OPERAR != null ? F.NO_OPERAR : 60;
    if (r.blocked) return { text: 'BLOQUEADA - NO OPERAR', cls: 'pop-act-bloqueada' };
    const s = r.score;
    if (s >= OP)  return { text: 'OPERAR', cls: 'pop-act-operar' };
    if (s >= OPC) return { text: r.contrarian ? 'OPERAR (CONTRARIAN)'
                                              : 'OPERAR SI CONTRARIAN',
                           cls: 'pop-act-cond' };
    if (s >= MED) return { text: 'RIESGO MEDIO', cls: 'pop-act-medio' };
    if (s >= NO)  return { text: 'NO OPERAR', cls: 'pop-act-no' };
    return { text: 'NO OPERAR - SCORE BAJO', cls: 'pop-act-bloqueada' };
  }

  // Resultado de un escaneo (patrones, S/R, tendencia + entrada sugerida)
  function showResult(r) {
    set('candles', r.detail.velas);
    // v4.1: si el filtro estructural techo la senal (contra
    // tendencia / S/R / MTF), la direccion sale en AMARILLO.
    // v4.2: BLOQUEO TOTAL: la senal techada ya NO se muestra como
    // entrada. El panel dice ESPERAR y el score real queda tachado
    // (transparencia: ves lo que la votacion decia, pero bloqueado).
    const warn = r.warning || null;
    const blocked = !!r.blocked;
    // v4.3: el bloqueo puede ser por ESTRUCTURA (v4.2) o por
    // MASA OBVIA (v4.3: senal que todos ven + trampa en contra)
    if (blocked) {
      set('dir', 'ESPERAR');
      set('score', r.rawScore + '/100');
      set('quality', r.blockReason === 'masa'
        ? '!! BLOQUEADO: MASA OBVIA - TRAMPA PROBABLE !!'
        : r.blockReason === 'confluencia'
        ? '!! BLOQUEADA: CONFLUENCIA INSUFICIENTE !!'
        : '!! SENAL BLOQUEADA - CONTRA-ESTRUCTURA !!');
    } else {
      set('dir', r.dir);
      set('score', r.score + '/100');
      set('quality', warn
        ? '!! SENAL CONTRA-ESTRUCTURA - Riesgo Alto !!'
        : (r.contrarian ? '[!] SENAL CONTRARIAN | Calidad: ' + r.quality
           : (r.confirmed ? 'Calidad: ' + r.quality : 'NO CONFIRMADO')));
    }
    const qEl = root.querySelector('[data-f="quality"]');
    if (qEl) qEl.className = 'pop-quality' + (warn ? ' pop-warn' : '');
    const dirEl = root.querySelector('[data-f="dir"]');
    dirEl.className = 'pop-dir ' + (warn ? 'pop-warn'
      : (r.dir === 'CALL' ? 'pop-call' : 'pop-put'));
    const sEl = root.querySelector('[data-f="score"]');
    if (sEl) sEl.className = 'pop-score' + (blocked ? ' pop-blocked' : '');
    // v4.4: ETIQUETA DE ACCION + aviso de senal debil
    const act = actionLabel(r);
    set('action', act.text);
    const aEl = root.querySelector('[data-f="action"]');
    if (aEl) aEl.className = 'pop-action ' + act.cls;
    const F4 = CFG.FILTER || {};
    const weakWarn = F4.WEAK_WARN != null ? F4.WEAK_WARN : 85;
    const entryMin = F4.ENTRY_MIN != null ? F4.ENTRY_MIN : 75;
    set('weak', blocked ? ''
      : (r.score < entryMin
          ? 'Sin entrada en el grafico: score bajo ' + entryMin
          : (r.score < weakWarn
              ? 'Senal debil, esperar mejor setup'
              : '')));
    const d = r.detail;
    // Acierto historico real de senales de ESTA calidad (aprendizaje)
    let histLine = '';
    try {
      const hq = POScannerPRO.History.byQuality(r.quality);
      if (hq.n > 0) histLine = '\nHistorico ' + r.quality + ': ' + hq.acc + '% en ' + hq.n + ' senales';
    } catch (e) { /* historial aun sin byQuality */ }
    const exp = expiryInfo();
    r.expiryText = tradeSec ? fmtSec(tradeSec) : fmtSec(tfSec); // para el overlay
    // v4.2: BACKTEST MADURO - el % solo se muestra con 30+ senales
    // de muestra; con menos, se indica el progreso de acumulacion.
    const btMin = (POScannerPRO.CONFIG.ARCHIVE.BT_MIN_SHOW || 30);
    const btLine = (r.backtest && r.backtest.n > 0)
      ? (r.backtest.n >= btMin
        ? ' | Backtest real: ' + r.backtest.acc + '% en ' + r.backtest.n + ' senales'
        : ' | Backtest: acumulando muestra (' + r.backtest.n + '/' + btMin + ' senales, aun sin %)')
      : '';
    set('detail',
      (blocked
        ? (r.blockReason === 'masa'
          ? '[X] BLOQUEADO: MASA OBVIA. La senal ' + r.dir + ' ' +
            r.rawScore + '/100 es la que TODOS ven y hay trampa del ' +
            'broker en contra (fakeout). NO entrar.\n'
          : r.blockReason === 'confluencia'
          ? '[X] BLOQUEADA: solo ' + (d.confluencia || '-') + ' fuentes ' +
            'coinciden. El ' + r.score + '% mide el reparto de votos, no ' +
            'cuantas fuentes votaron: con tan pocas es ruido. NO entrar.\n'
          : '[X] BLOQUEADA: la votacion interna decia ' + r.dir + ' ' +
            r.rawScore + '/100, pero va CONTRA la estructura del mercado. NO entrar.\n')
        : '') +
      (r.perfecto && !blocked
        ? '[*] SETUP CONTRARIAN PERFECTO: las 6 condiciones del metodo ' +
          'se cumplen (nivel fuerte, fakeout, contra la masa, confluencia, ' +
          'backtest y trap bajo).\n'
        : '') +
      (r.contrarian && !blocked
        ? '[!] SENAL CONTRARIAN: fakeout a favor, se opera CONTRA la ruptura falsa.\n'
        : '') +
      (warn ? '[!] ' + warn + '\n' : '') +
      (r.note ? '[*] ' + r.note + '\n' : '') +
      (r.contraNote ? '[*] ' + r.contraNote + '\n' : '') +
      (d.trapIndex != null
        ? 'Trap Index: ' + d.trapIndex + '% | Actividad: ' +
          (d.actividad || '-') +
          (d.reversalRatio != null ? ' | Reversal Ratio: ' + d.reversalRatio + '%' : '') +
          (d.fakeout ? ' | ' + d.fakeout : '') + '\n'
        : '') +
      'RSI(14): ' + d.rsi + ' | Estoc K/D: ' + d.stoch + '/' + (d.stochD || '-') +
      ' | Mom: ' + d.momentum + '\n' +
      'Medias: ' + (d.emaCross || '-') + ' | MACD hist: ' + d.macd +
      (d.reversion ? '\n>>> REVERSION ' + d.reversion + ' <<<' : '') + '\n' +
      'Patrones: ' + (d.patterns.length ? d.patterns.join(', ') : 'ninguno') + '\n' +
      'S/R: ' + d.srNear + ' (' + d.srLevels + ' niveles) | Tendencia: ' + d.trend +
      (d.trend !== 'FLAT' ? ' (amplitud ' + (d.trendStrength || 0) + '%)' : '') + '\n' +
      'Votos CALL: ' + d.votosCALL + ' | Votos PUT: ' + d.votosPUT +
      ' | Confluencia: ' + (d.confluencia || '-') + '\n' +
      'Contexto MTF: ' + (d.contexto || 'sin datos') + btLine + '\n' +
      btSplit() +
      (blocked
        ? 'ESPERAR: senal bloqueada (' + (r.blockReason || 'estructura') +
          '), sin entrada'
        : (r.confirmed && r.score >= entryMin
          ? 'Entrada: al cierre de esta vela | Expira en: ' + exp.text + exp.warn
          : r.confirmed
          ? 'Senal debil (' + r.score + ' < ' + entryMin +
            '): sin flecha de entrada, esperar mejor setup'
          : 'Espera: puntaje bajo, sin entrada')) + histLine);
    // Actualizar celda ACIERTO con las estadisticas del historial
    try {
      const s = POScannerPRO.History.stats();
      set('acc', s.total ? s.acc + '% (' + s.wins + 'W/' + s.losses + 'L' +
        (s.ties ? '/' + s.ties + 'E' : '') + ')' : '-');
    } catch (e) { /* historial aun no listo */ }
  }

  // v4.4: BACKTEST SEPARADO contrarian / normal / total. El
  // promedio unico escondia que las NORMAL arrastran al conjunto.
  function btSplit() {
    try {
      const b = POScannerPRO.History.backtests();
      const f = x => x.n ? x.acc + '% en ' + x.n : 'sin muestra';
      const leg = b.legacy && b.legacy.n
        ? '\n(' + b.legacy.n + ' senales antiguas excluidas: medidas en ' +
          'pixeles, ' + b.legacy.empates + ' de ellas EMPATE. No se pueden ' +
          'recalcular, PO no da el precio pasado.)'
        : '';
      if (!b.total.n) return leg ? leg.slice(1) + '\n' : '';
      return 'Acierto real -> CONTRARIAN: ' + f(b.contrarian) +
             ' | NORMAL: ' + f(b.normal) +
             ' | TOTAL: ' + f(b.total) + leg + '\n';
    } catch (e) { return ''; }
  }

  // Vista del HISTORIAL con estadisticas reales
  function showHistory() {
    const H = POScannerPRO.History;
    const s = H.stats();
    if (!s.total && !s.cancelled) {
      set('detail', 'Sin senales todavia. Pulsa ESCANEAR y las senales confirmadas se guardaran aqui.');
      set('status', 'HISTORIAL vacio');
      return;
    }
    const lines = H.lastItems(6).map(i =>
      i.time + ' ' + i.dir + ' ' + i.score + '%' +
      (i.tag === 'CONTRARIAN' ? ' [C]' : '') +
      (i.expiryText ? ' ' + i.expiryText : '') + ' -> ' + i.result);
    // v4.3: historial separado contrarian vs normal
    let tagLine = '';
    try {
      const b = H.backtests();
      const f = x => x.n ? x.acc + '% en ' + x.n + ' senales' : 'sin muestra';
      if (b.total.n) {
        tagLine = '\nBACKTEST CONTRARIAN: ' + f(b.contrarian) +
                  '\nBacktest NORMAL: ' + f(b.normal) +
                  '\nBacktest TOTAL: ' + f(b.total);
      }
    } catch (e) { /* historial sin backtests aun */ }
    set('detail',
      'Acierto: ' + s.acc + '% (' + s.wins + 'W/' + s.losses + 'L' +
      (s.ties ? '/' + s.ties + 'E' : '') + ') | Pendientes: ' +
      s.pending + (s.cancelled ? ' | Canceladas: ' + s.cancelled : '') +
      tagLine + '\n' +
      lines.join('\n'));
    set('status', 'HISTORIAL: ' + s.total + ' senales | Acierto real: ' + s.acc + '%');
  }

  // Estado visual del boton AUTO (ON = verde encendido)
  function setAuto(on) {
    const b = root && root.querySelector('[data-act="auto"]');
    if (!b) return;
    b.textContent = on ? 'AUTO ON' : 'AUTO';
    b.classList.toggle('pop-green', !!on);
  }

  function makeDraggable(el, handle) {
    handle.style.cursor = 'move';
    handle.onmousedown = function(e) {
      const dx = e.clientX - el.offsetLeft, dy = e.clientY - el.offsetTop;
      const move = function(ev) {
        el.style.left = (ev.clientX - dx) + 'px';
        el.style.top = (ev.clientY - dy) + 'px';
        el.style.right = 'auto'; el.style.bottom = 'auto';
      };
      const up = function() {
        removeEventListener('mousemove', move);
        removeEventListener('mouseup', up);
      };
      addEventListener('mousemove', move);
      addEventListener('mouseup', up);
    };
  }

  return { mount: mount, set: set, showResult: showResult, setAuto: setAuto,
           actionLabel: actionLabel,
           showHistory: showHistory, setVisible: setVisible,
           getTfSec: () => tfSec, getTradeSec: () => tradeSec,
           expiryInfo: expiryInfo, findCurrentPrice: findCurrentPrice,
           priceCandidates: priceCandidates, diagPrice: diagPrice,
           axisScale: axisScale, priceFromY: priceFromY,
           priceFromCandle: priceFromCandle,
           findTradeTime: findTradeTime };
})();
// [PO-PRO-OK:panel]

'@
  'src/patternDetector.js' = @'
// ============================================================
// patternDetector.js - PRO v3.2.0  [FASE 2 - ACTIVO]
// Reconocimiento de patrones de velas sobre las ultimas velas:
//   DOJI, MARTILLO, ESTRELLA FUGAZ, ENVOLVENTE ALCISTA/BAJISTA
// OJO coordenadas: Y invertida (menor Y = precio mayor).
//   high = Y minima (precio maximo), low = Y maxima (precio min)
// Devuelve lista de patrones: { name, bias } bias: +1 CALL / -1 PUT / 0 neutro
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('patternDetector');

POScannerPRO.PatternDetector = (() => {

  const range = c => Math.max(1, c.low - c.high); // rango total en px

  function detect(candles) {
    const pats = [];
    if (!candles || candles.length < 3) return pats;
    const last = candles[candles.length - 1];
    const prev = candles[candles.length - 2];
    const r = range(last);

    // DOJI: cuerpo minusculo respecto al rango (indecision)
    if (last.bodySize <= r * 0.15 && r >= 4) {
      pats.push({ name: 'DOJI', bias: 0 });
    }

    // MARTILLO: mecha inferior larga, cuerpo pequeno arriba -> rebote CALL
    if (last.wickDown >= last.bodySize * 2 && last.wickUp <= last.bodySize * 0.6 &&
        last.bodySize >= 2) {
      pats.push({ name: 'MARTILLO', bias: 1 });
    }

    // ESTRELLA FUGAZ: mecha superior larga, cuerpo pequeno abajo -> caida PUT
    if (last.wickUp >= last.bodySize * 2 && last.wickDown <= last.bodySize * 0.6 &&
        last.bodySize >= 2) {
      pats.push({ name: 'ESTRELLA FUGAZ', bias: -1 });
    }

    // ENVOLVENTE ALCISTA: vela verde actual envuelve el cuerpo rojo anterior
    if (last.dir === 'CALL' && prev.dir === 'PUT' &&
        last.bodyTop <= prev.bodyTop && last.bodyBottom >= prev.bodyBottom &&
        last.bodySize > prev.bodySize * 1.1) {
      pats.push({ name: 'ENVOLVENTE ALCISTA', bias: 1 });
    }

    // ENVOLVENTE BAJISTA: vela roja actual envuelve el cuerpo verde anterior
    if (last.dir === 'PUT' && prev.dir === 'CALL' &&
        last.bodyTop <= prev.bodyTop && last.bodyBottom >= prev.bodyBottom &&
        last.bodySize > prev.bodySize * 1.1) {
      pats.push({ name: 'ENVOLVENTE BAJISTA', bias: -1 });
    }

    return pats;
  }

  return { detect: detect, ready: true };
})();
// [PO-PRO-OK:patternDetector]

'@
  'src/scoring.js' = @'
// ============================================================
// scoring.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Score 0-100 por votacion ponderada + CONFLUENCIA:
//   12 fuentes de voto: RSI, Estocastico(nivel), Estocastico
//   14,3,3(cruce %K/%D), Momentum, MACD(histograma), MACD(cruce),
//   cruce EMA9/SMA10, estructura de color, patrones, S/R,
//   tendencia y CONTEXTO MULTI-TIMEFRAME (historial archivado
//   de TFs mayores = menos ruido, mas probabilidad).
//   BONUS por confluencia (>=3:+5, >=4:+10, >=5:+15).
// v3.4.0: DETECTOR DE REVERSION FUERTE (alcista/bajista): si 3+
// condiciones de giro coinciden, suma como fuente extra con peso
// doble y lo anuncia en detail.reversion.
// v4.1.0: FILTRO ESTRUCTURAL (casco anti contra-tendencia).
//   El motor vota igual que siempre, pero al final una capa de
//   ESTRUCTURA DE MERCADO revisa la senal ganadora:
//     - CONTRA TENDENCIA fuerte (strength>=50) -> techo 60
//     - CONTRA S/R (CALL en resistencia / PUT en soporte)
//       -> techo 60 (55 si el nivel tiene 3+ toques)
//     - CONTRA contexto MTF (archivo de TFs mayores) -> techo 55
//     - Las TRES a la vez -> techo 45
//   EXCEPCION: ruptura confirmada del nivel (3 velas cerrando
//   mas alla) anula el techo de S/R. El techo baja la calidad
//   y suele apagar la confirmacion (<65): la senal PELIGROSA se
//   muestra con advertencia amarilla y NO entra al historial.
// v4.3.0: CAPA CONTRARIAN ANTI-MANIPULACION (doctorado OTC):
//   tras el filtro estructural, ContrarianScoring ajusta el
//   score segun trampas del broker (Trap Index por mechas,
//   fakeouts en S/R, reversal ratio), masa obvia (senal que
//   todos ven) y order flow inferido (proxy por rango, el bot
//   lee pixeles: NO hay volumen real). Fakeout A FAVOR = bonus
//   CONTRARIAN; masa obvia CON trampa en contra = BLOQUEO.
// v4.4.0: UMBRAL DE CONFLUENCIA. El score mide el REPARTO de
//   votos (ganador / total), no cuantas fuentes votaron: 2 de 2
//   da 100%. Por eso una senal con menos de FILTER.MIN_CONFLUENCIA
//   fuentes se BLOQUEA aunque su porcentaje sea alto. Un setup
//   contrarian PERFECTO baja el listado y queda exento de la
//   regla de los 90 (sus 6 condiciones ya son esa alineacion).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('scoring');

POScannerPRO.Scoring = (() => {
  const CFG = POScannerPRO.CONFIG;

  function evaluate(candles, ctx) {
    const P = POScannerPRO;
    const I = P.Indicators;
    const T = CFG.INDICATORS;
    const M = CFG.MODULES;
    const rsi = I.rsi(candles);
    const stochF = I.stochasticFull(candles, CFG.STOCH.K, CFG.STOCH.SLOWING, CFG.STOCH.D);
    const stoch = stochF.k;                    // %K suavizado (nivel)
    const mom = I.momentum(candles);
    const mf = T.MACD ? I.macdFull(candles) : null;
    const macd = mf ? mf.hist : I.macd(candles); // histograma (o simple)
    const cross = T.EMA_CROSS ?
      I.emaSmaCross(candles, CFG.CROSS.EMA_FAST, CFG.CROSS.SMA_SLOW) :
      { state: 'FLAT', crossed: null };
    const v = I.votes(candles);

    let callPts = 0, putPts = 0;
    // Fuentes que votaron a cada lado (para la confluencia)
    let callSrc = 0, putSrc = 0;

    // --- 1) RSI: sobreventa -> rebote CALL / sobrecompra -> PUT ---
    if (T.RSI) {
      if (rsi < 30) { callPts += 2; callSrc++; }
      else if (rsi > 70) { putPts += 2; putSrc++; }
      else if (rsi < 45) { callPts += 1; callSrc++; }
      else if (rsi > 55) { putPts += 1; putSrc++; }
    }
    // --- 2) Estocastico NIVEL: zona de sobreventa/sobrecompra ---
    if (T.STOCH) {
      if (stoch < 20) { callPts += 2; callSrc++; }
      else if (stoch > 80) { putPts += 2; putSrc++; }
    }
    // --- 3) Estocastico CRUCE %K/%D (14,3,3): giro temprano ---
    if (T.STOCH) {
      const upX = stochF.prevK <= stochF.prevD && stochF.k > stochF.d;
      const dnX = stochF.prevK >= stochF.prevD && stochF.k < stochF.d;
      if (upX && stochF.k < 30) { callPts += 2; callSrc++; }      // cruce en sobreventa
      else if (dnX && stochF.k > 70) { putPts += 2; putSrc++; }   // cruce en sobrecompra
      else if (stochF.k > stochF.d) { callPts += 1; callSrc++; }  // %K sobre %D
      else if (stochF.k < stochF.d) { putPts += 1; putSrc++; }
    }
    // --- 4) Momentum: signo directo ---
    if (T.MOMENTUM) {
      if (mom > 0) { callPts += 2; callSrc++; }
      else if (mom < 0) { putPts += 2; putSrc++; }
    }
    // --- 5) MACD HISTOGRAMA: direccion y giro del momentum ---
    if (T.MACD && mf) {
      if (mf.hist > 0 && mf.rising) { callPts += 1; callSrc++; }
      else if (mf.hist < 0 && !mf.rising) { putPts += 1; putSrc++; }
      else if (mf.hist < 0 && mf.rising) { callPts += 1; callSrc++; }  // se recupera
      else if (mf.hist > 0 && !mf.rising) { putPts += 1; putSrc++; }   // se agota
    }
    // --- 6) MACD CRUCE linea/senal: senal clasica fuerte ---
    if (T.MACD && mf) {
      if (mf.crossUp) { callPts += 2; callSrc++; }
      else if (mf.crossDown) { putPts += 2; putSrc++; }
    }
    // --- 7) CRUCE EMA 9 / SMA 10 (tus medias en PO) ---
    if (T.EMA_CROSS) {
      if (cross.crossed === 'CALL') { callPts += 2; callSrc++; }
      else if (cross.crossed === 'PUT') { putPts += 2; putSrc++; }
      else if (cross.state === 'UP') { callPts += 1; callSrc++; }
      else if (cross.state === 'DOWN') { putPts += 1; putSrc++; }
    }
    // --- 8) Estructura: predominio de color en ultimas 10 velas ---
    const rv = I.votes(candles.slice(-10));
    if (rv.call > rv.put) { callPts += 1; callSrc++; }
    else if (rv.put > rv.call) { putPts += 1; putSrc++; }

    // --- 9) PATRONES de velas: cada patron con sesgo suma 2 ---
    let patterns = [];
    if (M.PATTERNS) {
      patterns = P.PatternDetector.detect(candles);
      let pc = 0, pp = 0;
      patterns.forEach(p => {
        if (p.bias > 0) { callPts += 2; pc++; }
        else if (p.bias < 0) { putPts += 2; pp++; }
      });
      if (pc) callSrc++;
      if (pp) putSrc++;
    }

    // --- 11) TENDENCIA: se calcula ANTES de S/R para el filtro anti-cuchillo
    let trend = { trend: 'FLAT', strength: 0 };
    if (M.TREND) trend = P.TrendAnalyzer.analyze(candles);
    function trendDownStrong() { return trend.trend === 'DOWN' && trend.strength >= 50; }
    function trendUpStrong()   { return trend.trend === 'UP'   && trend.strength >= 50; }
    if (M.TREND) {
      // v3.4.0: tendencia fuerte pesa DOBLE (manda sobre osciladores)
      const w = trend.strength >= 50 ? 2 : 1;
      if (trend.trend === 'UP') { callPts += w; callSrc++; }
      else if (trend.trend === 'DOWN') { putPts += w; putSrc++; }
    }

    // --- 10) SOPORTE/RESISTENCIA: rebote esperado en el nivel ---
    let sr = { near: null, levels: [] };
    if (M.SR) {
      sr = P.SupportResistance.proximity(candles);
      // v3.4.0: el rebote en S/R solo vota si NO contradice una
      // tendencia fuerte (evita "atrapar el cuchillo que cae")
      const strongDown = trendDownStrong();
      const strongUp = trendUpStrong();
      if (sr.near && sr.near.type === 'S' && !strongDown) { callPts += 2; callSrc++; }
      if (sr.near && sr.near.type === 'R' && !strongUp) { putPts += 2; putSrc++; }
    }

    // --- 12) CONTEXTO MULTI-TIMEFRAME (v3.5.0): la tendencia de
    // los TFs MAYORES archivados filtra la senal (impulso + historial)
    let contexto = { dir: 'FLAT', used: [], score: 0 };
    if (ctx && ctx.asset && ctx.tfSec && P.CandleArchive) {
      try {
        contexto = P.CandleArchive.higherTrend(ctx.asset, ctx.tfSec);
        if (contexto.dir === 'UP') { callPts += Math.abs(contexto.score) >= 2 ? 2 : 1; callSrc++; }
        else if (contexto.dir === 'DOWN') { putPts += Math.abs(contexto.score) >= 2 ? 2 : 1; putSrc++; }
      } catch (e) { /* archivo aun vacio */ }
    }

    // --- REVERSION FUERTE (v3.4.0): detector multi-condicion ---
    // Cuenta condiciones de GIRO; con 3+ la reversion es FUERTE y
    // vota con peso doble (soluciona "reversion alcista con % bajo")
    let reversion = null;
    if (T.REVERSAL) {
      const last5 = candles.slice(-5);
      const last = candles[candles.length - 1];
      const prev = candles[candles.length - 2] || last;
      const avgBody = candles.slice(-14).reduce((a, c) =>
        a + Math.abs(c.close - c.open), 0) / Math.min(14, candles.length) || 1;
      // Condiciones de REVERSION ALCISTA.
      // v3.4.0 fix: exige EVIDENCIA del giro (vela verde reciente o
      // patron alcista); sin eso, una caida larga siempre "parece"
      // reversion por RSI bajo y es falso positivo.
      const hayGiroAlcista = last.dir === 'CALL' || patterns.some(p => p.bias > 0);
      const hayGiroBajista = last.dir === 'PUT' || patterns.some(p => p.bias < 0);
      let rc = 0;
      if (trend.trend === 'DOWN' || rv.put > rv.call) rc++;              // venia cayendo
      if (patterns.some(p => p.bias > 0)) rc++;                          // patron alcista
      if (last.dir === 'CALL' && Math.abs(last.close - last.open) > avgBody * 1.5) rc++; // vela verde fuerte
      if (rsi < 40) rc++;                                                // RSI en zona baja
      if (mf && mf.hist < 0 && mf.rising) rc++;                          // MACD girando arriba
      if (stochF.prevK <= stochF.prevD && stochF.k > stochF.d && stochF.k < 35) rc++; // cruce stoch bajo
      if (cross.crossed === 'CALL') rc++;                                // cruce EMA9/SMA10
      // Condiciones de REVERSION BAJISTA (espejo)
      let rp = 0;
      if (trend.trend === 'UP' || rv.call > rv.put) rp++;
      if (patterns.some(p => p.bias < 0)) rp++;
      if (last.dir === 'PUT' && Math.abs(last.close - last.open) > avgBody * 1.5) rp++;
      if (rsi > 60) rp++;
      if (mf && mf.hist > 0 && !mf.rising) rp++;
      if (stochF.prevK >= stochF.prevD && stochF.k < stochF.d && stochF.k > 65) rp++;
      if (cross.crossed === 'PUT') rp++;
      // Vela verde tras caida (ultima CALL y anterior PUT) como giro simple
      const giroVerde = last.dir === 'CALL' && prev.dir === 'PUT';
      const giroRoja  = last.dir === 'PUT' && prev.dir === 'CALL';
      if (giroVerde) rc++;
      if (giroRoja) rp++;

      if (hayGiroAlcista) {
        if (rc >= 3) { callPts += 4; callSrc++; reversion = 'ALCISTA FUERTE'; }
        else if (rc === 2) { callPts += 2; callSrc++; reversion = 'ALCISTA (moderada)'; }
      }
      if (hayGiroBajista) {
        if (rp >= 3) { putPts += 4; putSrc++; reversion = 'BAJISTA FUERTE'; }
        else if (rp === 2) { putPts += 2; putSrc++; reversion = 'BAJISTA (moderada)'; }
      }
    }

    const dir = callPts >= putPts ? 'CALL' : 'PUT';
    const total = callPts + putPts || 1;
    const winner = Math.max(callPts, putPts);
    const base = Math.round(winner / total * 100);

    // --- CONFLUENCIA: fuentes independientes que coinciden ---
    const agree = dir === 'CALL' ? callSrc : putSrc;
    let bonus = 0;
    if (agree >= 5) bonus = 15;
    else if (agree >= 4) bonus = 10;
    else if (agree >= 3) bonus = 5;
    let score = Math.min(97, base + bonus);

    // ========================================================
    // v4.1 FILTRO ESTRUCTURAL (casco anti contra-tendencia)
    // v4.2: BLOQUEO TOTAL (blocked = ESPERAR) + REGLA DE LOS 90
    // La votacion mide el IMPULSO local; esta capa mide la
    // ESTRUCTURA (tendencia + S/R + MTF). Una senal local
    // brillante que va contra la estructura es una trampa:
    // se TECHA el score y se BLOQUEA la entrada. Y un 90+
    // exige alineacion total (confluencia + aliado claro).
    // ========================================================
    const S = CFG.STRUCT || {};
    const CAP_TREND   = S.CAP_COUNTER_TREND   != null ? S.CAP_COUNTER_TREND   : 60;
    const CAP_SR      = S.CAP_COUNTER_SR      != null ? S.CAP_COUNTER_SR      : 60;
    const CAP_SR_STR  = S.CAP_COUNTER_SR_STRONG != null ? S.CAP_COUNTER_SR_STRONG : 55;
    const CAP_MTF     = S.CAP_COUNTER_MTF     != null ? S.CAP_COUNTER_MTF     : 55;
    const CAP_ALL     = S.CAP_ALL             != null ? S.CAP_ALL             : 45;
    const BRK_N       = S.BREAKOUT_CANDLES    != null ? S.BREAKOUT_CANDLES    : 3;

    let cap = 100;
    const reasons = [];
    let ruptura = null;   // 'R' o 'S' si el nivel cercano quedo ROTO

    // 1) CONTRA TENDENCIA FUERTE (la estructura manda sobre el impulso)
    if (trend.strength >= 50) {
      if (dir === 'CALL' && trend.trend === 'DOWN') {
        cap = Math.min(cap, CAP_TREND);
        reasons.push('CONTRA-TENDENCIA (mercado BAJISTA fuerte ' + trend.strength + '%)');
      } else if (dir === 'PUT' && trend.trend === 'UP') {
        cap = Math.min(cap, CAP_TREND);
        reasons.push('CONTRA-TENDENCIA (mercado ALCISTA fuerte ' + trend.strength + '%)');
      }
    }

    // 2) CONTRA S/R: CALL bajo RESISTENCIA o PUT sobre SOPORTE.
    //    EXCEPCION: ruptura confirmada = las ultimas BRK_N velas
    //    cierran MAS ALLA del nivel (ojo: Y invertida, menor Y =
    //    precio mayor; romper R al alza = cierres con Y < nivel).
    if (sr.near) {
      const lv = sr.near;
      const lastN = candles.slice(-BRK_N);
      if (dir === 'CALL' && lv.type === 'R') {
        const rota = lastN.length === BRK_N && lastN.every(c => c.close < lv.y);
        if (rota) { ruptura = 'R'; }
        else {
          const fuerte = lv.touches >= 3;
          cap = Math.min(cap, fuerte ? CAP_SR_STR : CAP_SR);
          reasons.push('bajo RESISTENCIA x' + lv.touches + ' (sin ruptura)');
        }
      } else if (dir === 'PUT' && lv.type === 'S') {
        const roto = lastN.length === BRK_N && lastN.every(c => c.close > lv.y);
        if (roto) { ruptura = 'S'; }
        else {
          const fuerte = lv.touches >= 3;
          cap = Math.min(cap, fuerte ? CAP_SR_STR : CAP_SR);
          reasons.push('sobre SOPORTE x' + lv.touches + ' (sin ruptura)');
        }
      }
    }

    // 3) CONTRA MTF: el contexto de TFs MAYORES archivados
    //    contradice la senal. Si aun no hay archivo, NO castiga
    //    (seria injusto: el contexto se construye escaneando).
    if (contexto.used && contexto.used.length && contexto.dir !== 'FLAT') {
      if (dir === 'CALL' && contexto.dir === 'DOWN') {
        cap = Math.min(cap, CAP_MTF);
        reasons.push('contra MTF (' + contexto.used.join(' ') + ' BAJISTA)');
      } else if (dir === 'PUT' && contexto.dir === 'UP') {
        cap = Math.min(cap, CAP_MTF);
        reasons.push('contra MTF (' + contexto.used.join(' ') + ' ALCISTA)');
      }
    }

    // Las TRES estructuras en contra a la vez = trampa total
    if (reasons.length >= 3) cap = Math.min(cap, CAP_ALL);

    const rawScore = score;
    let warning = null;
    if (score > cap) {
      score = cap;
      warning = 'RIESGO ALTO: senal ' + reasons.join(' + ') +
                '. Score real ' + rawScore + ' techado a ' + cap + '.';
    }
    if (ruptura) {
      warning = (warning ? warning + ' ' : '') +
        'Ruptura de ' + (ruptura === 'R' ? 'RESISTENCIA' : 'SOPORTE') +
        ' confirmada (' + BRK_N + ' cierres mas alla): techo de S/R anulado.';
    }

    // v4.2: BLOQUEO TOTAL de la senal techada. Ya no se muestra
    // como entrada: el panel dice ESPERAR, el overlay no dibuja
    // flecha y el historial no la registra. (Un aviso de RUPTURA
    // sin techo NO bloquea: es una confirmacion, no un riesgo.)
    let blocked = (score < rawScore);
    let blockReason = blocked ? 'estructura' : null;

    // ========================================================
    // v4.3 CAPA CONTRARIAN ANTI-MANIPULACION: ajusta el score
    // segun trampas del broker (Trap Index, fakeouts), masa
    // obvia y order flow inferido. Corre DESPUES del filtro
    // estructural: nunca desbloquea una contra-estructura y
    // puede anadir un bloqueo nuevo (masa obvia + trampa).
    // ========================================================
    // v4.3.1: las lineas de la capa contrarian son INFORMATIVAS
    // (bonus, castigos anti-masa) y viajan en contraNote. JAMAS
    // se mezclan en warning: el panel pinta warning como
    // "CONTRA-ESTRUCTURA - Riesgo Alto" y una senal contrarian
    // BUENA salia etiquetada como peligrosa (visto en video).
    let contra = null;
    let contraNote = null;
    if (CFG.CONTRARIAN && CFG.CONTRARIAN.ENABLED !== false &&
        P.ContrarianScoring) {
      try {
        contra = P.ContrarianScoring.adjust({
          dir: dir, score: score, agree: agree, candles: candles,
          trend: trend, sr: sr, patterns: patterns, blocked: blocked
        });
        score = contra.score;
        if (contra.bloqueoMasa && !blocked) {
          blocked = true;
          blockReason = 'masa';
        }
        if (contra.lines.length) contraNote = contra.lines.join(' | ');
      } catch (e) { /* capa contrarian desactivada o incompleta */ }
    }

    // ========================================================
    // v4.4 UMBRAL MINIMO DE CONFLUENCIA. Una senal sostenida por
    // pocas fuentes es ruido aunque el porcentaje salga alto: el
    // score mide el REPARTO de votos, no cuantos votaron. Con
    // menos de MIN_CONFLUENCIA fuentes se bloquea (ESPERAR).
    // Excepcion: un setup contrarian PERFECTO baja el listado a
    // MIN_CONFLUENCIA_PERFECTO (su evidencia es de otro tipo).
    // ========================================================
    const F = CFG.FILTER || {};
    const MIN_AGREE = F.MIN_CONFLUENCIA != null ? F.MIN_CONFLUENCIA : 7;
    const MIN_AGREE_PF = F.MIN_CONFLUENCIA_PERFECTO != null
      ? F.MIN_CONFLUENCIA_PERFECTO : 6;
    const perfecto = !!(contra && contra.perfecto);
    const needAgree = perfecto ? MIN_AGREE_PF : MIN_AGREE;
    if (!blocked && agree < needAgree) {
      blocked = true;
      blockReason = 'confluencia';
    }

    // v4.2: REGLA DE LOS 90 (senal IMPECABLE). Un 90+ solo se
    // permite con TODO alineado: confluencia alta (5+ fuentes) Y
    // al menos UN aliado estructural claro (tendencia a favor,
    // S/R a favor, patron alineado o MTF a favor). Si falta, la
    // senal es buena pero no impecable: se queda en 89.
    // v4.4: un SETUP CONTRARIAN PERFECTO queda exento: sus 6
    // condiciones YA son la alineacion que esta regla exige.
    let nota90 = null;
    const MIN90 = CFG.SCAN.SCORE_IMPECCABLE || 90;
    if (score >= MIN90 && !perfecto) {
      const aFavorTendencia =
        (dir === 'CALL' && trend.trend === 'UP'   && trend.strength >= 25) ||
        (dir === 'PUT'  && trend.trend === 'DOWN' && trend.strength >= 25);
      const aFavorSR = sr.near &&
        ((dir === 'CALL' && sr.near.type === 'S') ||
         (dir === 'PUT'  && sr.near.type === 'R'));
      const aFavorPatron = patterns.some(p =>
        dir === 'CALL' ? p.bias > 0 : p.bias < 0);
      const aFavorMTF = !!(contexto.used && contexto.used.length) &&
        ((dir === 'CALL' && contexto.dir === 'UP') ||
         (dir === 'PUT'  && contexto.dir === 'DOWN'));
      if (agree < 5 ||
          !(aFavorTendencia || aFavorSR || aFavorPatron || aFavorMTF)) {
        score = MIN90 - 1;   // 89: buena, no impecable
        nota90 = 'Para 90+ (IMPECABLE) se exige confluencia 5+ y un ' +
                 'aliado estructural (tendencia/S-R/patron/MTF a favor). ' +
                 'Confluencia actual: ' + agree + '/12.';
      }
    }

    // Calidad segun umbrales configurables (tras el techo)
    let quality = 'LOW';
    if (score >= CFG.SCAN.SCORE_HIGH) quality = 'HIGH';
    else if (score >= CFG.SCAN.SCORE_MIN_SIGNAL) quality = 'MEDIUM';

    return {
      dir: dir, score: score, quality: quality,
      confirmed: score >= CFG.SCAN.SCORE_MIN_SIGNAL,
      warning: warning,               // v4.1: texto de alerta o null
      rawScore: rawScore,             // v4.1: score antes del techo
      blocked: blocked,               // v4.2: true = ESPERAR (no entrar)
      blockReason: blockReason,       // v4.3: 'estructura' | 'masa' | null
      contrarian: !!(contra && contra.contrarian), // v4.3: fakeout a favor
      esObvia: !!(contra && contra.esObvia),       // v4.3: senal de masa
      contraNote: contraNote,         // v4.3.1: avisos contrarian (info)
      perfecto: perfecto,             // v4.4: setup contrarian perfecto
      agree: agree,                   // v4.4: fuentes que coincidieron
      note: nota90,                   // v4.2: por que no llego a 90+
      detail: {
        rsi: rsi.toFixed(1),
        stoch: stoch.toFixed(1), stochD: stochF.d.toFixed(1),
        momentum: mom.toFixed(2), macd: macd.toFixed(2),
        emaCross: cross.crossed ? ('CRUCE ' + cross.crossed) :
                  (cross.state === 'UP' ? 'EMA9>SMA10' :
                   cross.state === 'DOWN' ? 'EMA9<SMA10' : 'planas'),
        reversion: reversion,
        votosCALL: callPts, votosPUT: putPts, velas: v.total,
        confluencia: agree + '/12',
        patterns: patterns.map(p => p.name),
        srNear: sr.near ? (sr.near.type === 'S' ? 'SOPORTE' : 'RESISTENCIA') : '-',
        srLevels: sr.levels.length,
        trend: trend.trend,
        trendStrength: trend.strength,
        // v4.3: metricas anti-manipulacion para el panel
        trapIndex: contra ? contra.trapIndex : null,
        reversalRatio: contra ? contra.reversalRatio : null,
        fakeout: contra ? contra.fakeout : null,
        actividad: contra ? contra.actividad : null,
        contexto: contexto.used.length
          ? (contexto.dir === 'UP' ? 'ALCISTA' : contexto.dir === 'DOWN' ? 'BAJISTA' : 'mixto') +
            ' en ' + contexto.used.join(' ')
          : 'sin datos (escanea 1 vez en M1/M5 para crearlo)'
      }
    };
  }

  // VOTACION LIGERA (v3.5.0): solo para BACKTESTING masivo del
  // CandleArchive (rapida, sin patrones ni S/R). Devuelve
  // 'CALL' | 'PUT' | null (empate = sin senal).
  function quickEvaluate(candles) {
    const I = POScannerPRO.Indicators;
    if (!candles || candles.length < 40) return null;
    const rsi = I.rsi(candles);
    const sf = I.stochasticFull(candles, 14, 3, 3);
    const mom = I.momentum(candles);
    const mf = I.macdFull(candles);
    let c = 0, p = 0;
    if (rsi < 35) c += 2; else if (rsi > 65) p += 2;
    if (sf.prevK <= sf.prevD && sf.k > sf.d) c++;
    else if (sf.prevK >= sf.prevD && sf.k < sf.d) p++;
    if (mom > 0) c++; else if (mom < 0) p++;
    if (mf) { if (mf.hist > 0) c++; else if (mf.hist < 0) p++; }
    const rv = I.votes(candles.slice(-10));
    if (rv.call > rv.put) c++; else if (rv.put > rv.call) p++;
    if (c === p) return null;
    return c > p ? 'CALL' : 'PUT';
  }

  return { evaluate: evaluate, quickEvaluate: quickEvaluate };
})();
// [PO-PRO-OK:scoring]

'@
  'src/supportResistance.js' = @'
// ============================================================
// supportResistance.js - PRO v3.2.0  [FASE 2 - ACTIVO]
// Deteccion automatica de SOPORTES y RESISTENCIAS:
//   1) Busca "swing points" (maximos/minimos locales)
//   2) Agrupa niveles cercanos (clustering por tolerancia)
//   3) Un nivel con 2+ toques es VALIDO
//   4) proximity(): dice si el precio actual esta CERCA de un
//      nivel (zona de posible rebote)
// OJO coordenadas: Y invertida (menor Y = precio mayor).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('supportResistance');

POScannerPRO.SupportResistance = (() => {

  // Rango medio de vela (para tolerancias relativas al grafico)
  function avgRange(candles) {
    let s = 0;
    candles.forEach(c => { s += Math.max(1, c.low - c.high); });
    return s / candles.length;
  }

  // Niveles S/R con numero de toques
  function findLevels(candles) {
    const points = [];
    for (let i = 2; i < candles.length - 2; i++) {
      const c = candles[i];
      // Swing alto: precio maximo local (menor Y que sus vecinos)
      if (c.high <= candles[i-1].high && c.high <= candles[i-2].high &&
          c.high <= candles[i+1].high && c.high <= candles[i+2].high) {
        points.push({ y: c.high, type: 'R' });
      }
      // Swing bajo: precio minimo local (mayor Y que sus vecinos)
      if (c.low >= candles[i-1].low && c.low >= candles[i-2].low &&
          c.low >= candles[i+1].low && c.low >= candles[i+2].low) {
        points.push({ y: c.low, type: 'S' });
      }
    }

    // Clustering: fusionar puntos cercanos en niveles con "toques"
    const tol = avgRange(candles) * 0.6;
    const levels = [];
    points.forEach(p => {
      const found = levels.find(l => Math.abs(l.y - p.y) <= tol && l.type === p.type);
      if (found) {
        found.touches++;
        found.y = (found.y * (found.touches - 1) + p.y) / found.touches; // media
      } else {
        levels.push({ y: p.y, type: p.type, touches: 1 });
      }
    });
    // Solo niveles con 2+ toques son relevantes
    return levels.filter(l => l.touches >= 2)
                 .sort((a, b) => b.touches - a.touches);
  }

  // Precio actual (cierre de la ultima vela) cerca de algun nivel?
  function proximity(candles) {
    const levels = findLevels(candles);
    if (!levels.length) return { near: null, levels: [] };
    const last = candles[candles.length - 1];
    const price = last.close; // coordenada Y del cierre
    const zone = avgRange(candles) * 1.2; // zona de influencia del nivel
    let near = null;
    levels.forEach(l => {
      if (Math.abs(l.y - price) <= zone) near = l;
    });
    return { near: near, levels: levels };
  }

  return { findLevels: findLevels, proximity: proximity, ready: true };
})();
// [PO-PRO-OK:supportResistance]

'@
  'src/trapDetector.js' = @'
// ============================================================
// trapDetector.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Detecta TRAMPAS del broker OTC usando SOLO geometria de
// velas (el bot lee pixeles: NO hay volumen real ni libro
// de ordenes; todo es proxy honesto):
//   - TRAP INDEX: % de velas recientes con mechas largas
//     (mechas >= cuerpo). Mecha larga = el precio fue a un
//     sitio y lo trajeron de vuelta = barrido de stops.
//   - FAKEOUT en S/R: la ultima vela PINCHO el nivel con la
//     mecha pero cerro de vuelta dentro = ruptura falsa.
//     (Ojo: eje Y invertido, menor Y = precio mayor.)
//   - REVERSAL RATIO: de las veces que un nivel fue pinchado
//     en las ultimas velas, cuantas cerraron de vuelta dentro
//     (>70% = el broker revierte casi todas las rupturas).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('trapDetector');

POScannerPRO.TrapDetector = (() => {
  const CFG = POScannerPRO.CONFIG;

  // Mechas de una vela (en pixeles, Y invertida pero las
  // LONGITUDES son positivas igual)
  function wicks(c) {
    const hi = Math.min(c.open, c.close);   // techo del cuerpo (Y menor)
    const lo = Math.max(c.open, c.close);   // base del cuerpo (Y mayor)
    const upWick = Math.max(0, hi - c.high);  // mecha superior
    const dnWick = Math.max(0, c.low - lo);   // mecha inferior
    const body = Math.max(1, Math.abs(c.close - c.open));
    return { up: upWick, dn: dnWick, body: body, total: upWick + dnWick };
  }

  // TRAP INDEX: % de las ultimas N velas con mechas largas
  function trapIndex(candles) {
    const C = CFG.CONTRARIAN || {};
    const N = C.TRAP_WINDOW || 10;
    const RATIO = C.TRAP_WICK_RATIO || 1.0;
    const last = candles.slice(-N);
    if (!last.length) return { index: 0, longWicks: 0, n: 0 };
    let longW = 0;
    last.forEach(c => { if (wicks(c).total >= wicks(c).body * RATIO) longW++; });
    return { index: Math.round(longW / last.length * 100), longWicks: longW, n: last.length };
  }

  // FAKEOUT en la ULTIMA vela cerrada contra un nivel S/R:
  //  - Resistencia: mecha pincha POR ENCIMA (high con Y menor que
  //    el nivel) pero el cierre vuelve ABAJO -> trampa alcista,
  //    direccion contrarian PUT.
  //  - Soporte: mecha pincha POR DEBAJO pero cierra ARRIBA ->
  //    trampa bajista, direccion contrarian CALL.
  function detectarFakeout(candles, levels) {
    if (!candles || candles.length < 3 || !levels || !levels.length) return null;
    const c = candles[candles.length - 1];
    for (let i = 0; i < levels.length; i++) {
      const lv = levels[i];
      if (lv.type === 'R' && c.high < lv.y && c.close > lv.y) {
        return { tipo: 'FAKEOUT ALCISTA en RESISTENCIA', dir: 'PUT', level: lv };
      }
      if (lv.type === 'S' && c.low > lv.y && c.close < lv.y) {
        return { tipo: 'FAKEOUT BAJISTA en SOPORTE', dir: 'CALL', level: lv };
      }
    }
    return null;
  }

  // REVERSAL RATIO: % de pinchos de nivel (ultimas 30 velas) que
  // cerraron de vuelta dentro. Alto = rupturas falsas habituales.
  function reversalRatio(candles, levels) {
    if (!candles || candles.length < 6 || !levels || !levels.length) {
      return { ratio: null, rupturas: 0, revertidas: 0 };
    }
    const last = candles.slice(-30);
    let pinchos = 0, revertidos = 0;
    last.forEach(c => {
      levels.forEach(lv => {
        if (lv.type === 'R' && c.high < lv.y) {
          pinchos++;
          if (c.close > lv.y) revertidos++;
        } else if (lv.type === 'S' && c.low > lv.y) {
          pinchos++;
          if (c.close < lv.y) revertidos++;
        }
      });
    });
    if (!pinchos) return { ratio: null, rupturas: 0, revertidas: 0 };
    return { ratio: Math.round(revertidos / pinchos * 100),
             rupturas: pinchos, revertidas: revertidos };
  }

  // Analisis completo (lo usa contrarianScoring)
  function analyze(candles, sr) {
    const levels = (sr && sr.levels) || [];
    const ti = trapIndex(candles);
    const fk = detectarFakeout(candles, levels);
    const rr = reversalRatio(candles, levels);
    return {
      trapIndex: ti.index, longWicks: ti.longWicks, n: ti.n,
      fakeout: fk,
      reversalRatio: rr.ratio, rupturas: rr.rupturas, revertidas: rr.revertidas
    };
  }

  return { analyze: analyze, trapIndex: trapIndex,
           detectarFakeout: detectarFakeout, reversalRatio: reversalRatio };
})();
// [PO-PRO-OK:trapDetector]

'@
  'src/trendAnalyzer.js' = @'
// ============================================================
// trendAnalyzer.js - PRO v3.2.0  [FASE 2 - ACTIVO]
// Analisis de tendencia y estructura de mercado:
//   1) EMA20 vs EMA50 sobre cierres -> direccion de tendencia
//   2) Estructura: cuenta altos/bajos ascendentes (HH/HL) o
//      descendentes (LH/LL) en las ultimas velas
// Devuelve: { trend: 'UP'|'DOWN'|'FLAT', strength: 0-100 }
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('trendAnalyzer');

POScannerPRO.TrendAnalyzer = (() => {

  function analyze(candles) {
    if (!candles || candles.length < 22) {
      return { trend: 'FLAT', strength: 0 };
    }
    const I = POScannerPRO.Indicators;
    const closes = candles.map(c => -c.close); // Y invertida -> "precio"

    // 1) Cruce de medias: EMA20 sobre EMA50
    const e20 = I.ema(closes.slice(-40), 20);
    const e50 = I.ema(closes, Math.min(50, closes.length - 1));
    let trend = 'FLAT';
    if (e20 > e50) trend = 'UP';
    else if (e20 < e50) trend = 'DOWN';

    // 2) Estructura: ultimas 12 velas, pendiente de maximos y minimos
    const win = candles.slice(-12);
    const firstH = -win[0].high, lastH = -win[win.length - 1].high;
    const firstL = -win[0].low,  lastL = -win[win.length - 1].low;
    let struct = 0; // +1 estructura alcista / -1 bajista
    if (lastH > firstH && lastL > firstL) struct = 1;   // HH + HL
    else if (lastH < firstH && lastL < firstL) struct = -1; // LH + LL

    // Fuerza: separacion relativa de las EMAs (0-100)
    const sep = Math.abs(e20 - e50) / (Math.abs(e50) || 1) * 100;
    const strength = Math.min(100, Math.round(sep * 10));

    // Si estructura contradice a las EMAs, la tendencia es debil
    if ((trend === 'UP' && struct < 0) || (trend === 'DOWN' && struct > 0)) {
      return { trend: 'FLAT', strength: Math.round(strength / 2) };
    }
    return { trend: trend, strength: strength };
  }

  return { analyze: analyze, ready: true };
})();
// [PO-PRO-OK:trendAnalyzer]

'@
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$ok = 0; $bad = @()
foreach ($k in $files.Keys) {
  $p = Join-Path $base $k
  $d = Split-Path $p -Parent
  if (!(Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  [System.IO.File]::WriteAllText($p, $files[$k], $utf8)
  # verificacion byte a byte
  $read = [System.IO.File]::ReadAllText($p)
  if ($read -eq $files[$k]) { $ok++ } else { $bad += $k }
}

# verificacion de sellos de integridad
$sealed = 0
foreach ($k in $files.Keys) {
  if ($k -like '*.js' -or $k -like '*.css') {
    $p = Join-Path $base $k
    $t = [System.IO.File]::ReadAllText($p)
    if ($t -match '\[PO-PRO-OK:[a-zA-Z.-]+\]') { $sealed++ }
  }
}

Write-Host ''
if ($bad.Count -eq 0) {
  Write-Host ('INSTALACION PERFECTA: ' + $ok + '/' + $files.Count + ' archivos verificados, ' + $sealed + ' sellos OK') -ForegroundColor Green
} else {
  Write-Host ('ERRORES en: ' + ($bad -join ', ')) -ForegroundColor Red
}
Write-Host 'Carpeta:' $base
Write-Host 'Ahora ve a chrome://extensions y Carga sin empaquetar esa carpeta.'
