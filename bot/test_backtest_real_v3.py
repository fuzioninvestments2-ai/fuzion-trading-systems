"""
bot/test_backtest_real_v3.py
============================
Valida sin red las piezas de v3: sesión por hora, conteo de confirmados, elección y
aplicación de la regla afinada, y una corrida de `backtest_par_v3` sobre datos
sintéticos que cruzan el corte train/test.
"""
import math
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.backtest_real_v3 import (_sesion, _n_conf, _elegir_regla, _aplicar_regla,
                                  _wr_de, backtest_par_v3)


def test_sesion_por_hora():
    assert _sesion(3) == "asia"
    assert _sesion(9) == "europa"
    assert _sesion(15) == "eeuu"
    assert _sesion(22) == "tarde"


def test_n_conf_parsea():
    assert _n_conf("5/5 tiempos") == 5
    assert _n_conf("3/3 tiempos") == 3
    assert _n_conf("") == 0                                 # vacío -> 0, no revienta


def _s(reg, ses, fractal, r):
    return {"reg": reg, "sesion": ses, "fractal": fractal, "n_conf": 4,
            "exp": {180: r}}


def test_elegir_y_aplicar_regla():
    # 'slide' gana (muchas W), 'oscillate' pierde. La regla debe quedarse con slide.
    train = ([_s("slide", "europa", 0.95, "W") for _ in range(30)]
             + [_s("slide", "europa", 0.95, "L") for _ in range(5)]
             + [_s("oscillate", "asia", 0.80, "L") for _ in range(30)])
    regla = _elegir_regla(train, 180)
    assert "slide" in regla["reg"]                          # slide gana en train
    assert "oscillate" not in regla["reg"]                  # oscillate no

    test = [_s("slide", "europa", 0.95, "W"), _s("oscillate", "asia", 0.80, "L")]
    filtradas = _aplicar_regla(test, regla)
    assert all(s["reg"] == "slide" for s in filtradas)      # solo deja slide


def test_aplicar_regla_vacia_no_filtra_por_ese_eje():
    regla = {"reg": set(), "sesion": set(), "fractal": 0.0}
    test = [_s("slide", "asia", 0.5, "W"), _s("oscillate", "eeuu", 0.99, "L")]
    assert len(_aplicar_regla(test, regla)) == 2            # sin regla -> pasa todo


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


def test_backtest_par_v3_corre_sin_red():
    with tempfile.TemporaryDirectory() as d:
        corte_ms = 1_451_606_400_000
        t0 = corte_ms - 2000 * 60_000
        ts, closes = _serie(4000, t0)
        _guardar(d, "EURUSD", ts, closes)
        res = backtest_par_v3("EURUSD", destino=d, corte="2016-01-01", ventana=10,
                              train_n=40, test_n=60, expiries=(60, 180))
        assert res is not None
        assert "regla" in res and isinstance(res["test"], list)
        assert isinstance(res["test_regla"], list)
        assert len(res["test_regla"]) <= len(res["test"])   # afinar nunca añade


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
