"""
bot/test_progreso.py
====================
Valida el reporte de progreso SIN red: cuenta activos completos vs parciales.
"""

import io
import contextlib
import tempfile
import os

from bot.history import HistoryRepository
from bot.progreso import _reporte, COMPLETO_M1


def _velas(n):
    return [{"timestamp": i * 60000, "open": 1.1, "high": 1.1, "low": 1.1,
             "close": 1.1, "volume": 1} for i in range(n)]


def test_reporte_cuenta_completos():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    repo = HistoryRepository(db)
    repo.record_many("EURUSD_otc", "M1", _velas(COMPLETO_M1))     # completo
    repo.record_many("GBPUSD_otc", "M1", _velas(100))             # parcial
    repo.close()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _reporte(db, "OTC")
    salida = buf.getvalue()
    assert "Activos vistos: 2" in salida
    assert "Completos (>=5000 velas 1m): 1" in salida
    assert "parciales:     1" in salida
    os.remove(db)
    print("OK reporte cuenta 2 vistos, 1 completo, 1 parcial")


def test_reporte_vacio_no_rompe():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _reporte(db, "OTC")
    assert "Aún no hay datos" in buf.getvalue()
    os.remove(db)
    print("OK base vacía -> aviso, sin error")


if __name__ == "__main__":
    test_reporte_cuenta_completos()
    test_reporte_vacio_no_rompe()
    print("\nTODOS OK — reporte de progreso")
