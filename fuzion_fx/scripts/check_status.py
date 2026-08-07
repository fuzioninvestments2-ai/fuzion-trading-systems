"""
scripts/check_status.py (fuzion_fx)
===================================
Muestra si los 5 procesos (colector + 4 bots) estan corriendo, segun
logs/pids.json. Usa psutil para un chequeo SEGURO (en Windows, os.kill(pid, 0)
no sirve como "ping": puede matar el proceso; psutil solo consulta).

    python fuzion_fx/scripts/check_status.py
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")


def _vivo(pid: int) -> bool:
    """True si el proceso existe y no es zombie. Seguro (no lo toca)."""
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def main() -> None:
    if not os.path.exists(PIDS_FILE):
        print("Sin pids.json: los bots no fueron arrancados con start_all.py.")
        return
    with open(PIDS_FILE, "r", encoding="utf-8") as f:
        pids = json.load(f)

    print(f"{'PROCESO':<10} {'PID':<8} ESTADO")
    for nombre, pid in pids.items():
        estado = "CORRIENDO" if _vivo(pid) else "DETENIDO"
        print(f"{nombre:<10} {pid:<8} {estado}")


if __name__ == "__main__":
    main()
