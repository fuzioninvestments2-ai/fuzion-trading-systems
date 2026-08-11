"""
tests/test_calibrar.py (fuzion_fx)
==================================
Valida el nucleo de calibracion: grilla, agregado por bot y la regla de
recomendacion (mayor win-rate que cumpla frecuencia + muestra). SIN red.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts.calibrar import (_configs, evaluar_grilla, recomendar,   # noqa: E402
                              GRILLA_DEFAULT)

_IND = {"ema_fast": 9, "ema_slow": 21, "rsi_period": 14, "macd_fast": 12,
        "macd_slow": 26, "macd_signal": 9, "bb_period": 20, "bb_std": 2.0,
        "atr_period": 14}


def _serie(vals):
    c = list(vals)
    return {"open": c, "high": c, "low": c, "close": c}


def _series_demo():
    # Dos pares con movimiento distinto (suficientes velas para los indicadores).
    rng = 1.10 + np.cumsum(np.array([-0.0002, 0.00015] * 120))
    rng2 = 1.30 + np.cumsum(np.array([0.0001, -0.00012] * 120))
    return {"EUR/USD": _serie(rng), "GBP/USD": _serie(rng2)}


def test_grilla_cartesiana() -> None:
    n = len(list(_configs(GRILLA_DEFAULT)))
    assert n == 3 * 2 * 2                       # rsi_bands x bb_std x min_conf


def test_evaluar_grilla_forma_y_orden() -> None:
    filas = evaluar_grilla(_series_demo(), _IND, 60)
    assert len(filas) == 12
    for r in filas:
        assert {"etiqueta", "win_pct", "sph_bot", "pares", "cfg"} <= set(r)
        assert r["pares"] == 2
        # sph_bot = tasa por par * nro de pares.
        assert r["sph_bot"] == round(r["signals_per_hour"] * 2, 2)
    # Orden: win-rate desc (None al final).
    wr = [(-1 if r["win_pct"] is None else r["win_pct"]) for r in filas]
    assert wr == sorted(wr, reverse=True)


def test_recomendar_elige_mayor_winrate_que_cumple() -> None:
    filas = [
        {"etiqueta": "A", "win_pct": 80.0, "wins": 8, "losses": 2, "sph_bot": 2.0,
         "cfg": {}},   # win-rate alto pero POCA frecuencia -> descartada
        {"etiqueta": "B", "win_pct": 62.0, "wins": 40, "losses": 25, "sph_bot": 7.0,
         "cfg": {}},   # cumple todo
        {"etiqueta": "C", "win_pct": 70.0, "wins": 35, "losses": 15, "sph_bot": 6.5,
         "cfg": {}},   # cumple y mejor win-rate que B
        {"etiqueta": "D", "win_pct": 90.0, "wins": 5, "losses": 0, "sph_bot": 9.0,
         "cfg": {}},   # muestra insuficiente -> descartada
    ]
    rec = recomendar(filas, objetivo_sph=6.0, min_winrate=55.0, min_muestra=30)
    assert rec["etiqueta"] == "C"


def test_recomendar_none_si_ninguna_cumple() -> None:
    filas = [
        {"etiqueta": "A", "win_pct": 50.0, "wins": 40, "losses": 40, "sph_bot": 8.0,
         "cfg": {}},   # win-rate bajo
        {"etiqueta": "B", "win_pct": 80.0, "wins": 40, "losses": 10, "sph_bot": 1.0,
         "cfg": {}},   # frecuencia baja
    ]
    assert recomendar(filas, 6.0, 55.0, 30) is None


def _run_all() -> None:
    tests = [test_grilla_cartesiana, test_evaluar_grilla_forma_y_orden,
             test_recomendar_elige_mayor_winrate_que_cumple,
             test_recomendar_none_si_ninguna_cumple]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
