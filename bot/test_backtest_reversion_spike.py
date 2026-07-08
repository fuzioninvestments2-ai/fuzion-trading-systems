"""
bot/test_backtest_reversion_spike.py
====================================
Valida la mecánica del backtest de reversión-tras-pico (sin red): cálculo del
movimiento en pips y que la reversión acierte en una serie que sube-baja fuerte.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.backtest_reversion_spike import señales_par, _pip, BREAKEVEN, PAYOUT


def _df(closes):
    return pd.DataFrame({"timestamp": [1_000_000_000_000 + i * 60000 for i in range(len(closes))],
                         "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1.0] * len(closes)})


def test_breakeven():
    assert abs(BREAKEVEN - 52.083) < 0.01
    assert PAYOUT == 0.92


def test_movimiento_en_pips():
    # Picos de 3 pips en EURUSD (0.0003) alternados.
    closes = [1.1000 + (0.0003 if i % 2 == 0 else -0.0003) for i in range(120)]
    s = señales_par(_df(closes), "EURUSD")
    assert s is not None
    assert abs(s["mov"].abs().mean() - 6.0) < 0.3     # amplitud pico-a-pico = 6 pips


def test_reversion_acierta_en_picos_alternos():
    # Serie que alterna fuerte: revertir acierta casi siempre.
    closes = [1.1000 + (0.0003 if i % 2 == 0 else -0.0003) for i in range(200)]
    s = señales_par(_df(closes), "EURUSD")
    gano = np.sign(s["fut"]) != np.sign(s["mov"])
    assert gano.mean() > 0.9


def test_jpy_pip():
    closes = [150.00 + (0.03 if i % 2 == 0 else -0.03) for i in range(120)]
    s = señales_par(_df(closes), "USDJPY")
    assert abs(s["mov"].abs().mean() - 6.0) < 0.3     # 0.06/0.01 = 6 pips


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
