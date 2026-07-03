"""
bot/test_tradingview_import.py
==============================
Valida SIN red el parseo del CSV exportado de TradingView (UNIX e ISO) y el
guardado en la BD, además del rechazo de activos OTC.
"""

import os
import tempfile

from bot.history import HistoryRepository
from bot.tradingview_import import parse_tv_csv, _a_ms, import_tv_file


def test_a_ms_acepta_unix_e_iso():
    assert _a_ms("1700000000") == 1700000000 * 1000       # unix segundos -> ms
    assert _a_ms("1700000000000") == 1700000000000        # ya en ms
    assert _a_ms("2024-01-31") == _a_ms("2024-01-31T00:00:00+00:00")
    assert _a_ms("") is None and _a_ms("abc") is None
    print("OK _a_ms acepta unix, ms e ISO; rechaza vacío/basura")


def test_parse_unix():
    csv_txt = ("time,open,high,low,close,Volume\n"
               "1700000000,1.10,1.12,1.09,1.11,100\n"
               "1700000060,1.11,1.13,1.10,1.12,120\n")
    velas = parse_tv_csv(csv_txt)
    assert len(velas) == 2
    assert velas[0]["timestamp"] == 1700000000 * 1000
    assert velas[0]["open"] == 1.10 and velas[0]["close"] == 1.11
    assert velas[1]["volume"] == 120
    print("OK parsea CSV con tiempo UNIX")


def test_parse_iso_y_columnas_desordenadas():
    # 'date' en vez de 'time', y columnas en otro orden.
    csv_txt = ("close,open,date,high,low\n"
               "1.11,1.10,2024-01-31,1.12,1.09\n")
    velas = parse_tv_csv(csv_txt)
    assert len(velas) == 1
    assert velas[0]["open"] == 1.10 and velas[0]["high"] == 1.12
    print("OK parsea ISO y columnas desordenadas")


def test_cabecera_no_reconocible_no_rompe():
    assert parse_tv_csv("foo,bar\n1,2\n") == []
    print("OK cabecera desconocida -> lista vacía sin error")


def test_import_guarda_y_rechaza_otc():
    repo = HistoryRepository(":memory:")
    fd, ruta = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("time,open,high,low,close,Volume\n"
                "1700000000,1.10,1.12,1.09,1.11,100\n")
    n = import_tv_file("EURUSD", "tf3600", ruta, repo)
    assert n == 1 and repo.count("EURUSD", "tf3600") == 1
    # OTC se rechaza (no hay fuente real externa).
    assert import_tv_file("EURUSD_otc", "tf3600", ruta, repo) == 0
    os.remove(ruta)
    print("OK importa a la BD y rechaza OTC")


if __name__ == "__main__":
    test_a_ms_acepta_unix_e_iso()
    test_parse_unix()
    test_parse_iso_y_columnas_desordenadas()
    test_cabecera_no_reconocible_no_rompe()
    test_import_guarda_y_rechaza_otc()
    print("\nTODOS OK — importador de CSV de TradingView")
