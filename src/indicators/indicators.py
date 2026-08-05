"""
src/indicators/indicators.py
============================
FASE 2: fachada de los indicadores/votacion en la estructura limpia.

PORQUE: el manual mapea `indicators/indicators.py` <- `bot/scoring_strategy.py`.
Reexporta la estrategia de scoring (8 indicadores que votan) y sus utilidades de
pesos por tiempo/regimen al namespace limpio, sin duplicar la logica ni mover el
archivo (no rompe los imports existentes de `bot.scoring_strategy`).
"""

from __future__ import annotations

from bot.scoring_strategy import (
    ScoringStrategy,
    weights_for,
    regime,
    compression,
    BASE_WEIGHTS,
    CALL,
    PUT,
    HOLD,
)

__all__ = [
    "ScoringStrategy", "weights_for", "regime", "compression",
    "BASE_WEIGHTS", "CALL", "PUT", "HOLD",
]
