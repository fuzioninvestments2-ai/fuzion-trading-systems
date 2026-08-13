"""
tests/test_ml_direccion.py (fuzion_fx)
======================================
Valida que la MEDICION del modelo de direccion es HONESTA (sin red, sin DB):

  1) Si la serie TIENE senal (retornos con memoria: momentum real), el modelo la
     detecta -> acierto fuera de muestra CLARAMENTE > 50%.
  2) Si la serie es RUIDO puro (paseo aleatorio), el acierto fuera de muestra da
     ~50% -> el modelo NO inventa una ventaja que no existe.

Asi sabemos que cuando el script diga "no hay borde" sobre datos reales, es porque
de verdad no lo hay, no porque la medicion este rota. Todo con la logistica numpy
(sin sklearn), que es el piso que corre en cualquier maquina.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts.ml_direccion import (construir_features, _logistica_numpy,  # noqa: E402
                                  evaluar, TRAIN_FRAC)


def _ohlc_desde_retornos(ret: np.ndarray):
    """Arma OHLC coherente desde una serie de retornos. open=cierre previo; high/low
    envuelven open y close con un pequeno margen. ts cada 60s."""
    c = 1.10 * np.cumprod(1.0 + ret)
    o = np.empty_like(c); o[0] = c[0]; o[1:] = c[:-1]
    hi = np.maximum(o, c) * 1.0002
    lo = np.minimum(o, c) * 0.9998
    ts = np.arange(len(c), dtype=float) * 60.0
    return o, hi, lo, c, ts


def _acc_fuera_de_muestra(o, h, l, c, ts, horizonte=1):
    X, y = construir_features(o, h, l, c, ts, horizonte)
    corte = int(len(y) * TRAIN_FRAC)
    prob = _logistica_numpy(X[:corte], y[:corte], X[corte:])
    return evaluar(prob, y[corte:])[0]["acc"]


def test_detecta_borde_si_hay_memoria() -> None:
    # Retornos con autocorrelacion positiva fuerte: r[t] = 0.6*r[t-1] + ruido. El
    # signo de ayer predice el de hoy -> la logistica (que ve retornos rezagados)
    # DEBE superar 50% fuera de muestra. Si no, la medicion no sirve.
    rng = np.random.RandomState(7)
    n = 3000
    ruido = rng.normal(0, 0.0008, n)
    ret = np.zeros(n)
    for t in range(1, n):
        ret[t] = 0.6 * ret[t - 1] + ruido[t]
    o, h, l, c, ts = _ohlc_desde_retornos(ret)
    acc = _acc_fuera_de_muestra(o, h, l, c, ts)
    assert acc > 55.0, f"con memoria real deberia superar 55%, dio {acc:.1f}%"


def test_ruido_puro_da_cerca_de_50() -> None:
    # Paseo aleatorio: retornos independientes -> la direccion futura es ~50/50.
    # El modelo NO debe inventar borde (acierto lejos de 50 seria sobreajuste que
    # la validacion cronologica justamente evita).
    rng = np.random.RandomState(11)
    ret = rng.normal(0, 0.0008, 3000)
    o, h, l, c, ts = _ohlc_desde_retornos(ret)
    acc = _acc_fuera_de_muestra(o, h, l, c, ts)
    assert 43.0 < acc < 57.0, f"en ruido deberia dar ~50%, dio {acc:.1f}%"


def test_features_sin_nan_y_alineadas() -> None:
    rng = np.random.RandomState(3)
    ret = rng.normal(0, 0.0008, 800)
    o, h, l, c, ts = _ohlc_desde_retornos(ret)
    X, y = construir_features(o, h, l, c, ts, horizonte=1)
    assert len(X) == len(y) and len(y) > 500
    assert not np.isnan(X).any() and not np.isinf(X).any()
    assert set(np.unique(y)).issubset({0, 1})


def _run_all() -> None:
    tests = [test_detecta_borde_si_hay_memoria, test_ruido_puro_da_cerca_de_50,
             test_features_sin_nan_y_alineadas]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
