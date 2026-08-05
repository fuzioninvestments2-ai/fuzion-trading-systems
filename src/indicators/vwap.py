"""
src/indicators/vwap.py
======================
FASE 2: fachada del VWAP en la estructura limpia.

PORQUE: el manual mapea `indicators/vwap.py` <- `bot/vwap.py`. Reexporta el
calculo del VWAP y su voto al namespace limpio sin duplicar ni mover el archivo
(no rompe los imports existentes de `bot.vwap`).
"""

from __future__ import annotations

from bot.vwap import vwap, vwap_signal, CALL, PUT, HOLD

__all__ = ["vwap", "vwap_signal", "CALL", "PUT", "HOLD"]
