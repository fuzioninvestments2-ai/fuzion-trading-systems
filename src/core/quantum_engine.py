"""
src/core/quantum_engine.py
==========================
FASE 2: fachada del Motor Cuantico en la estructura limpia.

PORQUE: el manual mapea `core/quantum_engine.py` <- `bot/cuantico.py`. En vez de
DUPLICAR el motor (Regla 1: no duplicar) o mover el archivo de golpe (romperia los
~40 imports existentes de `bot.cuantico`), este modulo REEXPORTA la API estable
del motor real. Asi el codigo nuevo puede importar desde el namespace limpio
(`src.core.quantum_engine`) mientras el bot sigue usando `bot.cuantico`. Cuando
toda la base migre, se invierte la dependencia sin sobresaltos.

No hay logica propia aqui: es un punto de entrada unico y tipado al motor.
"""

from __future__ import annotations

from typing import Any, Dict

from bot.cuantico import (
    GRUPOS,
    TIMEFRAMES_9,
    TOTAL_TF,
    PROB_MIN,
    CONV_MIN,
    PROB_MIN_PAYOUT_BAJO,
    calculate_timeframe_signal,
    calculate_quantum_probability,
    calculate_logarithmic_convergence,
    validate_signal_90,
    display_timeframe_panel,
)

__all__ = [
    "GRUPOS", "TIMEFRAMES_9", "TOTAL_TF", "PROB_MIN", "CONV_MIN",
    "PROB_MIN_PAYOUT_BAJO", "calculate_timeframe_signal",
    "calculate_quantum_probability", "calculate_logarithmic_convergence",
    "validate_signal_90", "display_timeframe_panel", "evaluate",
]


def evaluate(frames: Dict[int, Any], payout: float = None,
             hora_utc: int = None) -> Dict[str, Any]:
    """
    Punto de entrada de alto nivel del motor: dado el diccionario de velas por
    timeframe, devuelve la decision final (operar/no + probabilidad/convergencia).

    Envuelve `validate_signal_90` con un nombre en ingles acorde al namespace
    limpio; la logica y las formulas viven en `bot/cuantico.py`.
    """
    return validate_signal_90(frames, payout=payout, hora_utc=hora_utc)
