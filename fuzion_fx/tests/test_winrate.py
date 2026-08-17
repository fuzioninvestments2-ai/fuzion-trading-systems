"""
tests/test_winrate.py (fuzion_fx)
=================================
Valida el reporte de acierto real: lectura de signals, calculo de win_pct (ties no
cuentan) y break-even por pago. SIN red (sqlite temporal).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts import winrate                                     # noqa: E402


def _db_con(filas):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute("CREATE TABLE signals (timeframe TEXT, setup_id TEXT, "
                 "resolved INTEGER, result TEXT)")
    conn.executemany("INSERT INTO signals VALUES (?,?,1,?)", filas)
    conn.commit()
    conn.close()
    return tmp.name


def test_leer_y_tasa() -> None:
    p = _db_con([("1m", "A", "win"), ("1m", "A", "loss"), ("1m", "A", "win"),
                 ("1m", "A", "tie")])
    try:
        filas = winrate.leer_signals(p)
        assert len(filas) == 4
        w, l, t, pct = winrate._tasa(filas)
        assert (w, l, t) == (2, 1, 1)
        assert abs(pct - 66.6667) < 0.01                 # 2/3, ties fuera
    finally:
        os.unlink(p)


def test_break_even() -> None:
    assert abs(winrate.break_even(80) - 55.5556) < 0.01
    assert abs(winrate.break_even(100) - 50.0) < 0.01


def test_db_inexistente_no_revienta() -> None:
    assert winrate.leer_signals("/no/existe/x.db") == []


def _run_all() -> None:
    for fn in (test_leer_y_tasa, test_break_even, test_db_inexistente_no_revienta):
        fn()
        print(f"  OK  {fn.__name__}")
    print("3 tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
