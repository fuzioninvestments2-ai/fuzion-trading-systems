"""
src/indicators/candle_patterns.py
=================================
FASE 2: fachada de patrones de velas en la estructura limpia.

PORQUE: el manual mapea `indicators/candle_patterns.py` <- `bot/candle_patterns.py`.
Reexporta el detector de patrones real al namespace limpio sin duplicar ni mover
el archivo (no rompe los imports existentes de `bot.candle_patterns`).
"""

from __future__ import annotations

from bot.candle_patterns import detect_patterns, CALL, PUT

__all__ = ["detect_patterns", "CALL", "PUT"]
