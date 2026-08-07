"""
scripts/stop_all.py (fuzion_fx)
===============================
Detiene los 5 procesos (colector + 4 bots) usando los PIDs de start_all.py.
Usa psutil.terminate() (cross-platform y seguro).

    python fuzion_fx/scripts/stop_all.py
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")


def main() -> None:
    if not os.path.exists(PIDS_FILE):
        print("No hay pids.json; no se lanzaron bots con start_all.py?")
        return
    with open(PIDS_FILE, "r", encoding="utf-8") as f:
        pids = json.load(f)

    try:
        import psutil
    except Exception:
        print("Falta psutil. Instalalo con: pip install psutil")
        return

    for nombre, pid in pids.items():
        try:
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                p.terminate()                    # pide cierre; si no, se mata
                try:
                    p.wait(timeout=5)
                except psutil.TimeoutExpired:
                    p.kill()
                print(f"[stop] {nombre} (PID {pid}) detenido")
            else:
                print(f"[stop] {nombre} (PID {pid}) ya no corria")
        except Exception as e:
            print(f"[stop] {nombre} (PID {pid}) no se pudo detener: {e}")

    os.remove(PIDS_FILE)


if __name__ == "__main__":
    main()
