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
