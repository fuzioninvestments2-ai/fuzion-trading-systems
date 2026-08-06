"""
scripts/check_status.py (fuzion_fx)
===================================
Muestra si los 4 bots estan corriendo (segun logs/pids.json).

    python fuzion_fx/scripts/check_status.py
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> None:
    if not os.path.exists(PIDS_FILE):
        print("Sin pids.json: los bots no fueron arrancados con start_all.py.")
        return
    with open(PIDS_FILE, "r", encoding="utf-8") as f:
        pids = json.load(f)

    print(f"{'BOT':<8} {'PID':<8} ESTADO")
    for bot, pid in pids.items():
        estado = "CORRIENDO" if _vivo(pid) else "DETENIDO"
        print(f"{bot:<8} {pid:<8} {estado}")


if __name__ == "__main__":
    main()
