"""
bot/test_otc_bot.py
===================
Prueba de validación del orquestador OTC (Regla 4).

Verifica:
  (A) El guardia DESCARTA señales con deriva > 500 ms y EMITE las válidas.
  (B) Un error en la estrategia NO tumba el bot (Catch-All por tick).
  (C) Smoke-test: la simulación completa corre de principio a fin y devuelve
      estadísticas coherentes.

Para (A) y (B) inyectamos dependencias FALSAS (fakes), lo que es posible gracias
al diseño SOLID por inyección. Así la prueba es determinista y no depende de que
la estrategia real produzca señales sobre datos aleatorios.
"""

import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.otc_bot import OTCSignalBot
from validation.timestamp_guard import TimestampGuard
from strategy.confluence import CALL, NONE


def _silent_logger():
    """Logger que no escribe a ningún sitio (para no ensuciar en las pruebas)."""
    logger = logging.getLogger("otc_bot_test")
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.CRITICAL)
    return logger


class _FakeStrategyAlwaysCall:
    """Estrategia falsa: siempre devuelve CALL (para aislar la lógica del bot)."""
    def update(self, price):
        return CALL


class _FakeStrategyExplota:
    """Estrategia falsa que lanza una excepción (para probar el Catch-All)."""
    def update(self, price):
        raise RuntimeError("fallo simulado en la estrategia")


# "Ahora" fijo para el guardia -> prueba determinista (ms desde época).
NOW = 1_000_000.0


def test_descartar_y_emitir():
    guard = TimestampGuard(max_drift_ms=500.0, now_ms_provider=lambda: NOW)
    bot = OTCSignalBot(_FakeStrategyAlwaysCall(), guard, _silent_logger(),
                       simulated=True)

    # Tick 1: deriva 100 ms -> dentro de umbral -> debe EMITIR.
    s1 = bot.on_tick(price=100.0, broker_ts_ms=NOW - 100)
    # Tick 2: deriva 1200 ms -> fuera de umbral -> debe DESCARTAR.
    s2 = bot.on_tick(price=101.0, broker_ts_ms=NOW - 1200)

    assert s1 == CALL, f"❌ El primer tick debía emitir CALL, dio {s1}"
    assert s2 == NONE, f"❌ El segundo tick debía descartarse, dio {s2}"
    assert bot.stats["emitidas"] == 1, "❌ Debía emitirse exactamente 1 señal"
    assert bot.stats["descartadas_por_deriva"] == 1, "❌ Debía descartarse 1"
    print("✅ (A) Emite señal válida y descarta la de deriva alta.")


def test_catch_all_no_tumba_el_bot():
    guard = TimestampGuard(max_drift_ms=500.0, now_ms_provider=lambda: NOW)
    bot = OTCSignalBot(_FakeStrategyExplota(), guard, _silent_logger(),
                       simulated=True)
    # La estrategia lanza excepción; on_tick debe capturarla y devolver NONE.
    s = bot.on_tick(price=100.0, broker_ts_ms=NOW)
    assert s == NONE, f"❌ Ante un error debía devolver NONE, dio {s}"
    assert bot.stats["ticks"] == 1, "❌ El tick debía contarse igualmente"
    print("✅ (B) Un error en la estrategia NO tumba el bot (Catch-All).")


def test_simulacion_completa():
    # Importamos aquí para reutilizar el feed real del entry point.
    from bot.run_simulado import main
    stats = main(n_ticks=300, seed=7)
    # Coherencia: emitidas = calls + puts; ticks procesados = 300.
    assert stats["ticks"] == 300, "❌ Deberían procesarse 300 ticks"
    assert stats["emitidas"] == stats["calls"] + stats["puts"], \
        "❌ Las emitidas no cuadran con calls+puts"
    print("✅ (C) Simulación completa coherente:", stats)


if __name__ == "__main__":
    test_descartar_y_emitir()
    test_catch_all_no_tumba_el_bot()
    test_simulacion_completa()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
