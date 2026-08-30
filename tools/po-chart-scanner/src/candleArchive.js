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
