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
