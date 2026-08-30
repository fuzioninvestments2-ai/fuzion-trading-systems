// ============================================================
// crowdBehavior.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Deteccion de "MASA" (crowd behavior). ADAPTACION HONESTA:
// el bot NO puede leer el % real de traders de PO desde los
// pixeles de las velas, asi que la masa se INFIERE asi:
//   - SENAL OBVIA = la que "todos ven": confluencia muy alta
//     (6+ fuentes de voto) en un nivel claro (S/R con 2+
//     toques) o con patron fuerte. Si es obvia para el bot,
//     es obvia para la masa... y para el broker.
//   - MOVIMIENTO EXTENDIDO: el precio ya recorrio mucho en la
//     direccion de la senal (la masa entra tarde, por FOMO).
//   - CROWD LOSS RATE: se calcula de verdad con el HISTORIAL
//     del propio bot: % de senales OBVIAS archivadas que
//     perdieron. >60% = ir contra la masa tiene ventaja aqui.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('crowdBehavior');

POScannerPRO.CrowdBehavior = (() => {
  const CFG = POScannerPRO.CONFIG;

  // Movimiento neto reciente en "cuerpos" (cuanto recorrio ya)
  function extension(candles) {
    const last = candles.slice(-12);
    if (last.length < 3) return 0;
    const avgBody = candles.slice(-20).reduce((a, c) =>
      a + Math.abs(c.close - c.open), 0) / Math.min(20, candles.length) || 1;
    const neto = last[0].close - last[last.length - 1].close; // Y invertida:
    return neto / avgBody; // >0 = subio (Y baja), en unidades de cuerpo
  }

  // La senal es OBVIA (la ve todo el mundo)?
  // dir = direccion de la senal del bot; agree = confluencia (0-12)
  function analizar(candles, dir, agree, sr, trend, patterns) {
    const C = CFG.CONTRARIAN || {};
    const MIN_CONF = C.OBVIO_CONFLUENCIA || 6;
    const nivelClaro = !!(sr && sr.near && sr.near.touches >= 2);
    const patronFuerte = (patterns || []).some(p =>
      dir === 'CALL' ? p.bias > 0 : p.bias < 0);
    const ext = extension(candles);
    // La masa entra tarde: movimiento ya extendido (3+ cuerpos)
    // en la direccion de la senal.
    const extendido = (dir === 'CALL' && ext >= 3) || (dir === 'PUT' && ext <= -3);
    const esObvia = agree >= MIN_CONF && (nivelClaro || patronFuerte);
    const razones = [];
    if (agree >= MIN_CONF) razones.push('confluencia ' + agree + '/12');
    if (nivelClaro) razones.push('nivel claro x' + sr.near.touches);
    if (patronFuerte) razones.push('patron a favor');
    if (extendido) razones.push('movimiento ya extendido');
    return {
      esObvia: esObvia,
      extendido: extendido,
      direccionMasa: esObvia ? dir : null,  // la masa sigue lo obvio
      razon: razones.join(' + ') || 'senal no masiva'
    };
  }

  // CROWD LOSS RATE real: % de senales OBVIAS pasadas que perdieron
  // (usa el historial del propio bot; necesita muestra 10+)
  function crowdLossRate() {
    try {
      const H = POScannerPRO.History;
      if (!H || !H.lastItems) return { rate: null, n: 0 };
      const items = H.lastItems(100).filter(i =>
        i.obvia && (i.result === 'WIN' || i.result === 'LOSS'));
      const losses = items.filter(i => i.result === 'LOSS').length;
      if (items.length < 10) return { rate: null, n: items.length };
      return { rate: Math.round(losses / items.length * 100), n: items.length };
    } catch (e) { return { rate: null, n: 0 }; }
  }

  return { analizar: analizar, crowdLossRate: crowdLossRate,
           extension: extension };
})();
// [PO-PRO-OK:crowdBehavior]
