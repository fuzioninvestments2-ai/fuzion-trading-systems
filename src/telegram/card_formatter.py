"""
src/telegram/card_formatter.py
==============================
FASE 2: fachada del formateo de tarjeta de senal en la estructura limpia.

PORQUE: el manual mapea `telegram/card_formatter.py` <- `bot/escaner_reversion.py`.
Ese modulo produce la TARJETA de senal para Telegram (`tarjeta`) ademas de
escanear pares (`escanear`) y resumir operables (`resumen`). Se reexporta al
namespace limpio sin duplicar ni mover el archivo (no rompe los imports
existentes de `bot.escaner_reversion`). `format_card` es alias de `tarjeta`.
"""

from __future__ import annotations

from bot.escaner_reversion import (
    escanear,
    tarjeta,
    resumen,
    VENTANA_ENTRADA_SEG,
)

# Alias con el nombre del namespace limpio; misma funcion (no envuelve nada).
format_card = tarjeta

__all__ = ["format_card", "tarjeta", "escanear", "resumen", "VENTANA_ENTRADA_SEG"]
