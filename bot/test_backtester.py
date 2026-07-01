"""
bot/test_backtester.py
======================
Prueba del backtester (Regla 4). No mide rentabilidad real: valida que las
métricas se calculan de forma coherente y que la calibración (sweep) funciona.
"""

import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.config import get_preset
from bot.candles import CandleBuilder
from bot.backtester import backtest, sweep_confidence


def _make_candles(n=1200, seed=3):
    """Genera velas sintéticas (onda + ruido) con el constructor real."""
    cb = CandleBuilder(60)
    rng = random.Random(seed)
    ts = 0
    for i in range(n * 3):                      # 3 ticks por vela
        price = 100 + 3 * math.sin(i / 60.0) + rng.uniform(-0.4, 0.4)
        cb.add_tick(price, ts)
        ts += 20_000
    return cb.to_dataframe()


def test_backtest_coherente():
    cfg = get_preset("agresivo")
    df = _make_candles()
    res = backtest(cfg, df, expiry_horizon=1)

    # Coherencia interna (no rentabilidad).
    assert res["wins"] + res["losses"] + res["ties"] == res["signals"], res
    assert 0.0 <= res["win_rate"] <= 1.0, res
    assert res["max_drawdown"] >= 0.0, res
    print("✅ (A) Backtest coherente:", res)


def test_sweep_calibracion():
    cfg = get_preset("agresivo")
    df = _make_candles()
    barrido = sweep_confidence(cfg, df, valores=(0.2, 0.4, 0.6))

    # A mayor umbral, en general MENOS (o igual) señales: es la idea de calibrar.
    s02 = barrido[0.2]["signals"]
    s06 = barrido[0.6]["signals"]
    assert s02 >= s06, f"❌ Umbral alto debería dar <= señales: {s02} vs {s06}"
    print("✅ (B) Sweep de calibración:")
    for v, r in barrido.items():
        print(f"    conf>={v}: señales={r['signals']}, win_rate={r['win_rate']}, "
              f"net={r['net_profit']}, PF={r['profit_factor']}")


if __name__ == "__main__":
    test_backtest_coherente()
    test_sweep_calibracion()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
