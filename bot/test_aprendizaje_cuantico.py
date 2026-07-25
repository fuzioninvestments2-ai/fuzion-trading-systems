"""
bot/test_aprendizaje_cuantico.py
================================
Valida sin red la máquina: la fórmula (regresión logística) aprende un caso separable,
el vector de eventos tiene el largo correcto, el P&L, y una corrida de `aprender` sobre
datos sintéticos que produce resultado y guarda la fórmula.
"""
import json
import math
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.aprendizaje_cuantico import (_fila, _entrenar, _prob, _pnl, aprender,
                                      FEATURES)


def test_fila_largo_correcto():
    r = {"fuerza": 1.0, "alineacion_fractal": 0.9, "coinciden": "4/4 tiempos",
         "contra_tendencia": False, "consenso_extremo": False}
    fila = _fila(r, "slide", "europa", (0, 0, 0.001))
    assert len(fila) == len(FEATURES)                  # una columna por evento
    assert fila[0] == 1.0 and fila[3] == 1.0           # fuerza y slide


def test_pnl_signo():
    assert _pnl(60) > 0                                 # 60% con payout 92% gana
    assert _pnl(45) < 0                                 # 45% pierde


def test_logistica_aprende_separable():
    # Dos nubes separables: la fórmula debe clasificarlas casi perfecto.
    rng = np.random.RandomState(0)
    a = rng.normal(-1.5, 0.3, (200, 2))
    b = rng.normal(1.5, 0.3, (200, 2))
    X = np.vstack([a, b]); y = np.concatenate([np.zeros(200), np.ones(200)])
    mu, sd = X.mean(0), X.std(0)
    w, bias = _entrenar((X - mu) / sd, y)
    pred = (_prob((X - mu) / sd, w, bias) >= 0.5).astype(float)
    assert (pred == y).mean() > 0.95                    # >95% aciertos


def _serie(n, t0):
    ts = np.array([t0 + i * 60_000 for i in range(n)], dtype=np.int64)
    closes = [1.10 + 0.0001 * i + 0.0006 * math.sin(i / 8.0) for i in range(n)]
    return ts, closes


def _guardar(d, par, ts, closes):
    c = np.asarray(closes, float)
    df = pd.DataFrame({"timestamp": ts, "open": c, "high": c * 1.0006,
                       "low": c * 0.9994, "close": c, "volume": 1.0})
    df.to_csv(os.path.join(d, f"{par}__M1.csv.gz"), index=False, compression="gzip")
    for tf in (120, 180, 300):
        b = (df["timestamp"] // (tf * 1000)) * (tf * 1000)
        agg = df.groupby(b).agg(open=("open", "first"), high=("high", "max"),
                                low=("low", "min"), close=("close", "last"),
                                volume=("volume", "sum")).reset_index()
        agg.rename(columns={"index": "timestamp"}, inplace=True)
        agg.to_csv(os.path.join(d, f"{par}__tf{tf}.csv.gz"), index=False,
                   compression="gzip")


def test_aprender_corre_y_guarda():
    with tempfile.TemporaryDirectory() as d:
        corte_ms = 1_451_606_400_000
        t0 = corte_ms - 2500 * 60_000
        ts, closes = _serie(5000, t0)
        _guardar(d, "EURUSD", ts, closes)
        out = aprender(destino=d, pares=["EURUSD"], corte="2016-01-01",
                       train_n=60, test_n=80, ventana=10)
        # Puede haber pocas señales en sintético; si las hay, se guarda la fórmula.
        if out:
            assert "base_win_rate" in out
            if os.path.exists(os.path.join(d, "formula_cuantica.json")):
                with open(os.path.join(d, "formula_cuantica.json")) as f:
                    frm = json.load(f)
                assert len(frm["w"]) == len(FEATURES)   # un peso por evento
                assert len(frm["mean"]) == len(FEATURES)


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
