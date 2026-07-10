"""
bot/test_reparar_4h.py
======================
Valida lo testeable sin red: conteo de velas (con y sin archivo). La descarga en sí
usa red y se prueba en la PC.
"""
import gzip
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.reparar_4h import _velas


def test_velas_cuenta_sin_cabecera():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "EURUSD__tf14400.csv.gz")
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("1000,1,1,1,1,1\n2000,1,1,1,1,1\n3000,1,1,1,1,1\n")
        assert _velas(p) == 3          # 3 velas, la cabecera no cuenta


def test_velas_archivo_inexistente():
    assert _velas("/no/existe/x.csv.gz") == 0


def test_velas_solo_cabecera():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.csv.gz")
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write("timestamp,open,high,low,close,volume\n")
        assert _velas(p) == 0          # sin filas → 0, no negativo


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
