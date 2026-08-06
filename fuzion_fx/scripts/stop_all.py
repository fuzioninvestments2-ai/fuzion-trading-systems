"""
scripts/stop_all.py (fuzion_fx)
===============================
Detiene los 4 bots usando los PIDs guardados por start_all.py.

    python fuzion_fx/scripts/stop_all.py
"""

from __future__ import annotations

import json
import os
import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")


def _vivo(pid: int) -> bool:
    """True si el proceso existe (señal 0 no mata, solo comprueba)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> None:
    if not os.path.exists(PIDS_FILE):
        print("No hay pids.json; no se lanzaron bots con start_all.py?")
        return
    with open(PIDS_FILE, "r", encoding="utf-8") as f:
        pids = json.load(f)

    for bot, pid in pids.items():
        if _vivo(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"[stop] {bot} (PID {pid}) detenido")
            except OSError as e:
                print(f"[stop] {bot} (PID {pid}) no se pudo detener: {e}")
        else:
            print(f"[stop] {bot} (PID {pid}) ya no corria")

    os.remove(PIDS_FILE)


if __name__ == "__main__":
    main()
