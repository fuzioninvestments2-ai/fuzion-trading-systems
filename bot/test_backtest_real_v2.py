"""
bot/test_backtest_real_v2.py
============================
Valida sin red las piezas nuevas de la v2: conversión de fecha a epoch ms, el filtro
`_vetar` (mercado plano veta; tendencia limpia no), win-rate por lista, y una corrida
completa de `backtest_par_v2` sobre datos sintéticos que cruzan el corte train/test.
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

from bot.backtest_real_v2 import (_fecha_ms, _vetar, _wr_de, backtest_par_v2,
                                  GRID_CONF)


def _ohlc(ts, o, h, l, c):
    return pd.DataFrame({"timestamp": np.asarray(ts, dtype=np.int64),
                         "open": o, "high": h, "low": l, "close": c, "volume": 1.0})


def test_fecha_ms_conocidas():
    assert _fecha_ms("1970-01-01") == 0
    assert _fecha_ms("2016-01-01") == 1_451_606_400_000     # epoch conocido
    assert _fecha_ms("2003-01-01") == 1_041_379_200_000


def test_vetar_mercado_plano():
    # 80 velas idénticas: rango 0 -> plano -> veta.
    ts = [i * 60_000 for i in range(80)]
    p = [1.10] * 80
    frames = {60: _ohlc(ts, p, p, p, p)}
    assert _vetar(frames) is True


def test_vetar_tendencia_limpia_no_veta():
    # Tendencia alcista con velas marubozu limpias: hay recorrido, sin doji ni
    # manipulación -> NO veta.
    ts = [i * 60_000 for i in range(80)]
    o = [1.10 + 0.0001 * i for i in range(80)]
    c = [1.10 + 0.0001 * (i + 1) for i in range(80)]
    h = [max(a, b) for a, b in zip(o, c)]
    lo = [min(a, b) for a, b in zip(o, c)]
    frames = {60: _ohlc(ts, o, h, lo, c)}
    assert _vetar(frames) is False


def test_vetar_sin_frame_60():
    assert _vetar({}) is False                              # sin 1m no puede vetar


def test_wr_de_cuenta_solo_wl():
    senales = [{"exp": {180: "W"}}, {"exp": {180: "L"}}, {"exp": {180: "W"}},
               {"exp": {180: "E"}}, {"exp": {180: None}}]
    wr, margen, n = _wr_de(senales, 180)
    assert n == 3                                           # E y None no cuentan
    assert abs(wr - 66.666) < 0.1


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
        bloque = (df["timestamp"] // (tf * 1000)) * (tf * 1000)
        agg = df.groupby(bloque).agg(open=("open", "first"), high=("high", "max"),
                                     low=("low", "min"), close=("close", "last"),
                                     volume=("volume", "sum")).reset_index()
        agg.rename(columns={"index": "timestamp"}, inplace=True)
        agg.to_csv(os.path.join(d, f"{par}__tf{tf}.csv.gz"), index=False,
                   compression="gzip")


def test_backtest_par_v2_train_test_sin_red():
    with tempfile.TemporaryDirectory() as d:
        # Serie que cruza 2016-01-01: 2000 velas antes (train) y 2000 después (test).
        corte_ms = 1_451_606_400_000
        t0 = corte_ms - 2000 * 60_000
        ts, closes = _serie(4000, t0)
        _guardar(d, "EURUSD", ts, closes)

        res = backtest_par_v2("EURUSD", destino=d, corte="2016-01-01", ventana=10,
                              train_n=40, test_n=60, expiries=(60, 180))
        assert res is not None
        assert res["min_conf"] in GRID_CONF or res["min_conf"] == 0.18
        assert isinstance(res["senales"], list)
        for s in res["senales"]:                            # estructura de cada señal
            assert s["lado"] in (1, -1)
            assert 0.0 <= s["fuerza"] <= 1.0
            assert set(s["exp"].keys()) == {60, 180}


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
