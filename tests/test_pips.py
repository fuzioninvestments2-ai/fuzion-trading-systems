"""
tests/test_pips.py
==================
Valida `src/indicators/pips.py` (conversion precio->pips). SIN red.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.indicators import pips   # noqa: E402


def test_pip_size() -> None:
    assert pips.pip_size("EURUSD_otc") == 0.0001
    assert pips.pip_size("EURUSD") == 0.0001
    assert pips.pip_size("USDJPY") == 0.01           # JPY -> 0.01
    assert pips.pip_size("GBPJPY_otc") == 0.01
    # No-FX -> None (sin pip estandar).
    assert pips.pip_size("BTCUSD_otc") is None       # BTC no es divisa ISO
    assert pips.pip_size("#AAPL_otc") is None
    assert pips.pip_size("XAUUSD") is None            # oro


def test_to_pips() -> None:
    # 0.0012 en un major = 12 pips.
    assert pips.to_pips(0.0012, "EURUSD") == 12.0
    # 0.12 en un par JPY = 12 pips.
    assert pips.to_pips(0.12, "USDJPY") == 12.0
    assert pips.to_pips(0.0012, "BTCUSD_otc") is None


def test_atr_pips() -> None:
    # Rango constante de 0.0010 -> ATR 0.0010 -> 10 pips en un major.
    high = np.array([1.1010] * 6)
    low = np.array([1.1000] * 6)
    close = np.array([1.1005] * 6)
    assert pips.atr_pips(high, low, close, "EURUSD", period=3) == 10.0
    # Par no-FX -> None.
    assert pips.atr_pips(high, low, close, "BTCUSD_otc") is None


def test_nearest_sr_distance_pips() -> None:
    levels = {"soportes": [1.0990], "resistencias": [1.1020, 1.1050]}
    # Precio 1.1005: soporte a 15 pips, resistencia a 15 pips -> 15.
    assert pips.nearest_sr_distance_pips(1.1005, levels, "EURUSD") == 15.0
    # Sin niveles -> None.
    assert pips.nearest_sr_distance_pips(1.1005, {"soportes": [], "resistencias": []},
                                         "EURUSD") is None
    # No-FX -> None.
    assert pips.nearest_sr_distance_pips(1.1005, levels, "BTCUSD_otc") is None


def _run_all() -> None:
    tests = [test_pip_size, test_to_pips, test_atr_pips, test_nearest_sr_distance_pips]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
