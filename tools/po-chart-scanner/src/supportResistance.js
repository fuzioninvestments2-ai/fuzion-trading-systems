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
