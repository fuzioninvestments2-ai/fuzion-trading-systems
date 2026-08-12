"""
tests/test_panel_data.py (fuzion_fx)
====================================
Valida la capa de datos del tablero: win-rate REAL por bot (sin contar NULAS),
pagos con marca de filtro, y ultimas transacciones ordenadas. SIN red (sqlite
temporal).
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                      # noqa: E402
from collector.candle_store import CandleStore                   # noqa: E402
from dashboard import panel_data                                 # noqa: E402


def _db(nombre):
    d = tempfile.mkdtemp()
    return os.path.join(d, nombre)


def test_winrate_bot_no_cuenta_nulas() -> None:
    db = _db("f1_memory.db")
    st = ResultsStore(db)
    a = st.save_signal({"pair": "EUR/USD", "timeframe": "1m", "direction": "CALL",
                        "setup_id": "s", "confirmations": 3, "price": 1.1, "atr": 0})
    b = st.save_signal({"pair": "EUR/USD", "timeframe": "1m", "direction": "PUT",
                        "setup_id": "s", "confirmations": 3, "price": 1.1, "atr": 0})
    c = st.save_signal({"pair": "EUR/USD", "timeframe": "1m", "direction": "CALL",
                        "setup_id": "s", "confirmations": 3, "price": 1.1, "atr": 0})
    st.save_signal({"pair": "EUR/USD", "timeframe": "1m", "direction": "CALL",
                    "setup_id": "s", "confirmations": 3, "price": 1.1, "atr": 0})  # pend
    st.resolve_signal(a, "win", 8)
    st.resolve_signal(b, "loss", -10)
    st.resolve_signal(c, "NULL", 0)
    st.close()
    r = panel_data.winrate_bot("f1_m1", db=db)
    assert r["emitidas"] == 4 and r["wins"] == 1 and r["losses"] == 1
    assert r["nulas"] == 1 and r["pendientes"] == 1
    assert r["win_pct"] == 50.0                 # 1/(1+1); la NULA no cuenta


def test_pagos_marca_filtro() -> None:
    db = _db("po_candles.db")
    s = CandleStore(db)
    s.upsert_payout("GBP/JPY", 79.0, 1000)
    s.upsert_payout("EUR/USD", 67.0, 1000)
    s.close()
    ps = panel_data.pagos(db_candles=db, min_pct=72.0)
    assert ps[0]["pair"] == "GBP/JPY" and ps[0]["pasa"] is True     # desc + pasa
    assert ps[1]["pair"] == "EUR/USD" and ps[1]["pasa"] is False


def test_resumen_general_estructura() -> None:
    # Con bases inexistentes no debe romper: todo vacio pero con las claves.
    r = panel_data.resumen_general(now_ts=1000)
    for k in ("ts", "bots", "global", "pagos", "transacciones", "procesos", "noticias"):
        assert k in r
    assert len(r["bots"]) == 4


def _run_all() -> None:
    tests = [test_winrate_bot_no_cuenta_nulas, test_pagos_marca_filtro,
             test_resumen_general_estructura]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
