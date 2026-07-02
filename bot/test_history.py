"""
bot/test_history.py
===================
Prueba del repositorio de historial (Regla 4), con base de datos EN MEMORIA.

Verifica:
  (A) Se guardan velas y se recuperan en orden cronológico.
  (B) No se duplican (misma vela dos veces = una sola).
  (C) Los conteos y el resumen por activo funcionan.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.history import HistoryRepository


def _candle(ts, o, h, l, c, v=1):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c,
            "volume": v}


def test_guardar_y_recuperar():
    repo = HistoryRepository(":memory:")
    repo.record_candle("EUR/USD OTC", "M1", _candle(0, 10, 12, 9, 11))
    repo.record_candle("EUR/USD OTC", "M1", _candle(60000, 11, 13, 10, 12))
    repo.record_candle("EUR/USD OTC", "M1", _candle(120000, 12, 14, 11, 13))

    df = repo.get_recent("EUR/USD OTC", "M1")
    assert len(df) == 3, df
    # Orden cronológico: la primera fila es la más antigua (ts=0).
    assert df["timestamp"].iloc[0] == 0 and df["timestamp"].iloc[-1] == 120000
    assert df["close"].iloc[-1] == 13
    print("✅ (A) Velas guardadas y recuperadas en orden correcto.")


def test_no_duplica():
    repo = HistoryRepository(":memory:")
    # Misma vela (mismo ts) dos veces -> debe quedar una sola.
    repo.record_candle("BTC/USD OTC", "M5", _candle(0, 100, 101, 99, 100))
    repo.record_candle("BTC/USD OTC", "M5", _candle(0, 100, 105, 98, 104))
    assert repo.count("BTC/USD OTC", "M5") == 1, "❌ No debía duplicar la vela"
    # Y debe quedarse con la última versión (close=104).
    assert repo.get_recent("BTC/USD OTC", "M5")["close"].iloc[-1] == 104
    print("✅ (B) No duplica velas (reemplaza por timestamp).")


def test_resumen():
    repo = HistoryRepository(":memory:")
    repo.record_many("EUR/USD OTC", "M1",
                     [_candle(i * 60000, 10, 11, 9, 10) for i in range(5)])
    repo.record_many("Gold OTC", "M5",
                     [_candle(i * 300000, 20, 21, 19, 20) for i in range(3)])
    assert repo.count() == 8
    resumen = repo.assets_tracked()
    assert {"asset": "EUR/USD OTC", "timeframe": "M1", "velas": 5} in resumen
    print("✅ (C) Conteos y resumen por activo correctos:", resumen)


if __name__ == "__main__":
    test_guardar_y_recuperar()
    test_no_duplica()
    test_resumen()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
