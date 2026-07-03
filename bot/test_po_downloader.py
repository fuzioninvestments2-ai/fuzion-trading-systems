"""
bot/test_po_downloader.py
========================
Valida el descargador de historial OTC (sin red): conversión de velas de la
librería a formato del bot, claves por temporalidad, y guardado con un cliente
falso. La descarga real (BinaryOptionsToolsV2) se prueba en la máquina del usuario.
"""

import asyncio

from bot.po_history_downloader import _to_candles, _tf_key, download_asset
from bot.history import HistoryRepository


def test_tf_key():
    assert _tf_key(60) == "M1"
    assert _tf_key(300) == "tf300"
    assert _tf_key(1800) == "tf1800"
    print("OK claves por temporalidad (60->M1, resto->tf<seg>)")


def test_to_candles_segundos():
    velas = [{"time": 1700000000, "open": 1.1, "high": 1.12, "low": 1.09,
              "close": 1.11}, {"time": 1700000060, "open": 1.11, "high": 1.13,
              "low": 1.10, "close": 1.12}]
    filas = _to_candles(velas)
    assert len(filas) == 2
    assert filas[0]["timestamp"] == 1700000000 * 1000     # seg -> ms
    assert filas[0]["close"] == 1.11
    print("OK convierte velas (tiempo en segundos -> ms)")


def test_to_candles_ignora_malas():
    velas = [{"time": 1, "open": 1}, "basura", {"time": 2, "open": 1,
             "high": 1, "low": 1, "close": 1}]
    filas = _to_candles(velas)
    assert len(filas) == 1                                # solo la completa
    print("OK ignora velas incompletas/basura")


def test_download_asset_guarda():
    repo = HistoryRepository(":memory:")

    class _FakeClient:
        async def get_candles(self, asset, period, offset):
            # Devuelve 5 velas para cualquier temporalidad.
            return [{"time": 1700000000 + i * offset, "open": 1.1, "high": 1.1,
                     "low": 1.1, "close": 1.1} for i in range(5)]

    total = asyncio.run(download_asset(_FakeClient(), repo, "EURUSD_otc",
                                       dias_por_tf={60: 1, 300: 1}))
    assert total == 10
    assert repo.count("EURUSD_otc", "M1") == 5
    assert repo.count("EURUSD_otc", "tf300") == 5
    print("OK descarga y guarda por temporalidad en la BD del bot")


if __name__ == "__main__":
    test_tf_key()
    test_to_candles_segundos()
    test_to_candles_ignora_malas()
    test_download_asset_guarda()
    print("\nTODOS OK — descargador de historial OTC (BinaryOptionsToolsV2)")
