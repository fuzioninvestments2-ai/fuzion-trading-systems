"""
tests/test_database.py
======================
Validacion de `src/persistence/database.py` (TAREA 3). SIN red.

PORQUE: la BD alimenta backtest y win-rate del filtro de proteccion; si el
esquema o el conteo de WIN/LOSS se rompe, las metricas mienten. Se prueba con
una BD temporal en disco (aislada) y datos deterministas.
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.persistence.database import Database, WIN, LOSS, PENDING  # noqa: E402


def _db() -> Database:
    """BD temporal aislada (se borra al terminar el proceso de test)."""
    ruta = os.path.join(tempfile.mkdtemp(), "test.db")
    return Database(ruta)


def test_velas_ida_y_vuelta() -> None:
    db = _db()
    velas = [{"timestamp": 1000 + i, "open": 1.0, "high": 1.1, "low": 0.9,
              "close": 1.05, "volume": 10} for i in range(5)]
    n = db.save_candles("EURUSD", "1m", velas)
    assert n == 5
    df = db.get_candles("EURUSD", "1m")
    assert len(df) == 5
    # Orden cronologico: el primer ts debe ser el menor.
    assert df["timestamp"].iloc[0] < df["timestamp"].iloc[-1]
    db.close()


def test_senales_y_win_rate() -> None:
    db = _db()
    # 3 WIN y 1 LOSS en EURUSD/1m -> win-rate 0.75. 1 PENDING no cuenta.
    ids = []
    for i in range(4):
        sid = db.save_signal("EURUSD", "1m", "CALL", 92.0, 96.0,
                             ts_created=1000 + i)
        ids.append(sid)
    db.resolve_signal(ids[0], WIN, 2000)
    db.resolve_signal(ids[1], WIN, 2001)
    db.resolve_signal(ids[2], WIN, 2002)
    db.resolve_signal(ids[3], LOSS, 2003)
    db.save_signal("EURUSD", "1m", "PUT", 91.0, 95.0, ts_created=1500)  # PENDING

    wr = db.win_rate("EURUSD", "1m")
    assert wr["wins"] == 3 and wr["losses"] == 1 and wr["total"] == 4
    assert wr["win_rate"] == 0.75

    # La PENDING sigue pendiente y aparece en pending_signals.
    pend = db.pending_signals()
    assert len(pend) == 1 and pend[0]["direction"] == "PUT"
    db.close()


def test_metricas_y_por_par() -> None:
    db = _db()
    a = db.save_signal("EURUSD", "1m", "CALL", 90.0, 95.0, 1)
    b = db.save_signal("GBPUSD", "5m", "PUT", 94.0, 97.0, 2)
    db.resolve_signal(a, WIN, 10)
    db.resolve_signal(b, LOSS, 11)
    db.save_signal("USDJPY", "1m", "CALL", 93.0, 96.0, 3)   # PENDING

    m = db.performance_metrics()
    assert m["total_signals"] == 3
    assert m["wins"] == 1 and m["losses"] == 1 and m["pending"] == 1
    assert m["resolved"] == 2 and m["win_rate"] == 0.5

    por_par = db.win_rate_by_pair()
    pares = {(p["asset"], p["timeframe"]): p for p in por_par}
    assert pares[("EURUSD", "1m")]["win_rate"] == 1.0
    assert pares[("GBPUSD", "5m")]["win_rate"] == 0.0
    # USDJPY es PENDING: no aparece en el desglose de resueltas.
    assert ("USDJPY", "1m") not in pares
    db.close()


def test_result_invalido_lanza() -> None:
    db = _db()
    sid = db.save_signal("EURUSD", "1m", "CALL", 90.0, 95.0, 1)
    try:
        db.resolve_signal(sid, PENDING, 10)   # PENDING no es resolucion valida
        raise AssertionError("deberia haber lanzado ValueError")
    except ValueError:
        pass
    db.close()


def _run_all() -> None:
    tests = [test_velas_ida_y_vuelta, test_senales_y_win_rate,
             test_metricas_y_por_par, test_result_invalido_lanza]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
