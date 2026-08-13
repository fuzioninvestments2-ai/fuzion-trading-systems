"""
core/control.py (fuzion_fx)
===========================
Estado de CONTROL compartido entre el panel y los bots (config/control.json).
- pausado: pausa GLOBAL de senales (los bots no emiten).
- telegram: por bot (f1_m1..f4_m5) si su tarjeta se MANDA a Telegram (True/False).
  Asi el dueno elige recibir 1, 2, 3 o las 4 temporalidades sin apagar los bots.

El panel lo escribe; los 4 bots lo leen cada pasada. Un archivo (no acople): los
bots son procesos independientes. Robusto: si falta o esta mal, se asume el
default seguro (no pausado, todas las temporalidades a Telegram).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_PATH = os.path.join(ROOT, "config", "control.json")


def leer_control(path: Optional[str] = None) -> Dict[str, Any]:
    """Estado de control completo. {} si no hay archivo o esta corrupto."""
    path = path or CONTROL_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir(data: Dict[str, Any], path: Optional[str] = None) -> None:
    path = path or CONTROL_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ------------------------------------------------------------- pausa global
def esta_pausado(path: Optional[str] = None) -> bool:
    return bool(leer_control(path).get("pausado", False))


def set_pausado(valor: bool, path: Optional[str] = None) -> None:
    """Pausa/reanuda sin pisar el resto del estado (telegram, etc.)."""
    data = leer_control(path)
    data["pausado"] = bool(valor)
    _escribir(data, path)


# ------------------------------------------------- telegram por temporalidad
def telegram_activo(bot_id: str, path: Optional[str] = None) -> bool:
    """True si el bot manda su tarjeta a Telegram (default True)."""
    tg = leer_control(path).get("telegram", {})
    return bool(tg.get(bot_id, True)) if isinstance(tg, dict) else True


def set_telegram(bot_id: str, valor: bool, path: Optional[str] = None) -> None:
    """Activa/desactiva Telegram de UNA temporalidad, sin tocar el resto."""
    data = leer_control(path)
    tg = data.get("telegram", {})
    if not isinstance(tg, dict):
        tg = {}
    tg[str(bot_id)] = bool(valor)
    data["telegram"] = tg
    _escribir(data, path)


def estado_telegram(bots, path: Optional[str] = None) -> Dict[str, bool]:
    """{bot_id: activo} para la lista de bots dada (para el panel)."""
    tg = leer_control(path).get("telegram", {})
    tg = tg if isinstance(tg, dict) else {}
    return {b: bool(tg.get(b, True)) for b in bots}


# ------------------------------------------------- modo (lento / normal / rapido)
def get_modo(path: Optional[str] = None) -> str:
    """
    Modo de agresividad del sistema: 'rapido' (mas entradas), 'normal' o 'lento'
    (menos, mas exigentes). El panel lo escribe; los bots lo leen cada pasada y
    ajustan umbral de convergencia, confirmaciones y cadencia. Default 'rapido':
    el usuario quiere que el bot ENCUENTRE entradas.
    """
    m = str(leer_control(path).get("modo", "rapido")).lower()
    return m if m in ("rapido", "normal", "lento") else "rapido"


# ---------------------------------------- candado de emision (una a la vez, global)
def get_emitir_despues_de(path: Optional[str] = None) -> float:
    """
    Epoch a partir del cual se puede emitir la PROXIMA señal. Compartido por los 4
    bots: mientras hay una señal en curso + el descanso, todos callan (señales
    ORDENADAS, de a una). 0 = libre.
    """
    try:
        return float(leer_control(path).get("emitir_despues_de", 0) or 0)
    except (ValueError, TypeError):
        return 0.0


def set_emitir_despues_de(ts: float, path: Optional[str] = None) -> None:
    """Fija cuando se habilita la proxima emision (sin pisar el resto del estado)."""
    data = leer_control(path)
    data["emitir_despues_de"] = float(ts)
    _escribir(data, path)


def set_modo(valor: str, path: Optional[str] = None) -> None:
    """
    Cambia el modo (lento/normal/rapido) sin pisar el resto del estado. Un valor
    INVALIDO se IGNORA (no se toca el modo actual): asi un cliente con un valor
    corrupto no fuerza el modo mas permisivo sin que el usuario lo pida.
    """
    v = str(valor).lower()
    if v not in ("rapido", "normal", "lento"):
        return                                 # invalido -> no cambiar nada
    data = leer_control(path)
    data["modo"] = v
    _escribir(data, path)
