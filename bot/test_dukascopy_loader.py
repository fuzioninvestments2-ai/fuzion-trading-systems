"""
bot/test_dukascopy_loader.py
============================
Valida lo testeable SIN red del descargador de Dukascopy: el resampleo de 1s a
5s/10s/15s/30s y la normalización de formato. La descarga real necesita red y se
prueba en la PC del trader.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.dukascopy_loader import _a_formato, SEGUNDOS_OBJETIVO, CLAVE
from bot.resamplear import resamplear


def _seg1(n):
    """n velas de 1 segundo alineadas a bloque de 30s."""
    base = 1_000_000_000_000 // 30_000 * 30_000
    filas = []
    for i in range(n):
        p = 100.0 + i * 0.001
        filas.append({"timestamp": base + i * 1000, "open": p, "high": p + 0.002,
                      "low": p - 0.002, "close": p + 0.001, "volume": 1.0})
    return pd.DataFrame(filas)


def test_resample_1s_a_5s():
    df = _seg1(30)                               # 30 velas 1s → 6 velas de 5s
    r = resamplear(df, 5)
    assert len(r) == 6, f"esperaba 6 velas de 5s, {len(r)}"
    assert r["open"].iloc[0] == df["open"].iloc[0]
    assert r["close"].iloc[0] == df["close"].iloc[4]
    assert r["high"].iloc[0] == df["high"].iloc[:5].max()
    assert r["volume"].iloc[0] == df["volume"].iloc[:5].sum()


def test_objetivos_son_los_4():
    assert SEGUNDOS_OBJETIVO == [5, 10, 15, 30]
    for s in SEGUNDOS_OBJETIVO:
        assert s in CLAVE


def test_a_formato_desde_indice_datetime():
    # Simula el DataFrame de dukascopy: índice datetime, columnas OHLC.
    idx = pd.date_range("2026-07-01", periods=5, freq="s", tz="UTC")
    df = pd.DataFrame({"open": [1, 2, 3, 4, 5], "high": [1, 2, 3, 4, 5],
                       "low": [1, 2, 3, 4, 5], "close": [1, 2, 3, 4, 5],
                       "volume": [1, 1, 1, 1, 1]}, index=idx)
    out = _a_formato(df)
    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out["timestamp"].is_monotonic_increasing
    assert out["timestamp"].iloc[0] > 1_000_000_000_000     # ms epoch plausible


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
            except Exception as e:
                fallos += 1
                print(f"ERR  {nombre}: {e}")
    sys.exit(1 if fallos else 0)
