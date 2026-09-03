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
    // v4.4.4: RATIO de linea. Las medias moviles de PO son ROJA y
    // VERDE LIMA, los mismos colores que las velas, y son CONTINUAS:
    // en el hueco entre dos velas la unica cosa coloreada es la
    // media. Como es del mismo color y cae a la misma altura, el
    // agrupador la tomaba por continuacion de la vela y pegaba una
    // vela con la siguiente, y con la siguiente... hasta formar un
    // bloque mas ancho que MAX_WIDTH_PX que luego se descartaba
    // entero. Con el grafico AMPLIADO (velas anchas) esto se comia
    // casi toda la lectura: el usuario veia "4 velas / 17513 px".
    // Ahora una columna cuyo tramo es MUCHO mas bajo que la vela en
    // curso corta el grupo en vez de alargarlo.
    const LINE_RATIO = C.LINE_RATIO != null ? C.LINE_RATIO : 0.35;
    for (const col of columns) {
      if (col) {
        const cMin = col.rows[0], cMax = col.rows[col.rows.length - 1];
        const colH = cMax - cMin + 1;
        if (cur) {
          const curH = Math.max(6, cur.maxY - cur.minY);
          if (colH < Math.max(4, curH * LINE_RATIO)) {
            flush();                     // columna de linea: separa velas
          } else {
            const tol = Math.max(10, curH * 0.6);
            const mismaZona = cMin <= cur.maxY + tol && cMax >= cur.minY - tol;
            if (col.dir !== cur.dir || !mismaZona) flush();
          }
        }
        if (!cur) cur = { dir: col.dir, cols: [], minY: cMin, maxY: cMax };
        cur.cols.push(col);
        if (cMin < cur.minY) cur.minY = cMin;
        if (cMax > cur.maxY) cur.maxY = cMax;
        gap = 0;
      } else if (cur && ++gap > C.MAX_GAP_PX) flush();
    }
    flush();

    // 2b) v4.4.4: quitar los grupos que son TROZOS DE LINEA. Tras
    //     cortar por altura quedan restos de la media movil (grupos
    //     de 2-5 px de alto) junto a las velas (decenas de px).
    //     Se buscan DOS POBLACIONES: se ordenan las alturas y se
    //     corta por el SALTO relativo mas grande. Solo se corta si
    //     ese salto es de 3x o mas, es decir, si de verdad hay dos
    //     cosas distintas; entre velas de tamanos variados los
    //     saltos son suaves y no se toca nada.
    //     Se usa el salto y no la mediana porque los fragmentos de
    //     linea pueden ser casi la mitad de los grupos y envenenan
    //     cualquier promedio (visto con medias gruesas y el grafico
    //     muy ampliado: 12 velas leidas como 26).
    if (groups.length >= 6) {
      const alt = groups.map(g => ({ g: g, h: g.maxY - g.minY + 1 }))
                        .sort((a, b) => a.h - b.h);
      let corteIdx = -1, mejorR = 1;
      for (let i = 0; i < alt.length - 3; i++) {   // dejar 3 grupos arriba
        const r = alt[i + 1].h / Math.max(1, alt[i].h);
        if (r > mejorR) { mejorR = r; corteIdx = i; }
      }
      if (corteIdx >= 0 && mejorR >= 3) {
        const corte = alt[corteIdx + 1].h;
        for (let i = groups.length - 1; i >= 0; i--) {
          if (groups[i].maxY - groups[i].minY + 1 < corte) groups.splice(i, 1);
        }
      }
    }

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
