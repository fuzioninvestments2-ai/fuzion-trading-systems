// ============================================================
// history.js - PRO v4.3.0 CONTRARIAN  [FASE 4 - ACTIVO]
// Historial REAL de senales con estadisticas de acierto:
//   - Senal confirmada se guarda con precio de referencia Y
//     PLAZO (deadline = tu tiempo de expiracion de PO)
//   - WIN/LOSS solo se evalua cuando el plazo YA vencio
//   - UNIFICADO (manual + AUTO): una senal contraria cancela
//     la pendiente (no se contradicen)
// v3.5.2 - EVALUACION HONESTA (adios al 3% falso):
//   La v3.5.1 caia al respaldo de pixeles-Y cuando no leia el
//   precio del eje; como PO mantiene el precio actual siempre
//   en la misma zona vertical de pantalla, el "precio" apenas
//   cambiaba entre escaneos -> la comparacion estricta marcaba
//   LOSS casi siempre (3W/114L). Ahora:
//   1) Si hay precio REAL (DOM) en ambos lados: comparacion
//      directa; si no se movio -> EMPATE (PO devuelve la apuesta)
//   2) Si no hay precio real: comparar en la ESCALA UNIFICADA
//      del archivo de velas (mismo activo+TF, re-anclada):
//      cierre de la vela del momento de la senal vs cierre
//      de la vela actual. Y baja = precio sube.
//   3) Si ninguna fuente es confiable: la senal espera; pasado
//      el tiempo de gracia se marca SIN DATO (no cuenta).
//   JAMAS se evalua con pixeles-Y crudos de pantalla.
// v4.4: backtests() devuelve el acierto REAL separado en tres
//   categorias (contrarian / normal / total): el promedio unico
//   escondia que las NORMAL arrastran a las CONTRARIAN.
// v4.3: cada senal se etiqueta tag='CONTRARIAN'|'NORMAL' y con
//   obvia=true/false (senal de masa) -> estadisticas separadas
//   (byTag) y crowd loss rate real (crowdBehavior).
// Persistencia: localStorage (sobrevive a F5 y a reinicios).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('history');

POScannerPRO.History = (() => {
  const KEY = 'poscanner_pro_history_v3';
  const MAX_ITEMS = 100; // rotacion: conserva las ultimas 100 senales
  let items = [];
  load();

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      items = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(items)) items = [];
    } catch (e) { items = []; }
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(items.slice(-MAX_ITEMS))); }
    catch (e) { /* silencioso */ }
  }

  // Registrar una senal confirmada (manual o AUTO: mismo camino)
  function add(signal) {
    // UNIFICACION: cancelar pendientes CONTRARIAS del mismo activo
    let cancelled = false;
    items.forEach(it => {
      if (it.result === 'PENDING' && it.dir !== signal.dir &&
          it.asset === (signal.asset || '-')) {
        it.result = 'CANCELLED';
        cancelled = true;
      }
    });
    // No duplicar: si la ultima senal es igual y esta pendiente, ignorar
    const last = items[items.length - 1];
    if (!cancelled && last && last.result === 'PENDING' &&
        last.dir === signal.dir && last.asset === (signal.asset || '-')) return;
    items.push({
      time: new Date().toLocaleTimeString(),
      asset: signal.asset || '-',
      dir: signal.dir,               // CALL o PUT
      score: signal.score,
      quality: signal.quality,
      refPrice: signal.refPrice,     // precio REAL (o null si no se leyo)
      refReal: !!signal.refReal,     // v3.5.2: true = refPrice es real
      refT: signal.refT || Date.now(), // momento de la senal (ms)
      tfSec: signal.tfSec || 0,      // timeframe del grafico
      deadline: signal.deadline || 0,// plazo de expiracion (ms)
      expiryText: signal.expiryText || '',
      tag: signal.tag || 'NORMAL',   // v4.3: CONTRARIAN o NORMAL
      obvia: !!signal.obvia,         // v4.3: senal de masa (obvia)
      result: 'PENDING'
    });
    save();
  }

  // Decidir WIN/LOSS/EMPATE/SIN DATO de una senal vencida.
  // Devuelve null si aun no hay datos confiables (sigue PENDING).
  function judge(it, realPrice, now) {
    // 1) PRECIO REAL en ambos extremos: comparacion directa
    if (it.refReal && realPrice != null && typeof it.refPrice === 'number') {
      const d = realPrice - it.refPrice;
      const eps = Math.abs(it.refPrice) * 1e-9;
      if (Math.abs(d) <= eps) return 'EMPATE';
      if (it.dir === 'CALL') return d > 0 ? 'WIN' : 'LOSS';
      return d < 0 ? 'WIN' : 'LOSS';
    }
    // 2) ESCALA UNIFICADA del archivo de velas (espacio-Y):
    //    cierre de la vela de la senal vs cierre de la vela actual
    try {
      const A = POScannerPRO.CandleArchive;
      if (A && it.refT && it.tfSec) {
        const refC = A.closeAt(it.asset, it.tfSec, it.refT);
        const curC = A.lastClose(it.asset, it.tfSec);
        if (refC != null && curC != null) {
          const dy = curC - refC;          // Y: bajar = precio SUBE
          if (Math.abs(dy) < 0.5) return 'EMPATE';   // no se movio
          if (it.dir === 'CALL') return dy < 0 ? 'WIN' : 'LOSS';
          return dy > 0 ? 'WIN' : 'LOSS';
        }
      }
    } catch (e) { /* archivo no disponible */ }
    // 3) Sin datos confiables: esperar hasta agotar la gracia
    const GRACE = (POScannerPRO.CONFIG.HISTORY &&
                   POScannerPRO.CONFIG.HISTORY.GRACE_MS) || 300000;
    if (it.deadline && now - it.deadline > GRACE) return 'SIN DATO';
    return null;
  }

  // Evaluar pendientes YA VENCIDOS. realPrice = precio real del
  // eje (o null si no se pudo leer en este escaneo).
  function update(realPrice) {
    const now = Date.now();
    let changed = false;
    items.forEach(it => {
      if (it.result !== 'PENDING') return;
      if (it.deadline && now < it.deadline) return; // aun no expira
      const r = judge(it, realPrice, now);
      if (r) { it.result = r; changed = true; }
    });
    if (changed) save();
    return changed;
  }

  function stats() {
    const wins   = items.filter(i => i.result === 'WIN').length;
    const losses = items.filter(i => i.result === 'LOSS').length;
    const ties   = items.filter(i => i.result === 'EMPATE').length;
    const pend   = items.filter(i => i.result === 'PENDING').length;
    const canc   = items.filter(i => i.result === 'CANCELLED').length;
    const done = wins + losses;
    return {
      total: wins + losses + pend, wins: wins, losses: losses,
      ties: ties, pending: pend, cancelled: canc,
      acc: done ? Math.round(wins / done * 100) : 0
    };
  }

  // Acierto historico FILTRADO por calidad (HIGH/MEDIUM/LOW)
  function byQuality(q) {
    const its = items.filter(i => i.quality === q &&
      (i.result === 'WIN' || i.result === 'LOSS'));
    const w = its.filter(i => i.result === 'WIN').length;
    return { n: its.length, acc: its.length ? Math.round(w / its.length * 100) : null };
  }

  // v4.3: acierto FILTRADO por tipo (CONTRARIAN vs NORMAL)
  function byTag(tag) {
    const its = items.filter(i => (i.tag || 'NORMAL') === tag &&
      (i.result === 'WIN' || i.result === 'LOSS'));
    const w = its.filter(i => i.result === 'WIN').length;
    return { n: its.length, acc: its.length ? Math.round(w / its.length * 100) : null };
  }

  // v4.4: BACKTEST SEPARADO en tres categorias. "Backtest" aqui
  // significa el acierto REAL de las senales que este bot emitio
  // y que ya vencieron; no es una simulacion sobre el archivo de
  // velas (eso lo hace CandleArchive.backtest). Separarlos importa
  // porque el promedio total lo arrastran las senales NORMAL.
  function backtests() {
    const c = byTag('CONTRARIAN');
    const n = byTag('NORMAL');
    const done = items.filter(i => i.result === 'WIN' || i.result === 'LOSS');
    const w = done.filter(i => i.result === 'WIN').length;
    return {
      contrarian: c,
      normal: n,
      total: { n: done.length,
               acc: done.length ? Math.round(w / done.length * 100) : null }
    };
  }

  function clear() { items = []; save(); }

  function lastItems(n) { return items.slice(-(n || 8)).reverse(); }

  return { add: add, update: update, stats: stats, byQuality: byQuality,
           byTag: byTag, backtests: backtests,
           clear: clear, lastItems: lastItems, ready: true };
})();
// [PO-PRO-OK:history]
