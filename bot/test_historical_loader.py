"""
bot/test_historical_loader.py
============================
Valida el cargador de historial REAL (sin red): mapeo de tickers, conversión de
DataFrame a velas, y que rechaza OTC. La descarga real (yfinance) se prueba en la
máquina del usuario.
"""

import pandas as pd

from bot.historical_loader import (yf_ticker, _df_to_candles, load_real_history,
                                   PO_TO_YF)
from bot.history import HistoryRepository


def test_mapeo_de_tickers():
    assert yf_ticker("EURUSD") == "EURUSD=X"
    assert yf_ticker("BTCUSD") == "BTC-USD"
    assert yf_ticker("XAUUSD") == "GC=F"
    # Tolera formatos con barra/espacios/otc.
    assert yf_ticker("EUR/USD") == "EURUSD=X"
    assert yf_ticker("desconocido_xyz") is None
    print("OK mapeo de tickers PO -> Yahoo Finance")


def test_df_a_velas_columnas_simples():
    idx = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 00:01:00"], utc=True)
    df = pd.DataFrame({"Open": [1.10, 1.11], "High": [1.12, 1.13],
                       "Low": [1.09, 1.10], "Close": [1.11, 1.12],
                       "Volume": [100, 200]}, index=idx)
    velas = _df_to_candles(df)
    assert len(velas) == 2
    assert velas[0]["open"] == 1.10 and velas[0]["close"] == 1.11
    assert velas[0]["timestamp"] == int(idx[0].timestamp() * 1000)
    print("OK convierte DataFrame (columnas simples) a velas")


def test_df_a_velas_multiindex():
    # yfinance a veces devuelve columnas MultiIndex (campo, ticker).
    idx = pd.to_datetime(["2024-01-01 00:00:00"], utc=True)
    df = pd.DataFrame({("Open", "EURUSD=X"): [1.10], ("High", "EURUSD=X"): [1.12],
                       ("Low", "EURUSD=X"): [1.09], ("Close", "EURUSD=X"): [1.11],
                       ("Volume", "EURUSD=X"): [100]}, index=idx)
    velas = _df_to_candles(df)
    assert len(velas) == 1 and velas[0]["high"] == 1.12
    print("OK convierte DataFrame (MultiIndex) a velas")


def test_rechaza_otc():
    repo = HistoryRepository(":memory:")
    # OTC no tiene fuente externa real -> devuelve 0, no guarda nada.
    assert load_real_history("EURUSD_otc", repo) == 0
    print("OK rechaza activos OTC (sin fuente externa real)")


def test_guarda_en_repo_via_conversion():
    # Simula el guardado (sin yfinance) usando _df_to_candles + record_many.
    repo = HistoryRepository(":memory:")
    idx = pd.date_range("2024-01-01", periods=50, freq="5min", tz="UTC")
    df = pd.DataFrame({"Open": 1.1, "High": 1.11, "Low": 1.09, "Close": 1.10,
                       "Volume": 1}, index=idx)
    repo.record_many("EURUSD", "tf300", _df_to_candles(df))
    assert repo.count("EURUSD", "tf300") == 50
    print("OK las velas convertidas se guardan en la BD (tf300)")


if __name__ == "__main__":
    test_mapeo_de_tickers()
    test_df_a_velas_columnas_simples()
    test_df_a_velas_multiindex()
    test_rechaza_otc()
    test_guarda_en_repo_via_conversion()
    print("\nTODOS OK — cargador de historial REAL (yfinance)")
