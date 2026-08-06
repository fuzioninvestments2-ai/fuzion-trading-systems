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

# (nombre, ruta del script). El COLECTOR va primero: es la unica conexion a PO
# y llena po_candles.db; los bots leen de ahi. Todos son procesos independientes.
PROCESOS = [("collector", os.path.join(ROOT, "collector", "po_collector.py"))]
PROCESOS += [(b, os.path.join(ROOT, "bots", f"{b}.py")) for b in BOTS]


def main() -> None:
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    pids = {}
    for nombre, script in PROCESOS:
        # Proceso hijo independiente; su salida va a su propio log.
        proc = subprocess.Popen([sys.executable, script],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        pids[nombre] = proc.pid
        print(f"[start] {nombre} -> PID {proc.pid}")

    with open(PIDS_FILE, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)
    print(f"PIDs guardados en {PIDS_FILE}")
    print("Colector + 4 bots corriendo. check_status.py para verlos.")


if __name__ == "__main__":
    main()
