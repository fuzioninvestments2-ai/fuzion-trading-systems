"""
bot/skills/test_multi_timeframe.py
==================================
Valida el analizador multi-timeframe (sin red): estructura, alineación y formato.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.skills.multi_timeframe import (analizar, formato_telegram,
                                        TF_ALERTA, TF_OPERABLES)


def _df(closes):
    filas = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        filas.append({"timestamp": 1_000_000_000_000 + i * 60000, "open": o,
                      "high": max(o, c) + 0.01, "low": min(o, c) - 0.01,
                      "close": c, "volume": 10.0})
        prev = c
    return pd.DataFrame(filas)


def _frames(closes):
    """Mismos cierres en los 13 tiempos (suficiente para el test estructural)."""
    return {tf: _df(closes) for tf in TF_ALERTA}


def test_tiempos_definidos():
    assert TF_ALERTA[0] == 5 and TF_ALERTA[-1] == 14400
    assert set(TF_OPERABLES) == {60, 120, 180, 300, 600}


def test_estructura_resultado():
    r = analizar(_frames([100 + np.sin(i / 5) * 0.3 for i in range(120)]), pair="EURUSD")
    for k in ("pair", "direccion", "confianza", "operar", "alineados",
              "presentes", "dir_por_tf", "operables"):
        assert k in r
    assert r["presentes"] <= len(TF_ALERTA)


def test_formato_no_vacio():
    r = analizar(_frames([100 + i * 0.05 for i in range(120)]), pair="GBPUSD")
    txt = formato_telegram(r)
    assert "GBPUSD" in txt and "Vigilancia 13 tiempos" in txt
    assert "No garantiza" in txt          # nota honesta presente


def test_pocos_frames_no_opera():
    # Solo 2 tiempos presentes → no debe emitir (presentes < 9).
    r = analizar({60: _df([100 + i * 0.1 for i in range(120)]),
                  120: _df([100 + i * 0.1 for i in range(120)])}, pair="EURUSD")
    assert r["operar"] is False


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
