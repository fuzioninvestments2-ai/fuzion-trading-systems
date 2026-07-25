"""
bot/test_backtest_reversion_real.py
===================================
Valida sin red la reversión: tamaño de pip, estadística (win-rate/margen/P&L), la
acumulación sobre una serie con reversión perfecta (debe detectar acierto alto), y
una corrida completa de `correr` sobre un M1 sintético.
"""
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.backtest_reversion_real import (_pip, _stats, _acumular_par, correr,
                                         BREAKEVEN)


def test_pip_jpy_vs_resto():
    assert _pip("USDJPY") == 0.01
    assert _pip("EURUSD") == 0.0001


def test_stats_winrate_margen_pnl():
    wr, margen, pnl, n = _stats(60, 40)
    assert n == 100 and abs(wr - 60.0) < 1e-9 and margen > 0
    assert pnl > 0                                     # 60% con payout 92% gana dinero
    assert _stats(0, 0) is None


def test_breakeven_92():
    assert abs(BREAKEVEN - 52.083) < 0.01


def _serie_reversion(n):
    # Serie que SIEMPRE se devuelve: sube 8 pips, baja 8 pips... reversión gana a 1m.
    # 8 pips (no 5) evita el borde exacto del umbral por redondeo de float.
    return np.array([1.10 + 0.0008 * (i % 2) for i in range(n)], dtype=float)


def test_acumular_detecta_reversion():
    acc = {}
    _acumular_par(_serie_reversion(400), "EURUSD", acc)
    # A umbral 5 pips, expiry 1m, OOS: la reversión debe acertar casi siempre.
    w, l = acc.get((5, 1, "oos"), (0, 0))
    assert w + l > 0
    assert w / (w + l) > 0.9                            # serie perfecta -> win alto


def test_acumular_serie_corta_no_revienta():
    acc = {}
    _acumular_par(np.array([1.1, 1.2, 1.3], dtype=float), "EURUSD", acc)
    assert acc == {}                                    # <300 velas -> no acumula


def test_correr_sobre_m1_sintetico():
    with tempfile.TemporaryDirectory() as d:
        c = _serie_reversion(1000)
        ts = np.array([1_700_000_000_000 + i * 60_000 for i in range(len(c))],
                      dtype=np.int64)
        pd.DataFrame({"timestamp": ts, "open": c, "high": c, "low": c,
                      "close": c, "volume": 1.0}).to_csv(
            os.path.join(d, "EURUSD__M1.csv.gz"), index=False, compression="gzip")
        resumen = correr(destino=d, pares=["EURUSD"])
        assert (5, 1) in resumen
        wr_oos, margen, pnl, n = resumen[(5, 1)]
        assert wr_oos > 90.0 and pnl > 0                # reversión perfecta -> gana


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
