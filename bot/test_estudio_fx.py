"""
bot/test_estudio_fx.py
======================
Valida la MECÁNICA del estudio FX (sin red, con series sintéticas de propiedad
conocida): que detecte memoria cuando la hay, azar cuando no, y que el split
out-of-sample parta bien. No valida win-rates reales (dependen de los datos).
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.estudio_fx import estudiar_frame, estudiar_oos, _etq


def _df(closes):
    """DataFrame OHLC mínimo desde una lista de cierres (open = cierre previo)."""
    filas = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) + 0.001
        lo = min(o, c) - 0.001
        filas.append({"timestamp": 1_000_000_000_000 + i * 60000,
                      "open": o, "high": hi, "low": lo, "close": c, "volume": 10.0})
        prev = c
    return pd.DataFrame(filas)


def test_etq():
    assert _etq(5) == "5s"
    assert _etq(60) == "1m"
    assert _etq(300) == "5m"
    assert _etq(3600) == "1h"


def test_serie_alternante_es_reversion():
    # Serie que sube-baja-sube-baja: fuerte reversión → autocorr negativa marcada.
    closes = [100 + (1 if i % 2 == 0 else -1) * 0.5 for i in range(300)]
    r = estudiar_frame(_df(closes))
    assert r is not None
    assert r["autocorr"] < -0.3, f"esperaba autocorr muy negativa, dio {r['autocorr']}"
    # La estrategia de reversión debe superar claramente a momentum aquí.
    assert r["rev"] > r["mom"]


def test_serie_tendencia_es_momentum():
    # Serie monótona creciente: cada vela sube → momentum domina, autocorr ~ >=0.
    closes = [100 + i * 0.1 for i in range(300)]
    r = estudiar_frame(_df(closes))
    assert r is not None
    assert r["pct_up"] > 95.0, f"casi todas alcistas, dio {r['pct_up']}%"
    assert r["mom"] >= r["rev"]


def test_oos_parte_en_dos():
    closes = [100 + (i % 3) * 0.1 for i in range(400)]
    is_, oos = estudiar_oos(_df(closes))
    assert is_ is not None and oos is not None
    # Ambas mitades tienen ~200 velas (menos el expiry).
    assert abs(is_["velas"] - oos["velas"]) <= 1


def test_datos_insuficientes_devuelve_none():
    assert estudiar_frame(_df([100.0] * 50)) is None   # <100 velas


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
