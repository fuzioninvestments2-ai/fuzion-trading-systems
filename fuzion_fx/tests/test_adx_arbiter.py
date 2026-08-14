"""
tests/test_adx_arbiter.py (fuzion_fx)
=====================================
Valida el arbitro ADX: tendencia limpia -> ADX alto -> modo Slide (tendencia pesa
mas que reversion); ruido lateral -> ADX bajo -> modo Oscillate (reversion pesa
mas). Y que los pesos de la tabla del doc fuente son los correctos. SIN red.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import adx_arbiter as A                               # noqa: E402


def _velas(close):
    close = np.asarray(close, float)
    o = np.concatenate([[close[0]], close[:-1]])
    h = np.maximum(o, close) * 1.0002
    l = np.minimum(o, close) * 0.9998
    return {"open": list(o), "high": list(h), "low": list(l), "close": list(close)}


def test_tendencia_da_adx_alto_y_slide() -> None:
    a = A.arbitrar(_velas(np.linspace(1.10, 1.13, 120)))
    assert a["adx"] > 25
    assert a["modo"] in ("slide", "slide_agresivo")
    # En Slide, la tendencia pesa mas que la reversion.
    assert a["pesos"]["ema"] > a["pesos"]["rsi"]


def test_rango_da_adx_bajo_y_oscillate() -> None:
    rng = np.random.RandomState(3)
    lateral = 1.1000 + rng.normal(0, 0.0002, 200)      # sin tendencia
    a = A.arbitrar(_velas(lateral))
    assert a["adx"] < 20
    assert a["modo"] == "oscillate"
    # En Oscillate, la reversion pesa mas que la tendencia.
    assert a["pesos"]["rsi"] > a["pesos"]["ema"]


def test_tabla_de_pesos_exacta() -> None:
    assert A.pesos("slide")["macd"] == 1.3 and A.pesos("slide")["bollinger"] == 0.7
    assert A.pesos("oscillate")["rsi"] == 1.3 and A.pesos("oscillate")["ema"] == 0.8
    assert A.pesos("transicion")["ema"] == 1.0
    for m in A.PESOS:
        assert A.pesos(m)["vwap"] == 1.0             # VWAP neutral siempre


def test_sin_datos_transicion() -> None:
    assert A.adx({"high": [1, 2], "low": [1, 1], "close": [1, 2]}) == 0.0
    assert A.modo(0.0) == "transicion"


def _run_all() -> None:
    tests = [test_tendencia_da_adx_alto_y_slide, test_rango_da_adx_bajo_y_oscillate,
             test_tabla_de_pesos_exacta, test_sin_datos_transicion]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
