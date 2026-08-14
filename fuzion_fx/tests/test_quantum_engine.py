"""
tests/test_quantum_engine.py (fuzion_fx)
========================================
Valida el motor cuantico:
 - Tendencia alcista fuerte en TODOS los tiempos -> direccion CALL y veredicto
   OPERAR/OPCIONAL con probabilidad alta.
 - Ruido lateral -> no OPERAR (MONITOREAR o NO_OPERAR), probabilidad tibia.
 - Un timeframe MAYOR (30m) que contradice fuerte -> NO_OPERAR (regla del doc).
 - analizar_tf da direccion/prob coherentes en un tf. SIN red.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import quantum_engine as Q                            # noqa: E402
from core.indicator_set import CALL, PUT                        # noqa: E402

_TFS = [60, 120, 180, 300, 600, 900, 1800]


def _velas(close):
    close = np.asarray(close, float)
    o = np.concatenate([[close[0]], close[:-1]])
    h = np.maximum(o, close) * 1.0003
    l = np.minimum(o, close) * 0.9997
    return {"open": list(o), "high": list(h), "low": list(l),
            "close": list(close), "volume": [0.0] * len(close)}


def _tendencia(direccion, seed):
    """Tendencia REALISTA: deriva + ruido con pullbacks (no una recta perfecta, que
    fijaria los osciladores en extremos y falsearia la reversion)."""
    rng = np.random.RandomState(seed)
    n = 200
    drift = np.linspace(0.0, direccion * 0.012, n)
    ruido = np.cumsum(rng.normal(0, 0.0004, n))
    ruido = ruido - np.linspace(0.0, ruido[-1], n)     # deriva domina, no el ruido
    return _velas(1.1150 + drift + 0.5 * ruido)


def _sube(seed=1):
    return _tendencia(+1, seed)


def _baja(seed=2):
    return _tendencia(-1, seed)


def _ruido(seed):
    rng = np.random.RandomState(seed)
    return _velas(1.1000 + rng.normal(0, 0.0003, 200))


def test_tf_alcista_da_call() -> None:
    r = Q.analizar_tf(_sube())
    assert r is not None and r["dir"] == CALL and 0.0 <= r["prob"] <= 1.0


def test_todos_los_tiempos_suben_opera_call() -> None:
    velas = {tf: _sube() for tf in _TFS}
    r = Q.analizar(velas)
    assert r["direccion"] == CALL
    assert r["veredicto"] in ("OPERAR", "OPCIONAL")
    assert r["probabilidad"] >= Q.UMBRAL_OPCIONAL
    assert r["n_alineados"] >= 3


def test_ruido_no_opera() -> None:
    velas = {tf: _ruido(tf) for tf in _TFS}
    r = Q.analizar(velas)
    assert r["veredicto"] in ("MONITOREAR", "NO_OPERAR")
    assert r["probabilidad"] < Q.UMBRAL_OPERAR


def test_timeframe_mayor_contradice_bloquea() -> None:
    # Todo sube menos el 30m que baja fuerte -> la regla del doc fuerza NO_OPERAR.
    velas = {tf: _sube() for tf in _TFS}
    velas[1800] = _baja()
    r = Q.analizar(velas)
    assert r["veredicto"] == "NO_OPERAR"
    assert "mayor" in r["motivo"]


def test_sin_datos_no_opera() -> None:
    r = Q.analizar({})
    assert r["veredicto"] == "NO_OPERAR" and r["n_alineados"] == 0


def _run_all() -> None:
    tests = [test_tf_alcista_da_call, test_todos_los_tiempos_suben_opera_call,
             test_ruido_no_opera, test_timeframe_mayor_contradice_bloquea,
             test_sin_datos_no_opera]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
