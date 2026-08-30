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
