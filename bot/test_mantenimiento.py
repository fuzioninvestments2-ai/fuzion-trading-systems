"""
bot/test_mantenimiento.py
=========================
Valida sin red la limpieza del historial: borra velas mal alineadas, tiempos no usados
y activos OTC, y conserva las velas buenas.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.history import HistoryRepository
from bot.mantenimiento import limpiar, _seg_de


def test_seg_de():
    assert _seg_de("M1") == 60 and _seg_de("tf300") == 300
    assert _seg_de("raro") is None


def test_limpia_lo_que_no_procede():
    with tempfile.TemporaryDirectory() as d:
        repo = HistoryRepository(os.path.join(d, "h.db"))
        # Buena M1 alineada (ts múltiplo de 60000).
        repo.record_candle("EURUSD", "M1", {"timestamp": 60_000, "open": 1, "high": 1,
                                            "low": 1, "close": 1, "volume": 1})
        # M1 DESALINEADA (ts no múltiplo de 60000) -> se borra.
        repo.record_candle("EURUSD", "M1", {"timestamp": 60_123, "open": 1, "high": 1,
                                            "low": 1, "close": 1, "volume": 1})
        # Tiempo NO usado (tf3600) -> se borra.
        repo.record_candle("EURUSD", "tf3600", {"timestamp": 3_600_000, "open": 1,
                            "high": 1, "low": 1, "close": 1, "volume": 1})
        # Activo OTC en base real -> se borra.
        repo.record_candle("EURUSD_otc", "M1", {"timestamp": 120_000, "open": 1,
                            "high": 1, "low": 1, "close": 1, "volume": 1})

        b = limpiar(repo)
        assert b["desalineadas"] == 1
        assert b["no_usados"] == 1
        assert b["otc"] == 1
        # Solo queda la vela buena.
        assert repo.count() == 1
        df = repo.get_recent("EURUSD", "M1", 10)
        assert len(df) == 1 and int(df["timestamp"].iloc[0]) == 60_000


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
