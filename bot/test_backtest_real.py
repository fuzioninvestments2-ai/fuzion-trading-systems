"""
bot/test_backtest_real.py
=========================
Valida lo testeable sin red del backtest REAL: mapeo de claves, anti look-ahead al
armar frames, resolución del expiry con huecos, break-even, y una corrida completa
de `backtest_par` sobre datos sintéticos. La corrida sobre los 27GB reales se hace
en la PC.
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

from bot.backtest_real import (_clave, _frames_en, _salida_idx, _wr, BREAKEVEN,
                               backtest_par, correr)


def _df(ts_ms, closes):
    """DataFrame OHLC mínimo a partir de timestamps (ms) y cierres."""
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"timestamp": np.asarray(ts_ms, dtype=np.int64),
                         "open": c, "high": c * 1.0005, "low": c * 0.9995,
                         "close": c, "volume": 1.0})


def _serie_m1(n, t0=1_700_000_000_000):
    """n velas M1 sintéticas: tendencia suave + onda (da dirección a los indicadores)."""
    ts = np.array([t0 + i * 60_000 for i in range(n)], dtype=np.int64)
    closes = [1.10 + 0.0001 * i + 0.0005 * math.sin(i / 10.0) for i in range(n)]
    return ts, closes


def _resample(ts_ms, closes, tf_seg):
    """Agrega M1 a velas de tf_seg (alineado por bloque), para generar tiempos largos."""
    df = _df(ts_ms, closes)
    bloque = (df["timestamp"] // (tf_seg * 1000)) * (tf_seg * 1000)
    agg = df.groupby(bloque).agg(open=("open", "first"), high=("high", "max"),
                                 low=("low", "min"), close=("close", "last"),
                                 volume=("volume", "sum"))
    agg.index.name = "timestamp"
    return agg.reset_index()


def test_clave_mapea_m1_y_tf():
    assert _clave(60) == "M1"
    assert _clave(300) == "tf300"
    assert _clave(14400) == "tf14400"


def test_breakeven_92():
    assert abs(BREAKEVEN - 52.083) < 0.01          # 1/(1+0.92)*100


def test_frames_en_anti_lookahead():
    # 60s: 10 velas. En T = cierre de la vela que empieza en t0+5*60000, solo deben
    # entrar velas YA cerradas (inicio <= T - 60000). Nada del futuro.
    ts = np.array([i * 60_000 for i in range(10)], dtype=np.int64)
    datos = {60: (ts, _df(ts, [1.0] * 10))}
    T = int(ts[5]) + 60_000                         # cierre de la vela índice 5
    frames = _frames_en(datos, T, ventana=80)
    assert 60 in frames
    # cutoff = T - 60000 = ts[5]; searchsorted 'right' incluye la vela 5, excluye la 6+.
    assert int(frames[60]["timestamp"].max()) == int(ts[5])
    assert int(frames[60]["timestamp"].max()) < int(ts[6])   # el futuro NO entra


def test_frames_en_tiempo_largo_cierra_tarde():
    # Una vela de 300s no está cerrada hasta inicio+300s: a T pequeño no debe entrar.
    ts60 = np.array([i * 60_000 for i in range(20)], dtype=np.int64)
    r300 = _resample(ts60, [1.0] * 20, 300)
    ts300 = r300["timestamp"].to_numpy(dtype=np.int64)
    datos = {300: (ts300, r300)}
    T = int(ts300[0]) + 200_000                      # antes de cerrar la 1ª vela de 5m
    frames = _frames_en(datos, T, ventana=80)
    assert 300 not in frames or len(frames.get(300, [])) == 0  # aún nada cerrado


def test_salida_idx_hueco_devuelve_none():
    ts = np.array([0, 60_000, 120_000, 10_000_000], dtype=np.int64)  # hueco grande
    assert _salida_idx(ts, 180_000, tol_ms=120_000) is None          # no hay vela cerca
    assert _salida_idx(ts, 120_000, tol_ms=120_000) == 2             # exacta
    assert _salida_idx(ts, 999_999_999, tol_ms=120_000) is None      # fuera de rango


def test_wr_margen():
    wr, margen, n = _wr(60, 40)
    assert n == 100 and abs(wr - 60.0) < 1e-9 and margen > 0
    assert _wr(0, 0) == (None, None, 0)


def test_backtest_par_corre_sin_red():
    with tempfile.TemporaryDirectory() as d:
        ts, closes = _serie_m1(1500)
        _df(ts, closes).to_csv(os.path.join(d, "EURUSD__M1.csv.gz"),
                               index=False, compression="gzip")
        # Tiempos largos derivados del mismo M1 (para que el motor tenga varios paneles).
        for tf in (120, 180, 300):
            _resample(ts, closes, tf).to_csv(
                os.path.join(d, f"EURUSD__tf{tf}.csv.gz"),
                index=False, compression="gzip")

        res = backtest_par("EURUSD", destino=d, max_decisiones=120,
                           expiries=(60, 180))
        assert res is not None
        assert res["par"] == "EURUSD"
        assert res["decisiones"] > 0
        assert res["señales"] >= 0
        for e in (60, 180):
            w, l, emp = res["exp"][e]
            assert w + l + emp <= res["señales"]     # resueltas nunca exceden señales
            assert w >= 0 and l >= 0 and emp >= 0


def test_backtest_par_sin_m1_devuelve_none():
    with tempfile.TemporaryDirectory() as d:
        ts, closes = _serie_m1(300)
        _resample(ts, closes, 300).to_csv(
            os.path.join(d, "EURUSD__tf300.csv.gz"), index=False, compression="gzip")
        assert backtest_par("EURUSD", destino=d) is None   # sin M1 -> None


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
