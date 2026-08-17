"""
tests/test_reply_resultado.py (fuzion_fx)
=========================================
Valida que el RESULTADO pueda ir COMO RESPUESTA debajo de la señal:
 - ResultsStore guarda el tg_message_id de la señal y pending_older_than lo devuelve.
 - El notifier arma reply_to (message_id) en el payload de sendMessage.
SIN red.
"""
from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                     # noqa: E402
from telegram.notifier import TelegramNotifier                 # noqa: E402


def test_store_guarda_y_devuelve_message_id() -> None:
    st = ResultsStore(":memory:")
    sid = st.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                          "direction": "CALL", "setup_id": "x",
                          "entry_ts": 1060, "entry_show_ts": 1060})
    st.set_message_id(sid, 55555)
    pend = st.pending_older_than(2000)
    assert len(pend) == 1
    assert pend[0]["tg_message_id"] == 55555


def test_notifier_arma_reply_to() -> None:
    # Sin red: se intercepta _post y se revisa el payload.
    n = TelegramNotifier("TOKEN", "CANAL")
    capturado = {}

    def _fake_post(method, data, files=None):
        capturado["method"] = method
        capturado["data"] = data
        return {"ok": True, "result": {"message_id": 999}}

    n._post = _fake_post
    mid = n.send_text("hola", reply_to=55555)
    assert mid == 999
    assert capturado["data"]["reply_to_message_id"] == 55555


def test_notifier_sin_reply_no_pone_campo() -> None:
    n = TelegramNotifier("TOKEN", "CANAL")
    capturado = {}
    n._post = lambda m, d, files=None: (capturado.update(d) or
                                        {"ok": True, "result": {"message_id": 1}})
    n.send_text("hola")
    assert "reply_to_message_id" not in capturado


def _run_all() -> None:
    for fn in (test_store_guarda_y_devuelve_message_id, test_notifier_arma_reply_to,
               test_notifier_sin_reply_no_pone_campo):
        fn()
        print(f"  OK  {fn.__name__}")
    print("3 tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
