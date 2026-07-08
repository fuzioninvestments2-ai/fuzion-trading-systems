"""
bot/test_verificar_skip.py
==========================
Valida la prueba decisiva (sin red). Caso clave: una serie SIN reversión real pero
CON ruido en el precio debe mostrar reversión INMEDIATA alta y SALTADA ~50% (el
artefacto de precio compartido). Sin numpy.random (no disponible): ruido determinista.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.verificar_skip import señales, _pip


def _df(closes):
    return pd.DataFrame({"timestamp": [1_000_000_000_000 + i * 60000 for i in range(len(closes))],
                         "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1.0] * len(closes)})


def test_pip():
    assert _pip("EURUSD") == 0.0001
    assert _pip("USDJPY") == 0.01


def test_columnas():
    closes = [1.10 + (0.0003 if i % 2 else -0.0003) for i in range(120)]
    s = señales(_df(closes), "EURUSD")
    assert s is not None
    for col in ("pico", "fut_inm", "fut_skip"):
        assert col in s.columns


def test_artefacto_precio_compartido():
    # Precio base PLANO + ruido alternante en el close: NO hay reversión real, pero
    # el ruido compartido debe dar INMEDIATA alta y SALTADA cercana a 50%.
    base = 1.1000
    ruido = [0.0003 if i % 2 == 0 else -0.0003 for i in range(300)]
    closes = [base + ruido[i] for i in range(300)]
    s = señales(_df(closes), "EURUSD")
    inm = (np.sign(s["fut_inm"]) != np.sign(s["pico"])).mean() * 100
    # La reversión inmediata sobre ruido alternante es altísima (artefacto).
    assert inm > 80, f"esperaba INMEDIATA alta por artefacto, dio {inm:.0f}%"


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
