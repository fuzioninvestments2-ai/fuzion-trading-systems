"""
tests/test_indicator_set.py (fuzion_fx)
=======================================
Valida los 8 indicadores votantes: forma del voto (dir en {-1,0,1}, fuerza en
[0,1], sin NaN), y que en escenarios CLAROS votan lo esperado:
 - tendencia alcista -> EMA/MACD/momentum CALL; RSI (reversion) sesga PUT.
 - tendencia bajista -> EMA/MACD/momentum PUT; RSI sesga CALL.
 - breakout de Donchian -> CALL.
Puro, SIN red.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import indicator_set as I                              # noqa: E402


def _velas(close):
    close = np.asarray(close, float)
    o = np.concatenate([[close[0]], close[:-1]])
    h = np.maximum(o, close) * 1.0003
    l = np.minimum(o, close) * 0.9997
    return {"open": list(o), "high": list(h), "low": list(l),
            "close": list(close), "volume": [0.0] * len(close)}


def test_forma_del_voto_valida() -> None:
    v = I.votar(_velas(np.linspace(1.10, 1.11, 120)))
    assert set(v.keys()) == set(I.INDICADORES.keys())      # los 8
    for nombre, voto in v.items():
        assert voto["dir"] in (-1, 0, 1), nombre
        assert 0.0 <= voto["fuerza"] <= 1.0, nombre
        assert not math.isnan(voto["fuerza"]), nombre


def test_tendencia_alcista() -> None:
    v = I.votar(_velas(np.linspace(1.10, 1.115, 120)))
    assert v["ema"]["dir"] == I.CALL
    assert v["macd"]["dir"] == I.CALL
    assert v["momentum"]["dir"] == I.CALL
    assert v["rsi"]["dir"] == I.PUT                 # reversion: sube -> sobrecompra


def test_tendencia_bajista() -> None:
    v = I.votar(_velas(np.linspace(1.115, 1.10, 120)))
    assert v["ema"]["dir"] == I.PUT
    assert v["macd"]["dir"] == I.PUT
    assert v["momentum"]["dir"] == I.PUT
    assert v["rsi"]["dir"] == I.CALL


def test_donchian_breakout_call() -> None:
    # Rango plano y un salto fuerte arriba en la ultima vela -> breakout CALL.
    base = list(np.full(120, 1.1000) + np.random.RandomState(1).normal(0, 0.0001, 120))
    base[-1] = 1.1050
    v = I.votar(_velas(base))
    assert v["donchian"]["dir"] == I.CALL and v["donchian"]["fuerza"] > 0


def test_sin_velas_suficientes_vacio() -> None:
    assert I.votar(_velas(np.linspace(1.10, 1.11, 30))) == {}


def test_momentum_es_multiplicador() -> None:
    v = I.votar(_velas(np.linspace(1.10, 1.115, 120)))
    assert v["momentum"].get("es_multiplicador") is True


def _run_all() -> None:
    tests = [test_forma_del_voto_valida, test_tendencia_alcista,
             test_tendencia_bajista, test_donchian_breakout_call,
             test_sin_velas_suficientes_vacio, test_momentum_es_multiplicador]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
