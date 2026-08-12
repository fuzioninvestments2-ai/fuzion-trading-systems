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


def _python_exe() -> str:
    """
    Ejecutable python.exe (NO pythonw.exe) para lanzar los servicios. El vigilante
    corre bajo pythonw (sin ventana); si lanzara los servicios con pythonw, se
    caen (sin stdout/consola valida). Con python.exe + DETACHED_PROCESS corren SIN
    ventana igual, y estables (asi lo hacia start_all, que funcionaba horas).
    """
    exe = sys.executable or "python"
    if os.name == "nt" and os.path.basename(exe).lower() == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(cand):
            return cand
    return exe


def _kwargs(salida) -> dict:
    """Lanzar DESACOPLADO de la consola. `salida` = destino de stdout/stderr
    (DEVNULL o un archivo). Redirigir a archivo captura el traceback si el proceso
    crashea al arrancar (con DEVNULL se perdia)."""
    kwargs = {"stdout": salida, "stderr": salida}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP)
    return kwargs


def lanzar_proceso(script: str, args=None, err_path=None) -> int:
    """
    Lanza un script Python desacoplado con python.exe (no pythonw), sin ventana.
    Redirige stdout/stderr a `err_path` (si se da) para CAPTURAR cualquier crash
    de arranque; si no, a DEVNULL. Devuelve el PID.
    """
    salida = subprocess.DEVNULL
    fh = None
    if err_path:
        try:
            fh = open(err_path, "a", encoding="utf-8")
            salida = fh
        except OSError:
            salida = subprocess.DEVNULL
    try:
        proc = subprocess.Popen([_python_exe(), script, *(args or [])],
                                **_kwargs(salida))
    finally:
        if fh is not None:
            fh.close()                     # el hijo ya tiene su propia copia del fd
    return proc.pid


def lanzar_servicio(nombre: str) -> int:
    """Lanza un servicio del registro por su nombre. Su salida (y crashes) van a
    logs/<nombre>.err para poder diagnosticar."""
    s = POR_NOMBRE[nombre]
    err = os.path.join(ROOT, "logs", f"{nombre}.err")
    os.makedirs(os.path.dirname(err), exist_ok=True)
    return lanzar_proceso(s["script"], s["args"], err_path=err)


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
