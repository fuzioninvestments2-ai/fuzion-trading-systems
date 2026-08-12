"""
scripts/servicios.py (fuzion_fx)
================================
REGISTRO UNICO de servicios del sistema. Aca se define TODO lo que arranca y se
supervisa: el colector, los 4 bots y el panel. El Centro de Control y el vigilante
leen de aca; para CRECER (auto-optimizador, feed de noticias, alertas, un bot
nuevo) se agrega UNA entrada a esta lista, sin tocar el resto.

Cada servicio:
  nombre     -> id unico (y clave en logs/pids.json)
  script     -> ruta absoluta del .py que se lanza
  args       -> argumentos extra (lista)
  supervisar -> True: el vigilante lo mantiene vivo (lo reinicia si se cae)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # fuzion_fx/
_BOTS = ["f1_m1", "f2_m2", "f3_m3", "f4_m5"]


def _svc(nombre: str, ruta_rel, args=None, supervisar: bool = True) -> Dict[str, Any]:
    return {"nombre": nombre, "script": os.path.join(ROOT, *ruta_rel),
            "args": list(args or []), "supervisar": supervisar}


SERVICIOS: List[Dict[str, Any]] = [
    _svc("collector", ("collector", "po_collector.py")),
    *[_svc(b, ("bots", f"{b}.py")) for b in _BOTS],
    # El panel se supervisa igual que los bots; corre sin abrir navegador (la
    # ventana la abre el Centro de Control). Si se cae, el vigilante lo revive.
    _svc("panel", ("dashboard", "server.py"), args=["--no-open"]),
]

# Mapa nombre -> servicio (para relanzar por nombre).
POR_NOMBRE: Dict[str, Dict[str, Any]] = {s["nombre"]: s for s in SERVICIOS}


def supervisados() -> List[Dict[str, Any]]:
    """Servicios que el vigilante debe mantener vivos."""
    return [s for s in SERVICIOS if s["supervisar"]]
