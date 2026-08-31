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

  // PRECIO REAL del eje (v3.5.1): PO dibuja una etiqueta con el
  // precio actual RESALTADA (fondo de color) pegada al eje
  // derecho del grafico. Evaluar el WIN/LOSS con este precio
  // real evita el bug del eje-Y (cambia con zoom/auto-scroll y
  // producia el 0% falso de acierto con 465L).
  function findCurrentPrice() {
    let best = null;
    document.querySelectorAll('span, div').forEach(el => {
      if (el.closest && el.closest('#po-pro-panel')) return;
      const t = (el.textContent || '').trim();
      if (!/^\d{1,7}\.\d{2,5}$/.test(t)) return;   // formato precio
      if (el.children.length) return;              // solo hojas
      const r = el.getBoundingClientRect();
      if (r.left < innerWidth * 0.55 || r.left > innerWidth * 0.95) return;
      // v3.5.2: el fondo pintado suele estar en el PADRE de la
      // etiqueta-pildora; subir hasta 3 niveles buscandolo
      let node = el, bg = '';
      for (let up = 0; up < 3 && node; up++) {
        const b = getComputedStyle(node).backgroundColor;
        if (b && b !== 'rgba(0, 0, 0, 0)' && b !== 'transparent') { bg = b; break; }
        node = node.parentElement;
      }
      if (bg) best = parseFloat(t);
    });
    return best;
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
          : '[X] BLOQUEADA: la votacion interna decia ' + r.dir + ' ' +
            r.rawScore + '/100, pero va CONTRA la estructura del mercado. NO entrar.\n')
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
      (blocked
        ? 'ESPERAR: senal bloqueada por contra-estructura, sin entrada'
        : (r.confirmed
          ? 'Entrada: al cierre de esta vela | Expira en: ' + exp.text + exp.warn
          : 'Espera: puntaje bajo, sin entrada')) + histLine);
    // Actualizar celda ACIERTO con las estadisticas del historial
    try {
      const s = POScannerPRO.History.stats();
      set('acc', s.total ? s.acc + '% (' + s.wins + 'W/' + s.losses + 'L' +
        (s.ties ? '/' + s.ties + 'E' : '') + ')' : '-');
    } catch (e) { /* historial aun no listo */ }
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
      const tc = H.byTag('CONTRARIAN'), tn = H.byTag('NORMAL');
      if (tc.n + tn.n > 0) {
        tagLine = '\nPor tipo -> Contrarian: ' + (tc.n ? tc.acc + '% en ' + tc.n : 'sin datos') +
                  ' | Normal: ' + (tn.n ? tn.acc + '% en ' + tn.n : 'sin datos');
      }
    } catch (e) { /* historial sin byTag aun */ }
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
           showHistory: showHistory, setVisible: setVisible,
           getTfSec: () => tfSec, getTradeSec: () => tradeSec,
           expiryInfo: expiryInfo, findCurrentPrice: findCurrentPrice,
           findTradeTime: findTradeTime };
})();
// [PO-PRO-OK:panel]
