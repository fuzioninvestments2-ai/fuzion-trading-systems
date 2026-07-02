"""
bot/test_calibration.py
=======================
Prueba de la calibración (Regla 4).

Verifica:
  (A) Con pocas velas -> None (no se puede calibrar honestamente).
  (B) Con suficiente historial -> devuelve un umbral válido del set probado.
"""

import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.candles import CandleBuilder
from bot.calibration import calibrate


def _candles(n=800, seed=2):
    cb = CandleBuilder(60)
    rng = random.Random(seed)
    ts = 0
    for i in range(n * 3):
        price = 100 + 3 * math.sin(i / 50.0) + rng.uniform(-0.4, 0.4)
        cb.add_tick(price, ts)
        ts += 20_000
    return cb.to_dataframe()


def test_pocas_velas():
    assert calibrate(_candles(10)) is None, "❌ Con pocas velas debe dar None"
    print("✅ (A) Con pocas velas -> None (honesto).")


def test_calibra():
    valores = (0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
    best = calibrate(_candles(), valores=valores, min_signals=5)
    assert best is not None, "❌ Debería calibrar con suficiente historial"
    assert best["min_confidence"] in valores
    assert 0.0 <= best["win_rate"] <= 1.0
    print("✅ (B) Calibró un umbral:", best)


if __name__ == "__main__":
    test_pocas_velas()
    test_calibra()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
