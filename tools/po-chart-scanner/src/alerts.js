// ============================================================
// alerts.js - PRO v3.2.0  [FASE 4 - ACTIVO]
// Alerta sonora con Web Audio API (sin archivos externos):
//   CALL -> dos tonos ascendentes (ding-ding)
//   PUT  -> dos tonos descendentes
// Solo suena tras un clic del usuario (politica de Chrome OK).
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('alerts');

POScannerPRO.Alerts = (() => {
  let ctx = null;

  function ac() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function tone(freq, t0, dur, vol) {
    const c = ac(); if (!c) return;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = 'sine';
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, c.currentTime + t0);
    g.gain.exponentialRampToValueAtTime(vol, c.currentTime + t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + t0 + dur);
    o.connect(g); g.connect(c.destination);
    o.start(c.currentTime + t0);
    o.stop(c.currentTime + t0 + dur + 0.05);
  }

  // Beep de senal: CALL ascendente / PUT descendente
  function beep(dir) {
    const CFG = POScannerPRO.CONFIG;
    if (!CFG.ALERTS.SOUND) return;
    const v = CFG.ALERTS.VOLUME * 0.3;
    try {
      if (dir === 'CALL') { tone(660, 0, 0.12, v); tone(880, 0.14, 0.18, v); }
      else                { tone(880, 0, 0.12, v); tone(660, 0.14, 0.18, v); }
    } catch (e) { /* audio no disponible */ }
  }

  return { beep: beep, ready: true };
})();
// [PO-PRO-OK:alerts]
