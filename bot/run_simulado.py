"""
bot/run_simulado.py
===================
Arranque del bot OTC en MODO SIMULADO.

Uso:
    python3 bot/run_simulado.py

Genera un feed de precios SIMULADO (paseo aleatorio) y lo pasa por la estrategia
y el guardia de timestamp. NO se conecta a Pocket Option ni se envía ninguna
orden: es 100% seguro para entender el sistema.
"""

import os
import random
import sys
import time

# Permite ejecutar el archivo directamente: añade la raíz del proyecto al path
# para poder importar los paquetes `bot`, `strategy`, `validation`.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.otc_bot import OTCSignalBot, setup_logger
from strategy.confluence import ConfluenceStrategy, StrategyConfig
from validation.timestamp_guard import TimestampGuard


def simulated_feed(n_ticks, seed=None, stale_every=37):
    """
    Feed SIMULADO (no es Pocket Option). Produce (precio, timestamp_broker_ms).

    El precio sigue un PASEO ALEATORIO: precio_t = precio_(t-1) + ruido. ¿Por
    qué? Porque es el modelo más honesto de un precio impredecible; NO tiene un
    patrón que la estrategia pueda "acertar" artificialmente (a diferencia de
    una senoidal, que daría métricas engañosamente buenas).

    Cada `stale_every` ticks inyectamos un timestamp DESFASADO (1.2 s) para
    comprobar EN VIVO que el guardia de timestamp descarta esas señales.
    """
    rng = random.Random(seed)          # RNG local reproducible (sin globales)
    price = 100.0
    for i in range(n_ticks):
        price += rng.uniform(-0.5, 0.5)
        now_ms = time.time() * 1000.0
        if stale_every and i > 0 and i % stale_every == 0:
            broker_ts = now_ms - 1200.0           # deriva > 500 ms a propósito
        else:
            broker_ts = now_ms - rng.uniform(0, 100)   # deriva pequeña normal
        yield price, broker_ts


def main(n_ticks=500, seed=42):
    logger = setup_logger()
    strategy = ConfluenceStrategy(StrategyConfig())
    guard = TimestampGuard(max_drift_ms=500.0)     # reloj real del sistema
    bot = OTCSignalBot(strategy, guard, logger, simulated=True)

    stats = bot.run(simulated_feed(n_ticks, seed=seed))

    print("Resumen de la simulación (MODO SIMULADO, sin órdenes reales):")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return stats


if __name__ == "__main__":
    main()
