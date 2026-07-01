"""
bot/run_motor_sim.py
====================
Simulador del MOTOR COMPLETO (sin red, sin dinero, sin credenciales).

Enlaza todas las piezas ya validadas:
    config -> ticks simulados -> velas (OHLC) -> estrategia -> riesgo -> sesión

Sirve para VER el motor entero funcionando de punta a punta y de forma segura.

⚠️ HONESTIDAD SOBRE LA SIMULACIÓN:
El resultado de cada operación aquí es una MONEDA AL AIRE 50/50 (no hay ventaja
real, porque un mercado simulado no se puede "predecir"). Con payout < 100%, a la
larga eso da PÉRDIDA — es a propósito: demuestra que ni un motor bonito gana
dinero sobre datos sin ventaja. NO tomes estos números como prueba de nada.
"""

import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.config import get_preset
from bot.candles import CandleBuilder
from bot.scoring_strategy import ScoringStrategy
from bot.risk_manager import RiskManager
from bot.session import SessionManager


def synthetic_ticks(n_ticks, seed=0, ticks_per_candle=3):
    """
    Precio oscilante (seno + ruido) para que la estrategia tenga oportunidades
    de disparar señales en los extremos. Cada vela recibe `ticks_per_candle`.
    """
    rng = random.Random(seed)
    tf_ms = 60_000                                   # velas de 1 min
    step = tf_ms // ticks_per_candle
    ts = 0
    for i in range(n_ticks):
        # Onda suave + ruido: crea sobrecompra/sobreventa periódicas.
        price = 100.0 + 3.0 * math.sin(i / 25.0) + rng.uniform(-0.4, 0.4)
        yield price, ts
        ts += step


def run(preset="moderado", seed=7, n_ticks=3000):
    cfg = get_preset(preset)
    rng = random.Random(seed + 999)                  # RNG para el "resultado"
    logger = None                                    # silencioso en consola

    # Componentes del motor.
    cb = CandleBuilder(cfg.timeframe_seconds())
    strategy = ScoringStrategy(cfg)
    risk = RiskManager(cfg)
    # execute_fn: moneda al aire (resultado honesto, sin ventaja real).
    execute_fn = lambda signal, amount: rng.random() < 0.5
    session = SessionManager(cfg, strategy, risk, execute_fn, logger, payout=0.92)

    sessions_done = 0
    resúmenes = []
    session.start()

    for price, ts in synthetic_ticks(n_ticks, seed=seed):
        closed = cb.add_tick(price, ts)
        if closed is None:
            continue                                 # aún se forma la vela
        session.on_candle(cb.to_dataframe())
        if not session.active:                       # sesión terminó
            resúmenes.append(session.summary())
            sessions_done += 1
            if cfg.auto_restart and sessions_done < cfg.max_sessions_per_day:
                session.start()
            else:
                break

    # Si la simulación acabó con la sesión aún activa, guardamos su estado.
    if session.active:
        resúmenes.append(session.summary())

    return {"preset": preset, "sesiones": len(resúmenes), "detalle": resúmenes}


def main():
    print("=" * 60)
    print("SIMULACIÓN DEL MOTOR COMPLETO (moneda al aire 50/50 — sin ventaja)")
    print("=" * 60)
    for preset in ("conservador", "moderado", "agresivo"):
        res = run(preset=preset)
        print(f"\nPreset: {preset}  ->  {res['sesiones']} sesión(es)")
        for i, r in enumerate(res["detalle"], 1):
            print(f"  Sesión {i}: {r}")
    print("\nRecuerda: esto NO predice ganancias reales. Es solo el motor "
          "funcionando de punta a punta.")


if __name__ == "__main__":
    main()
