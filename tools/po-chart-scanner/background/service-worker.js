// ============================================================
// service-worker.js - PO Chart Scanner PRO v3.2.0
// FASE 1: lifecycle minimo + MOTOR 2: captura de pantalla.
// captureVisibleTab fotografia la pestana visible (funciona
// aunque el canvas sea WebGL o este protegido por CORS).
// ============================================================
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('[PO Scanner PRO] Instalado. Abre Pocket Option.');
  } else if (details.reason === 'update') {
    console.log('[PO Scanner PRO] Actualizado a v3.2.0');
  }
});

// MOTOR 2: el panel pide una captura de la pestana activa
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'PO_PRO_CAPTURE') return;
  const done = (resp) => { try { sendResponse(resp); } catch (e) { /* canal cerrado */ } };
  try {
    const winId = sender && sender.tab ? sender.tab.windowId : undefined;
    chrome.tabs.captureVisibleTab(winId, { format: 'png' }, (dataUrl) => {
      const err = chrome.runtime.lastError;
      if (err || !dataUrl) done({ ok: false, error: err ? err.message : 'sin imagen' });
      else done({ ok: true, dataUrl: dataUrl });
    });
  } catch (e) {
    done({ ok: false, error: e.message });
  }
  return true; // respuesta asincrona
});
// [PO-PRO-OK:service-worker]
