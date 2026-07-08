"""
bot/test_resamplear.py
======================
Valida el resampleador (sin red): agregación correcta de 1m → 2m/3m y que un
bloque toma open=primero, close=último, high=máx, low=mín, volumen=suma.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.resamplear import resamplear, DERIVADOS


def _m1(n):
    """n velas de 1m alineadas a bloques de 4h (múltiplo de todos los derivados)."""
    base = 1_000_000_000_000 // 14_400_000 * 14_400_000
    filas = []
    for i in range(n):
        p = 100.0 + i
        filas.append({"timestamp": base + i * 60_000, "open": p, "high": p + 0.5,
                      "low": p - 0.5, "close": p + 0.1, "volume": 10.0})
    return pd.DataFrame(filas)


def test_2m_desde_1m():
    df = _m1(6)                                  # 6 velas 1m → 3 velas de 2m
    r = resamplear(df, 120)
    assert len(r) == 3, f"esperaba 3 velas de 2m, {len(r)}"
    assert r["open"].iloc[0] == df["open"].iloc[0]
    assert r["close"].iloc[0] == df["close"].iloc[1]
    assert r["high"].iloc[0] == df["high"].iloc[:2].max()
    assert r["low"].iloc[0] == df["low"].iloc[:2].min()
    assert r["volume"].iloc[0] == df["volume"].iloc[:2].sum()


def test_3m_desde_1m():
    df = _m1(9)                                  # 9 velas 1m → 3 velas de 3m
    r = resamplear(df, 180)
    assert len(r) == 3
    assert r["close"].iloc[0] == df["close"].iloc[2]
    assert list(r.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_derivados_incluye_los_4():
    for clave in ("tf120", "tf180", "tf600", "tf14400"):
        assert clave in DERIVADOS


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
