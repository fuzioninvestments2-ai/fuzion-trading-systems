"""
src/core/connection_manager.py
==============================
FASE 2: fachada del cliente de conexion en la estructura limpia.

PORQUE: el manual mapea `core/connection_manager.py` <- `bot/pocket_client.py`.
Reexporta el cliente websocket real (con su reconexion automatica, Regla 3) al
namespace limpio sin duplicar ni mover el archivo, para no romper los imports
existentes de `bot.pocket_client`. `ConnectionManager` es alias del cliente real.
"""

from __future__ import annotations

from bot.pocket_client import (
    PocketOptionClient,
    URL_DEMO,
    URL_REAL,
)

# Alias con el nombre del namespace limpio; es la MISMA clase (no subclase),
# asi el comportamiento y la reconexion son identicos.
ConnectionManager = PocketOptionClient

__all__ = ["ConnectionManager", "PocketOptionClient", "URL_DEMO", "URL_REAL"]
