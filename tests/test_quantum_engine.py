"""
tests/test_quantum_engine.py
============================
Valida la fachada `src/core/quantum_engine.py` (FASE 2). SIN red.

PORQUE: la fachada debe exponer EXACTAMENTE el motor real, sin alterar
resultados. Se comprueba que los simbolos son los mismos objetos que en
`bot.cuantico` y que `evaluate` coincide con `validate_signal_90`.
"""

from __future__ import annotations

import os
import sys
from typing import Dict

import numpy as np
import pandas as pd

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from bot import cuantico as q                       # noqa: E402
from src.core import quantum_engine as qe           # noqa: E402


def _frame(trend: int, n: int = 60) -> pd.DataFrame:
    idx = np.arange(n)
    close = 1.10 + trend * 0.0004 * idx
    op = close - trend * 0.0002
    high = np.maximum(op, close) + 0.00008
    low = np.minimum(op, close) - 0.00008
    return pd.DataFrame({"open": op, "high": high, "low": low,
                         "close": close, "volume": np.full(n, 1000.0)})


def _frames(trend: int) -> Dict[int, pd.DataFrame]:
    return {tf: _frame(trend) for tf in q.TIMEFRAMES_9}


def test_reexporta_mismos_objetos() -> None:
    # Deben ser el MISMO objeto (no copias): la fachada no altera nada.
    assert qe.validate_signal_90 is q.validate_signal_90
    assert qe.calculate_quantum_probability is q.calculate_quantum_probability
    assert qe.PROB_MIN == q.PROB_MIN == 90.0
    assert qe.CONV_MIN == q.CONV_MIN == 90.0
    assert qe.TIMEFRAMES_9 == q.TIMEFRAMES_9


def test_evaluate_coincide_con_motor() -> None:
    frames = _frames(+1)
    a = qe.evaluate(frames, payout=92, hora_utc=14)
    b = q.validate_signal_90(frames, payout=92, hora_utc=14)
    assert a["operar"] == b["operar"] is True
    assert a["direccion"] == b["direccion"] == "CALL"
    assert a["probabilidad"] == b["probabilidad"]


def _run_all() -> None:
    tests = [test_reexporta_mismos_objetos, test_evaluate_coincide_con_motor]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
