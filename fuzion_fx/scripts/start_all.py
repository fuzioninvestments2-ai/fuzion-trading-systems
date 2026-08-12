"""
scripts/start_all.py (fuzion_fx)
================================
Arranca el colector + los 4 bots como PROCESOS INDEPENDIENTES (uno por timeframe)
y guarda sus PIDs en logs/pids.json. Cada uno corre en su propio proceso (sin
hilos), tal como pide la arquitectura.

Expone helpers (PROCESOS, lanzar_proceso, leer_pids, guardar_pids) para que el
vigilante (scripts/vigilante.py) reutilice el MISMO arranque sin duplicarlo.

    python fuzion_fx/scripts/start_all.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, os.path.dirname(_AQUI))     # para 'scripts.*'

from scripts.servicios import SERVICIOS, POR_NOMBRE, ROOT      # noqa: E402

PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")

# Compatibilidad: lista (nombre, script) derivada del registro unico.
PROCESOS = [(s["nombre"], s["script"]) for s in SERVICIOS]
SCRIPT_DE = POR_NOMBRE                              # nombre -> servicio (con args)


def _kwargs() -> dict:
    """Lanzar DESACOPLADO de la consola (los procesos siguen vivos aunque se
    cierre la ventana). Su salida va a DEVNULL (cada bot ya escribe su log)."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP)
    return kwargs


def lanzar_proceso(script: str, args=None) -> int:
    """Lanza un script Python desacoplado (con args opcionales) y devuelve su PID."""
    proc = subprocess.Popen([sys.executable, script, *(args or [])], **_kwargs())
    return proc.pid


def lanzar_servicio(nombre: str) -> int:
    """Lanza un servicio del registro por su nombre (usa su script y args)."""
    s = POR_NOMBRE[nombre]
    return lanzar_proceso(s["script"], s["args"])


def leer_pids() -> dict:
    """Lee logs/pids.json ({nombre: pid}); {} si no existe o esta corrupto."""
    try:
        with open(PIDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): int(v) for k, v in data.items()}
    except (OSError, ValueError, TypeError):
        return {}


def guardar_pids(pids: dict) -> None:
    os.makedirs(os.path.dirname(PIDS_FILE), exist_ok=True)
    with open(PIDS_FILE, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)


def main() -> None:
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    pids = {}
    for s in SERVICIOS:
        pids[s["nombre"]] = lanzar_servicio(s["nombre"])
        print(f"[start] {s['nombre']} -> PID {pids[s['nombre']]}")
    guardar_pids(pids)
    print(f"PIDs guardados en {PIDS_FILE}")
    print(f"{len(SERVICIOS)} servicios corriendo (colector + 4 bots + panel).")


if __name__ == "__main__":
    main()
