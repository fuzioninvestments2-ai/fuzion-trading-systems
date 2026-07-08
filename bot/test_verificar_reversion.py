"""
bot/test_verificar_reversion.py
===============================
Valida la mecánica de la verificación (sin red): alineación del movimiento actual
con el futuro y el tamaño en pips. Usa una serie con rebote perfecto (alterna) para
comprobar que la reversión "gana" ahí, y mide el tamaño correcto del movimiento.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.verificar_reversion import analizar, _pip


def _df(closes):
    return pd.DataFrame({"timestamp": [1_000_000_000_000 + i * 60000 for i in range(len(closes))],
                         "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1.0] * len(closes)})


def test_pip():
    assert _pip("EURUSD") == 0.0001
    assert _pip("USDJPY") == 0.01
    assert _pip("CADJPY") == 0.01


def test_rebote_perfecto_gana():
    # Alterna arriba/abajo → reversión (apostar contra) acierta casi siempre.
    closes = [1.1000 + (0.0005 if i % 2 == 0 else -0.0005) for i in range(200)]
    a = analizar(_df(closes), "EURUSD")
    assert a is not None and len(a) > 100
    assert a["gano"].mean() > 0.9


def test_tendencia_reversion_pierde():
    closes = [1.1000 + i * 0.0002 for i in range(200)]
    a = analizar(_df(closes), "EURUSD")
    assert a["gano"].mean() < 0.1


def test_magnitud_en_pips():
    # Movimientos de 5 pips en EURUSD (0.0005) → mag_pips ≈ 5.
    closes = [1.1000 + (0.0005 if i % 2 == 0 else -0.0005) for i in range(60)]
    a = analizar(_df(closes), "EURUSD")
    assert abs(a["mag_pips"].mean() - 10.0) < 0.5   # amplitud pico-a-pico = 10 pips


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
