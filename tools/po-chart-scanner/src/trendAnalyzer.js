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
