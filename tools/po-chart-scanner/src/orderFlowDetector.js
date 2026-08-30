// ============================================================
// orderFlowDetector.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Inferencia de ORDER FLOW (presion compra/venta). ADAPTACION
// HONESTA: el bot lee PIXELES, no existe vela.volumen real en
// OTC de pantalla. El "volumen relativo" del doctorado se
// aproxima con el RANGO de la vela (high-low): una vela con
// rango 2x el promedio movio mucho precio = actividad alta.
//   - presionCompra/presionVenta: mismo algoritmo del curso,
//     usando rangoRelativo en vez de volumenRelativo.
//   - actividad (ALTA/MEDIA/BAJA): rango medio de las ultimas
//     5 velas vs las 15 anteriores (proxy de volumen anomalo).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('orderFlowDetector');

POScannerPRO.OrderFlowDetector = (() => {

  function rango(c) { return Math.max(1, c.low - c.high); } // px (Y invertida)

  // Presion de compra/venta inferida (proxy por rango)
  function inferirOrderFlow(candles) {
    const last = candles.slice(-10);
    if (last.length < 3) {
      return { presionCompra: 0, presionVenta: 0, ratio: 1,
               interpretacion: 'EQUILIBRIO' };
    }
    const prom = last.reduce((a, c) => a + rango(c), 0) / last.length || 1;
    let presionCompra = 0, presionVenta = 0;
    last.forEach(v => {
      const rel = rango(v) / prom;   // proxy de volumenRelativo
      if (v.dir === 'CALL') {        // vela alcista
        presionCompra += rel > 1.5 ? rel * 2 : 1;
      } else if (v.dir === 'PUT') {  // vela bajista
        presionVenta += rel > 1.5 ? rel * 2 : 1;
      }
    });
    const ratio = presionVenta > 0 ? presionCompra / presionVenta
                                   : (presionCompra > 0 ? 99 : 1);
    return {
      presionCompra: Math.round(presionCompra * 10) / 10,
      presionVenta: Math.round(presionVenta * 10) / 10,
      ratio: Math.round(ratio * 100) / 100,
      interpretacion: ratio > 1.5 ? 'MAYORIA COMPRADORA' :
                      ratio < 0.67 ? 'MAYORIA VENDEDORA' : 'EQUILIBRIO'
    };
  }

  // ACTIVIDAD (proxy de volumen): rango reciente vs rango previo
  function actividad(candles) {
    if (candles.length < 20) return { nivel: 'MEDIA', pct: 100 };
    const rec = candles.slice(-5).reduce((a, c) => a + rango(c), 0) / 5;
    const ant = candles.slice(-20, -5).reduce((a, c) => a + rango(c), 0) / 15 || 1;
    const pct = Math.round(rec / ant * 100);
    return { nivel: pct > 140 ? 'ALTA' : pct < 70 ? 'BAJA' : 'MEDIA', pct: pct };
  }

  function analyze(candles) {
    const flow = inferirOrderFlow(candles);
    const act = actividad(candles);
    return {
      presionCompra: flow.presionCompra,
      presionVenta: flow.presionVenta,
      ratio: flow.ratio,
      interpretacion: flow.interpretacion,
      actividad: act.nivel,        // ALTA / MEDIA / BAJA
      actividadPct: act.pct,
      proxy: true                  // recordatorio: sin volumen real
    };
  }

  return { analyze: analyze, inferirOrderFlow: inferirOrderFlow,
           actividad: actividad };
})();
// [PO-PRO-OK:orderFlowDetector]
