"""
tests/test_signal_engine.py (fuzion_fx)
=======================================
Valida SignalEngine: regla de confirmaciones (determinista) + casos reales. SIN red.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.signal_engine import SignalEngine, CALL, PUT, NEUTRAL   # noqa: E402

_IND = {"ema_fast": 9, "ema_slow": 21, "rsi_period": 14, "macd_fast": 12,
        "macd_slow": 26, "macd_signal": 9, "bb_period": 20, "bb_std": 2.0,
        "atr_period": 14}


class _FakeEngine(SignalEngine):
    """Engine con votos fijos para testear la regla de decision aislada."""
    def __init__(self, votos, min_conf):
        super().__init__(_IND, {"min_confirmations": min_conf})
        self._fake = votos

    def _votos(self, candles):
        return self._fake


def _candles(n=60):
    c = list(np.linspace(1.10, 1.10, n))    # planas; el resultado lo fija _votos
    return {"open": c, "high": c, "low": c, "close": c}


def test_call_con_3_confirmaciones() -> None:
    eng = _FakeEngine({"ema": 1, "macd": 1, "rsi": 1, "bollinger": -1}, 3)
    r = eng.analyze(_candles())
    assert r["signal"] == CALL and r["confirmations"] == 3
    assert r["setup_id"] == "CALL|ema,macd,rsi"     # ordenado alfabetico


def test_put_todos() -> None:
    eng = _FakeEngine({"ema": -1, "macd": -1, "rsi": -1, "bollinger": -1}, 3)
    r = eng.analyze(_candles())
    assert r["signal"] == PUT and r["confirmations"] == 4


def test_neutral_por_empate() -> None:
    eng = _FakeEngine({"ema": 1, "macd": 1, "rsi": -1, "bollinger": -1}, 3)
    assert eng.analyze(_candles())["signal"] == NEUTRAL   # 2 vs 2


def test_neutral_por_pocas_confirmaciones() -> None:
    eng = _FakeEngine({"ema": 1, "macd": 1, "rsi": 0, "bollinger": 0}, 3)
    assert eng.analyze(_candles())["signal"] == NEUTRAL   # solo 2 < 3


def test_engine_real_plano_es_neutral() -> None:
    # Con precios planos, ningun indicador confirma nada -> NEUTRAL.
    eng = SignalEngine(_IND, {"min_confirmations": 3})
    c = [1.1000] * 60
    r = eng.analyze({"open": c, "high": c, "low": c, "close": c})
    assert r["signal"] == NEUTRAL


def _run_all() -> None:
    tests = [test_call_con_3_confirmaciones, test_put_todos,
             test_neutral_por_empate, test_neutral_por_pocas_confirmaciones,
             test_engine_real_plano_es_neutral]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
