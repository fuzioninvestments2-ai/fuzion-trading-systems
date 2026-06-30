"""
bot/test_run_demo.py
====================
Prueba de validación del runner de demo (Regla 4), con un cliente SIMULADO.

No hay red ni SSID: inyectamos un MockClient que entrega precios predefinidos.
Así validamos TODO el cableado (conectar -> leer -> decidir -> registrar) salvo
la conexión real al servidor de Pocket Option, que no se puede probar sin tu
SSID y acceso a sus servidores.

Verifica:
  (A) El runner conecta, lee N precios y procesa N ticks.
  (B) NUNCA se envían órdenes (place_order no se llama jamás).
  (C) Si el cliente trae timestamp del bróker, el guardia lo usa para descartar
      señales con deriva alta.
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.run_demo import LiveDemoRunner
from bot.otc_bot import OTCSignalBot
from validation.timestamp_guard import TimestampGuard
from strategy.confluence import CALL, NONE


class _MD:
    """MarketData mínimo (solo lo que usa el runner)."""
    def __init__(self, last, timestamp=""):
        self.last = last
        self.timestamp = timestamp


class _MockClient:
    """
    Cliente falso: 'conecta' sin red y devuelve precios de una lista. Registra
    si alguien intenta enviar una orden (para probar que NUNCA ocurre).
    """
    def __init__(self, prices, timestamps=None):
        self._prices = list(prices)
        self._timestamps = list(timestamps) if timestamps else None
        self._i = 0
        self.connected = False
        self.orders_enviadas = 0

    async def connect(self):
        self.connected = True
        return True

    async def get_market_data(self, symbol):
        # Entrega el siguiente precio; al agotarse, repite el último.
        i = min(self._i, len(self._prices) - 1)
        ts = ""
        if self._timestamps is not None:
            ts = self._timestamps[min(self._i, len(self._timestamps) - 1)]
        self._i += 1
        return _MD(self._prices[i], timestamp=ts)

    async def place_order(self, order):
        # Si esto se llamara, sería un fallo de seguridad en modo demo/lectura.
        self.orders_enviadas += 1
        raise AssertionError("❌ No se deben enviar órdenes en modo lectura")


def _silent_logger():
    import logging
    lg = logging.getLogger("live_demo_test")
    lg.addHandler(logging.NullHandler())
    lg.setLevel(logging.CRITICAL)
    return lg


class _FakeStrategyAlwaysCall:
    def update(self, price):
        return CALL


NOW = 1_000_000.0


async def test_lee_y_procesa():
    client = _MockClient(prices=[100, 101, 102, 103, 104])
    guard = TimestampGuard(500.0, now_ms_provider=lambda: NOW)
    bot = OTCSignalBot(_FakeStrategyAlwaysCall(), guard, _silent_logger(),
                       simulated=True)
    runner = LiveDemoRunner(client, bot, "TEST_otc", poll_interval=0,
                            max_ticks=5, logger=_silent_logger(),
                            now_ms_provider=lambda: NOW)
    stats = await runner.run()

    assert client.connected, "❌ El runner debía conectar"
    assert stats["ticks"] == 5, f"❌ Debía procesar 5 ticks, fueron {stats['ticks']}"
    assert client.orders_enviadas == 0, "❌ No debió enviarse ninguna orden"
    print("✅ (A) Conecta, lee 5 precios y procesa 5 ticks.")
    print("✅ (B) Cero órdenes enviadas (modo solo lectura).")


async def test_guardia_con_timestamp_del_broker():
    # Esta vez el cliente SÍ trae timestamp del bróker: el guardia debe actuar.
    # Tick 0: ts = NOW-100 (deriva 100 -> permitido).
    # Tick 1: ts = NOW-1200 (deriva 1200 -> descartado).
    client = _MockClient(prices=[100, 101],
                         timestamps=[str(NOW - 100), str(NOW - 1200)])
    guard = TimestampGuard(500.0, now_ms_provider=lambda: NOW)
    bot = OTCSignalBot(_FakeStrategyAlwaysCall(), guard, _silent_logger(),
                       simulated=True)
    runner = LiveDemoRunner(client, bot, "TEST_otc", poll_interval=0,
                            max_ticks=2, logger=_silent_logger(),
                            now_ms_provider=lambda: NOW)
    stats = await runner.run()

    assert stats["emitidas"] == 1, f"❌ Debía emitirse 1, fueron {stats['emitidas']}"
    assert stats["descartadas_por_deriva"] == 1, \
        f"❌ Debía descartarse 1, fueron {stats['descartadas_por_deriva']}"
    print("✅ (C) Con timestamp del broker, el guardia descarta la deriva alta.")


if __name__ == "__main__":
    asyncio.run(test_lee_y_procesa())
    asyncio.run(test_guardia_con_timestamp_del_broker())
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
