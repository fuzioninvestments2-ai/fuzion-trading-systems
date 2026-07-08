"""
bot/test_estudio_condiciones.py
===============================
Valida la señal de reversión vectorizada (sin red): en una serie que alterna
(reversión perfecta) debe ganar casi siempre; en una tendencia debe perder.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.estudio_condiciones import señal_reversion


def _df(closes):
    filas = []
    for i, c in enumerate(closes):
        filas.append({"timestamp": 1_000_000_000_000 + i * 60000,
                      "open": c, "high": c + 0.01, "low": c - 0.01,
                      "close": c, "volume": 1.0})
    return pd.DataFrame(filas)


def test_reversion_gana_en_serie_alternante():
    # Sube, baja, sube, baja... apostar contra el último movimiento acierta casi siempre.
    closes = [100 + (0.5 if i % 2 == 0 else -0.5) for i in range(200)]
    s = señal_reversion(_df(closes))
    assert len(s) > 100
    assert s["gano"].mean() > 0.9, f"reversión debería ganar >90%, dio {s['gano'].mean():.2f}"


def test_reversion_pierde_en_tendencia():
    # Tendencia monótona: apostar contra el movimiento falla casi siempre.
    closes = [100 + i * 0.1 for i in range(200)]
    s = señal_reversion(_df(closes))
    assert len(s) > 100
    assert s["gano"].mean() < 0.1, f"reversión debería perder en tendencia, dio {s['gano'].mean():.2f}"


def test_columnas_y_horas():
    closes = [100 + (0.3 if i % 2 else -0.3) for i in range(120)]
    s = señal_reversion(_df(closes))
    for col in ("dir", "gano", "hora", "vol"):
        assert col in s.columns
    assert s["hora"].between(0, 23).all()


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
