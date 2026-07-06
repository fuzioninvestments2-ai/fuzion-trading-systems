"""
bot/test_cuantico.py
====================
Valida SIN red el sistema multi-timeframe ponderado: señal por timeframe,
probabilidad ponderada, convergencia logarítmica y la decisión >=90%.
"""
import math
import numpy as np
import pandas as pd

from bot.cuantico import (
    calculate_timeframe_signal, calculate_quantum_probability,
    calculate_logarithmic_convergence, validate_signal_90, TIMEFRAMES_9, TOTAL_TF)


def _df(subiendo=True, n=120):
    xs = [100 + (i if subiendo else (n - i)) * 0.3 for i in range(n)]
    c = pd.Series(xs, dtype=float)
    return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]),
                         "high": c + 0.2, "low": c - 0.2, "close": c,
                         "volume": [100] * n})


def _plano(n=120):
    c = pd.Series([100.0] * n, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 0.01, "low": c - 0.01,
                         "close": c, "volume": [100] * n})


def test_signal_por_timeframe():
    d, f, p = calculate_timeframe_signal(_df(subiendo=True))
    assert d == 1 and 0 <= f <= 1 and p > 50, (d, f, p)
    d2, _f2, p2 = calculate_timeframe_signal(_df(subiendo=False))
    assert d2 == -1 and p2 < 50
    print(f"OK señal por timeframe: alcista +1 {p:.0f}% / bajista -1 {p2:.0f}%")


def test_convergencia_logaritmica():
    # Valores exactos de la fórmula del trader (total=9).
    assert calculate_logarithmic_convergence(9) == 100.0
    assert abs(calculate_logarithmic_convergence(8) - 95.4) < 0.2
    assert abs(calculate_logarithmic_convergence(7) - 90.3) < 0.2
    print("OK convergencia: 9/9=100%, 8/9=95.4%, 7/9=90.3%")


def test_probabilidad_alcista():
    frames = {tf: _df(subiendo=True) for tf in TIMEFRAMES_9}
    q = calculate_quantum_probability(frames)
    assert q["direccion"] == "CALL" and q["alineados"] == 9
    # Probabilidad CALIBRADA (operativa) llega alto en 9/9; la literal queda baja.
    assert q["probabilidad"] >= 90 and q["probabilidad_literal"] < 60
    print(f"OK 9/9 alcista -> CALL · prob calibrada {q['probabilidad']:.0f}% "
          f"(literal {q['probabilidad_literal']:.0f}%)")


def test_9de9_opera_y_7de9_no():
    # 9/9 fuerte -> OPERAR (prob calibrada >=90, convergencia 100%).
    f9 = {tf: _df(subiendo=True) for tf in TIMEFRAMES_9}
    r9 = validate_signal_90(f9, payout=85, hora_utc=14)
    assert r9["operar"] and r9["convergencia"] == 100.0, r9
    # 7/9 (dos en contra) -> NO OPERAR (probabilidad < 90).
    f7 = dict(f9); f7[600] = _df(subiendo=False); f7[900] = _df(subiendo=False)
    r7 = validate_signal_90(f7, payout=85, hora_utc=14)
    assert not r7["operar"], r7
    print(f"OK 9/9 -> OPERAR ({r9['probabilidad']:.0f}%); "
          f"7/9 -> NO OPERAR ({r7['probabilidad']:.0f}%)")


def test_faltan_tiempos_no_opera():
    frames = {tf: _df(subiendo=True) for tf in TIMEFRAMES_9[:5]}   # faltan 4
    r = validate_signal_90(frames)
    assert not r["operar"] and "faltan" in r["motivo"]
    print("OK faltan tiempos ->", r["motivo"])


def test_hora_baja_volatilidad_no_opera():
    frames = {tf: _df(subiendo=True) for tf in TIMEFRAMES_9}
    r = validate_signal_90(frames, hora_utc=23)   # 23:00 UTC
    assert not r["operar"] and "baja volatilidad" in r["motivo"]
    print("OK hora 23:00 UTC ->", r["motivo"])


def test_mercado_plano_no_opera():
    frames = {tf: _plano() for tf in TIMEFRAMES_9}
    r = validate_signal_90(frames, hora_utc=14)
    assert not r["operar"], r
    print("OK mercado plano -> NO OPERAR:", r["motivo"])


if __name__ == "__main__":
    test_signal_por_timeframe()
    test_convergencia_logaritmica()
    test_probabilidad_alcista()
    test_9de9_opera_y_7de9_no()
    test_faltan_tiempos_no_opera()
    test_hora_baja_volatilidad_no_opera()
    test_mercado_plano_no_opera()
    print("\nTODOS OK — sistema multi-timeframe ponderado (5s-15m)")
