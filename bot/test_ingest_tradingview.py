"""
bot/test_ingest_tradingview.py
==============================
Valida el ingestor de CSV de TradingView (sin red): parseo de nombre, mapeo de
timeframe, conversión al formato interno y rechazo de OTC / timeframes inválidos.
"""
import os
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.ingest_tradingview import _par_y_label, ingerir_archivo, LABEL_CLAVE

CSV_TV = """time,open,high,low,close,Volume
2026-06-30T00:00:00Z,1.1000,1.1010,1.0990,1.1005,120
2026-06-30T00:01:00Z,1.1005,1.1012,1.1001,1.1008,98
2026-06-30T00:02:00Z,1.1008,1.1009,1.0995,1.0999,110
"""


def test_par_y_label():
    assert _par_y_label("EURUSD_5m.csv") == ("EURUSD", "5m")
    assert _par_y_label("EUR-USD_1h.csv") == ("EURUSD", "1h")
    assert _par_y_label("GBPJPY_1m.csv.gz") == ("GBPJPY", "1m")
    assert _par_y_label("singuion.csv") == (None, None)


def test_mapeo_timeframes_completo():
    # Los timeframes que opera/estudia el trader deben estar todos.
    for label in ("1m", "2m", "3m", "5m", "15m", "30m", "1h", "4h"):
        assert label in LABEL_CLAVE, f"falta mapeo de {label}"


def test_ingerir_archivo_ok():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "EURUSD_1m.csv")
        with open(src, "w") as f:
            f.write(CSV_TV)
        salida, n = ingerir_archivo(src, destino=d)
        assert n == 3, f"esperaba 3 velas, {n}"
        assert salida.endswith("EURUSD__M1.csv.gz")
        df = pd.read_csv(salida)
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert df["timestamp"].is_monotonic_increasing


def test_rechaza_otc_y_tf_invalido():
    with tempfile.TemporaryDirectory() as d:
        # OTC: sin fuente real → saltado.
        src_otc = os.path.join(d, "EURUSD_OTC_5m.csv")
        with open(src_otc, "w") as f:
            f.write(CSV_TV)
        salida, n = ingerir_archivo(src_otc, destino=d)
        assert n == 0 and salida is None
        # Timeframe no soportado (7m) → saltado.
        src_bad = os.path.join(d, "EURUSD_7m.csv")
        with open(src_bad, "w") as f:
            f.write(CSV_TV)
        salida2, n2 = ingerir_archivo(src_bad, destino=d)
        assert n2 == 0 and salida2 is None


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
