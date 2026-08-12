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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # fuzion_fx/
BOTS = ["f1_m1", "f2_m2", "f3_m3", "f4_m5"]
PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")

# (nombre, ruta del script). El COLECTOR va primero: es la unica conexion a PO
# y llena po_candles.db; los bots leen de ahi. Todos son procesos independientes.
PROCESOS = [("collector", os.path.join(ROOT, "collector", "po_collector.py"))]
PROCESOS += [(b, os.path.join(ROOT, "bots", f"{b}.py")) for b in BOTS]

# Mapa nombre -> script (para relanzar por nombre desde el vigilante).
SCRIPT_DE = {nombre: script for nombre, script in PROCESOS}


def _kwargs() -> dict:
    """Lanzar DESACOPLADO de la consola (los procesos siguen vivos aunque se
    cierre la ventana). Su salida va a DEVNULL (cada bot ya escribe su log)."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP)
    return kwargs


def lanzar_proceso(script: str) -> int:
    """Lanza un script Python desacoplado y devuelve su PID."""
    proc = subprocess.Popen([sys.executable, script], **_kwargs())
    return proc.pid


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
    for nombre, script in PROCESOS:
        pids[nombre] = lanzar_proceso(script)
        print(f"[start] {nombre} -> PID {pids[nombre]}")
    guardar_pids(pids)
    print(f"PIDs guardados en {PIDS_FILE}")
    print("Colector + 4 bots corriendo. check_status.py para verlos.")


if __name__ == "__main__":
    main()
