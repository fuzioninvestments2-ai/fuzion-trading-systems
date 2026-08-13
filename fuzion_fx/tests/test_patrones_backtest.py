"""
tests/test_patrones_backtest.py (fuzion_fx)
===========================================
Valida:
  - core.candle_patterns.detectar: martillo/estrella/doji/marubozu/envolvente.
  - core.backtester.resample: agrega la serie base a una mas gruesa.
  - core.backtester.backtest_convergencia: corre la foto completa sobre una serie
    y devuelve acierto GLOBAL y por FUERZA (fuertes vs debiles), sin mirar futuro.
SIN red.
"""

from __future__ import annotations

import math
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import candle_patterns                                # noqa: E402
from core.backtester import resample, backtest_convergencia     # noqa: E402
from core.config import get_bot_config                          # noqa: E402


def _vela(o, h, l, c):
    return {"open": [o], "high": [h], "low": [l], "close": [c]}


def test_patron_martillo_y_estrella() -> None:
    # Martillo: cuerpo chico arriba, mecha inferior larga -> alcista (+1).
    assert candle_patterns.detectar(_vela(1.10, 1.101, 1.090, 1.1005))["lean"] == 1
    # Estrella: mecha superior larga -> bajista (-1).
    assert candle_patterns.detectar(_vela(1.10, 1.110, 1.099, 1.0995))["lean"] == -1


def test_patron_doji_indecision() -> None:
    r = candle_patterns.detectar(_vela(1.1000, 1.1010, 1.0990, 1.1000))
    assert r["indecision"] is True and r["lean"] == 0


def test_patron_envolvente_alcista() -> None:
    # Vela previa bajista, actual alcista que la envuelve -> +1.
    c = {"open": [1.101, 1.099], "high": [1.102, 1.103],
         "low": [1.0985, 1.0985], "close": [1.0990, 1.102]}
    assert candle_patterns.detectar(c)["lean"] == 1


def test_resample_agrega_bien() -> None:
    base = {"open": [1, 2, 3, 4], "high": [2, 3, 4, 5],
            "low": [0, 1, 2, 3], "close": [1.5, 2.5, 3.5, 4.5]}
    r = resample(base, 2)
    assert r["open"] == [1, 3]           # primer de cada bloque
    assert r["high"] == [3, 5]           # max
    assert r["low"] == [0, 2]            # min
    assert r["close"] == [2.5, 4.5]      # ultimo


def _serie_tendencia(n=400):
    # Tendencia alcista con ruido: sube neto, con cuerpos reales (no doji).
    o = []; h = []; l = []; c = []
    p = 1.1000
    for i in range(n):
        op = p
        p = p + 8e-5 + 4e-5 * math.sin(i / 5.0)      # sube con oscilacion
        hi = max(op, p) + 2e-5
        lo = min(op, p) - 2e-5
        o.append(op); h.append(hi); l.append(lo); c.append(p)
    return {"open": o, "high": h, "low": l, "close": c}


def test_backtest_convergencia_corre_y_mide_por_fuerza() -> None:
    cfg = get_bot_config("f1_m1")
    base = _serie_tendencia(400)
    r = backtest_convergencia(base, 60, cfg["indicators"], cfg["signal"],
                              umbral=0.35, min_tf=3, min_fuerza=0.0)
    # Estructura correcta y coherente.
    assert set(r) >= {"emissions", "wins", "losses", "win_pct", "by_fuerza"}
    assert r["wins"] + r["losses"] <= r["emissions"]        # ties no cuentan
    assert set(r["by_fuerza"]) == {"fuertes", "debiles"}
    # Emite algo sobre una tendencia clara.
    assert r["emissions"] >= 1


def test_backtest_horizonte_cambia_resolucion() -> None:
    # Con horizonte mayor se resuelve contra una vela mas lejana: la ventana util
    # se acorta (n-H), pero la estructura del resultado se mantiene y sigue emitiendo.
    cfg = get_bot_config("f1_m1")
    base = _serie_tendencia(400)
    r1 = backtest_convergencia(base, 60, cfg["indicators"], cfg["signal"],
                               umbral=0.35, min_tf=3, horizonte=1)
    r5 = backtest_convergencia(base, 60, cfg["indicators"], cfg["signal"],
                               umbral=0.35, min_tf=3, horizonte=5)
    assert set(r5) >= {"emissions", "wins", "losses", "win_pct", "by_fuerza"}
    # horizonte>1 no puede resolver las ultimas H velas -> a lo sumo tantas como H=1.
    assert r5["emissions"] <= r1["emissions"] + 1


def _run_all() -> None:
    tests = [test_patron_martillo_y_estrella, test_patron_doji_indecision,
             test_patron_envolvente_alcista, test_resample_agrega_bien,
             test_backtest_convergencia_corre_y_mide_por_fuerza,
             test_backtest_horizonte_cambia_resolucion]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
