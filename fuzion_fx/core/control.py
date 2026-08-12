"""
core/control.py (fuzion_fx)
===========================
Estado de CONTROL compartido entre el panel y los bots (config/control.json).
Hoy: pausa global de señales. El panel lo escribe; los 4 bots lo leen cada pasada.

Por que un archivo: los bots son procesos independientes; un archivo sqlite/json
compartido es la via simple para que un boton del panel afecte a los 4 sin
acoplarlos. PAUSA = no emitir (NO mata procesos): reversible y no pelea con el
vigilante (que revive procesos muertos).

Sin red. Robusto: si el archivo no existe o esta mal, se asume NO pausado.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_PATH = os.path.join(ROOT, "config", "control.json")


def leer_control(path: Optional[str] = None) -> Dict[str, Any]:
    """Estado de control ({pausado: bool}). {} si no hay archivo o esta corrupto."""
    path = path or CONTROL_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def esta_pausado(path: Optional[str] = None) -> bool:
    """True si las señales estan en PAUSA (los bots no emiten)."""
    return bool(leer_control(path).get("pausado", False))


def set_pausado(valor: bool, path: Optional[str] = None) -> None:
    """Escribe la pausa global. Crea la carpeta si falta."""
    path = path or CONTROL_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pausado": bool(valor)}, f)
