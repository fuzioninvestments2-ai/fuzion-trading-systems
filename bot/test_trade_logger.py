"""
bot/test_trade_logger.py
========================
Prueba del registro SQLite (Regla 4). Usa una base de datos EN MEMORIA para no
crear archivos ni depender del disco.

Verifica:
  (A) Se registran operaciones y las estadísticas cuadran.
  (B) Se registra una sesión.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.trade_logger import TradeLogger


def test_trades_y_estadisticas():
    logger = TradeLogger(":memory:")     # base de datos en RAM
    # 3 ganadas, 1 perdida.
    logger.log_trade({"asset": "EURUSD_otc", "direction": "CALL", "amount": 2,
                      "result": "win", "profit": 1.84, "confidence": 0.8})
    logger.log_trade({"asset": "EURUSD_otc", "direction": "PUT", "amount": 2,
                      "result": "win", "profit": 1.84, "confidence": 0.7})
    logger.log_trade({"asset": "EURUSD_otc", "direction": "CALL", "amount": 2,
                      "result": "loss", "profit": -2.0, "confidence": 0.65})
    logger.log_trade({"asset": "EURUSD_otc", "direction": "CALL", "amount": 2,
                      "result": "win", "profit": 1.84, "confidence": 0.9})

    stats = logger.get_statistics()
    assert stats["total_trades"] == 4, stats
    assert stats["wins"] == 3 and stats["losses"] == 1, stats
    assert abs(stats["win_rate"] - 0.75) < 1e-9, stats
    # profit = 1.84*3 - 2.0 = 3.52
    assert abs(stats["total_profit"] - 3.52) < 1e-6, stats
    print("✅ (A) Operaciones registradas y estadísticas correctas:", stats)


def test_registro_de_sesion():
    logger = TradeLogger(":memory:")
    sid = logger.log_session({"start_time": "t0", "end_time": "t1",
                              "target_profit": 5.0, "actual_profit": 5.8,
                              "total_trades": 7, "wins": 7, "losses": 0,
                              "win_rate": 1.0, "stop_reason": "target"})
    assert sid == 1, "❌ Debía insertar la sesión con id 1"
    print("✅ (B) Sesión registrada correctamente.")


if __name__ == "__main__":
    test_trades_y_estadisticas()
    test_registro_de_sesion()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
