"""
scripts/start_all.py (fuzion_fx)
================================
Arranca los 4 bots como PROCESOS INDEPENDIENTES (uno por timeframe) y guarda sus
PIDs en logs/pids.json. Cada bot corre en su propio proceso (sin hilos, sin
matrix), tal como pide la arquitectura.

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


def main() -> None:
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    pids = {}
    for bot in BOTS:
        script = os.path.join(ROOT, "bots", f"{bot}.py")
        # Proceso hijo independiente; su salida va a su propio log (base_bot ya
        # escribe a logs/<bot>.log), aca solo lanzamos y guardamos el PID.
        proc = subprocess.Popen([sys.executable, script],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        pids[bot] = proc.pid
        print(f"[start] {bot} -> PID {proc.pid}")

    with open(PIDS_FILE, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)
    print(f"PIDs guardados en {PIDS_FILE}")


if __name__ == "__main__":
    main()
