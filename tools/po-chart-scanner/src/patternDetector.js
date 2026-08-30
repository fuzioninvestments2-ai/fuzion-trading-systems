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
