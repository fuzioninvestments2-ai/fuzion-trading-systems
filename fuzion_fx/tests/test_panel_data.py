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


def _seed_candles(cdb, pair="EUR/USD", tf=60, n=120):
    s = CandleStore(cdb)
    for i in range(n):
        x = 1.10 + i * 0.0002                 # tendencia clara
        s.upsert_real_candle(pair, tf, i * tf, x, x + 0.0001, x - 0.0001, x + 0.00005, 3)
    s.upsert_payout(pair, 80.0, 1000)
    s.close()


def test_candles_json_devuelve_velas() -> None:
    cdb = _db("po_candles.db")
    _seed_candles(cdb)
    c = panel_data.candles_json("EUR/USD", 60, 50, db_candles=cdb)
    assert len(c["close"]) == 50 and "open" in c
    assert panel_data.candles_json("NADA/NADA", 60, 50, db_candles=cdb) == {}


def test_escaner_estructura_y_orden() -> None:
    cdb = _db("po_candles.db")
    _seed_candles(cdb, pair="EUR/USD", tf=60)
    rows = panel_data.escaner(60, db_candles=cdb)
    assert len(rows) == 22                          # los 22 pares
    for r in rows:
        for k in ("pair", "signal", "confirmations", "payout", "estado"):
            assert k in r
    # EUR/USD tiene velas -> se evalua (no 'sin datos') y va antes que los vacios.
    eur = next(r for r in rows if r["pair"] == "EUR/USD")
    assert eur["estado"] != "sin datos"
    assert rows[0]["estado"] != "sin datos"
    # 'sin datos' siempre al final.
    estados = [r["estado"] for r in rows]
    assert estados[-1] == "sin datos"


def _run_all() -> None:
    tests = [test_winrate_bot_no_cuenta_nulas, test_pagos_marca_filtro,
             test_resumen_general_estructura, test_candles_json_devuelve_velas,
             test_escaner_estructura_y_orden]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
