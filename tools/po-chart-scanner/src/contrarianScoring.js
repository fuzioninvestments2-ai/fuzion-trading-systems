// ============================================================
// contrarianScoring.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Capa de score ANTI-MANIPULACION (orquesta los otros 3
// modulos). Adaptacion del "calcularScoreAvanzado" del curso
// a la votacion real del bot: en vez de reconstruir el score
// desde 50, AJUSTA el score que ya calculo scoring.js:
//   PENALIZACIONES:
//   - Trap Index alto (>= TRAP_BLOCK): -TRAP_PENALTY
//     (mercado muy barrido, el broker esta activo).
//   - Fakeout EN CONTRA de la senal: -TRAP_PENALTY y aviso
//     (ej: senal CALL pero hubo fakeout alcista en resistencia).
//   - Senal OBVIA (masa): -OBVIO_PENALTY (lo que todos ven es
//     lo que el broker prepara para revertir).
//   - Order flow en contra: -FLOW_PENALTY.
//   BONUS:
//   - Fakeout A FAVOR de la senal: +FAKEOUT_BONUS y etiqueta
//     CONTRARIAN (ej: fakeout bajista en soporte + senal CALL =
//     operar contra la ruptura falsa, como el CASO 2 del examen).
//   BLOQUEO:
//   - MASA OBVIA + fakeout en contra = trampa de masa probable:
//     se bloquea igual que una contra-estructura (ESPERAR).
// NUNCA inventa datos: todo sale de la geometria de velas.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('contrarianScoring');

POScannerPRO.ContrarianScoring = (() => {
  const CFG = POScannerPRO.CONFIG;

  function adjust(o) {
    const C = CFG.CONTRARIAN || {};
    const P = POScannerPRO;
    const TRAP_BLOCK = C.TRAP_BLOCK != null ? C.TRAP_BLOCK : 70;
    const TRAP_PEN   = C.TRAP_PENALTY != null ? C.TRAP_PENALTY : 15;
    const OBVIO_PEN  = C.OBVIO_PENALTY != null ? C.OBVIO_PENALTY : 12;
    const FLOW_PEN   = C.FLOW_PENALTY != null ? C.FLOW_PENALTY : 8;
    const FK_BONUS   = C.FAKEOUT_BONUS != null ? C.FAKEOUT_BONUS : 10;

    // Sub-analisis (con guardas: si un modulo falta, no rompe nada)
    const trap = P.TrapDetector ? P.TrapDetector.analyze(o.candles, o.sr)
               : { trapIndex: 0, fakeout: null, reversalRatio: null };
    const flow = P.OrderFlowDetector ? P.OrderFlowDetector.analyze(o.candles)
               : { interpretacion: 'EQUILIBRIO', actividad: '-', actividadPct: 0 };
    const crowd = P.CrowdBehavior ? P.CrowdBehavior.analizar(
                    o.candles, o.dir, o.agree, o.sr, o.trend, o.patterns)
               : { esObvia: false, extendido: false, razon: '-' };

    let score = o.score;
    let contrarian = false;
    let bloqueoMasa = false;
    const lines = [];
    const yaBloqueada = !!o.blocked;   // v4.3.1: senal muerta, no tocar

    // 1) TRAP INDEX alto: mercado barrido, castigo general.
    // v4.3.1: si la senal YA esta bloqueada por estructura, no
    // se aplica ningun castigo ni bonus (solo se reportan las
    // metricas). Castigar una senal muerta es ruido doble.
    if (!yaBloqueada && trap.trapIndex >= TRAP_BLOCK) {
      score -= TRAP_PEN;
      lines.push('Trap Index ' + trap.trapIndex + '% (ALTA manipulacion): -' +
                 TRAP_PEN + ' pts');
    }

    // 2) FAKEOUT: trampa de nivel en la ultima vela cerrada
    if (trap.fakeout && !yaBloqueada) {
      if (trap.fakeout.dir === o.dir) {
        // La trampa va A FAVOR: el broker barrio y el precio
        // volvio = oportunidad contrarian (CASO 2 del examen)
        score += FK_BONUS;
        contrarian = true;
        lines.push('SENAL CONTRARIAN: ' + trap.fakeout.tipo +
                   ' a favor (operar contra la ruptura falsa): +' + FK_BONUS);
      } else {
        // La trampa va EN CONTRA: tu senal cayo en la trampa
        score -= TRAP_PEN;
        lines.push('TRAMPA EN CONTRA: ' + trap.fakeout.tipo +
                   ' contra tu ' + o.dir + ': -' + TRAP_PEN + ' pts');
        // 3) MASA OBVIA + trampa en contra = bloqueo total
        if (crowd.esObvia && C.MASA_BLOCK !== false) {
          bloqueoMasa = true;
          lines.push('BLOQUEADO: MASA OBVIA (' + crowd.razon +
                     ') con trampa del broker en contra');
        }
      }
    } else if (crowd.esObvia && !yaBloqueada) {
      // 4) Senal obvia sin trampa clara: castigo moderado
      score -= OBVIO_PEN;
      lines.push('Senal OBVIA (' + crowd.razon + '): la masa ya entro, -' +
                 OBVIO_PEN + ' pts');
    }

    // 5) ORDER FLOW en contra de la direccion
    if (flow.interpretacion === 'MAYORIA VENDEDORA' && o.dir === 'CALL') {
      score -= FLOW_PEN;
      lines.push('Order flow en contra (mayoria vendedora): -' + FLOW_PEN);
    } else if (flow.interpretacion === 'MAYORIA COMPRADORA' && o.dir === 'PUT') {
      score -= FLOW_PEN;
      lines.push('Order flow en contra (mayoria compradora): -' + FLOW_PEN);
    }

    score = Math.max(0, Math.min(97, score));
    return {
      score: score,
      contrarian: contrarian,
      bloqueoMasa: bloqueoMasa,
      trapIndex: trap.trapIndex,
      reversalRatio: trap.reversalRatio,
      fakeout: trap.fakeout ? trap.fakeout.tipo : null,
      actividad: flow.actividad,
      esObvia: crowd.esObvia,
      lines: lines
    };
  }

  return { adjust: adjust };
})();
// [PO-PRO-OK:contrarianScoring]
