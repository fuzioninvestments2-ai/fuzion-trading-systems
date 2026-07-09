"""
bot/test_dukascopy_deep.py
==========================
Valida lo testeable sin red: mapeo de intervalos y la fusión/dedup/guardado por
chunks (concatena ventanas, quita duplicados por timestamp, ordena, guarda .csv.gz).
"""
import gzip
import os
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.dukascopy_deep import INTERVALOS, _fusionar_guardar, COLS


def _df(ts_list):
    return pd.DataFrame({"timestamp": ts_list, "open": 1.1, "high": 1.2,
                         "low": 1.0, "close": 1.15, "volume": 1.0})


def test_intervalos_cubren_1m_a_4h():
    claves = {c for _, c in INTERVALOS}
    for c in ("M1", "tf300", "tf600", "tf900", "tf1800", "tf3600", "tf14400"):
        assert c in claves, f"falta {c}"


def test_fusion_dedup_y_orden():
    with tempfile.TemporaryDirectory() as d:
        # Dos chunks con un timestamp solapado (debe quedar una sola fila).
        c1 = _df([3000, 1000, 2000])
        c2 = _df([2000, 4000])            # 2000 duplicado
        salida = os.path.join(d, "EURUSD__M1.csv.gz")
        n = _fusionar_guardar([c1, c2], salida)
        assert n == 4, f"esperaba 4 velas unicas, {n}"
        with gzip.open(salida, "rt") as f:
            df = pd.read_csv(f)
        assert list(df.columns) == COLS
        assert df["timestamp"].tolist() == [1000, 2000, 3000, 4000]   # ordenado, sin dup


def test_fusion_vacia():
    with tempfile.TemporaryDirectory() as d:
        assert _fusionar_guardar([], os.path.join(d, "x.csv.gz")) == 0


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
