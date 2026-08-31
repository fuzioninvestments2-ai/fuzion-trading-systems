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
  // ============================================================
  // TIMEFRAME DEL GRAFICO - v4.4.3 ANCLADO AL CHIP
  // Antes se buscaba el primer token tipo M30 en TODO el texto de
  // la pagina. PO lista los timeframes en menus y en tooltips, asi
  // que ganaba cualquiera: un grafico S10 se leia como M30, y con
  // tfSec=1800 el archivo de velas se redondeaba a una rejilla de
  // media hora, se sobrescribia a si mismo (no crecia) y el
  // contexto MTF y el backtest salian de una serie falsa.
  // Ahora se busca el CHIP activo junto al selector de par: un
  // elemento pequeno, en la zona superior-izquierda del grafico,
  // cuyo texto es EXACTAMENTE un timeframe. Se prefiere el que
  // tiene fondo pintado (el chip activo va resaltado).
  // ============================================================
  function findTimeframe() {
    const keys = Object.keys(CFG.TF_SECONDS);
    let conFondo = null, conFondoArea = Infinity;
    let sinFondo = null, sinFondoArea = Infinity;
    document.querySelectorAll('span, div, button, a, li').forEach(el => {
      if (el.closest && el.closest('#po-pro-panel')) return;
      if (el.children.length) return;                  // solo hojas
      const t = (el.textContent || '').trim();
      if (keys.indexOf(t) < 0) return;
      let r;
      try { r = el.getBoundingClientRect(); } catch (e) { return; }
      if (!r || r.width <= 0 || r.height <= 0) return;
      if (r.left > innerWidth * 0.6) return;           // zona del grafico
      if (r.top < 0 || r.top > innerHeight * 0.45) return;
      const area = r.width * r.height;
      if (area > 4000) return;                         // no es un chip
      if (bgPintado(el).bg) {
        if (area < conFondoArea) { conFondoArea = area; conFondo = t; }
      } else if (area < sinFondoArea) { sinFondoArea = area; sinFondo = t; }
    });
    return conFondo || sinFondo;
  }

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
    // v4.4.3: primero el chip del grafico; el barrido del texto
    // completo queda solo como ultimo recurso (elegia mal).
    const tf = findTimeframe() ||
      (bodyText.match(/\b(S5|S10|S15|S30|M1|M2|M3|M5|M15|M30|H1|H2|H4|D1)\b/) || [null])[0];
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
            'coinciden. El ' + r.rawScore + '% mide el reparto de votos, no ' +
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
        ? 'ESPERAR: senal bloqueada por ' +
          (r.blockReason === 'masa' ? 'masa obvia + trampa'
           : r.blockReason === 'confluencia' ? 'confluencia insuficiente'
           : 'contra-estructura') + ', sin entrada'
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
           findTimeframe: findTimeframe,
           axisScale: axisScale, priceFromY: priceFromY,
           priceFromCandle: priceFromCandle,
           findTradeTime: findTradeTime };
})();
// [PO-PRO-OK:panel]
