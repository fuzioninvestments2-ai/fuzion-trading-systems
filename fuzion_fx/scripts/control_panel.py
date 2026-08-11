"""
scripts/control_panel.py (fuzion_fx)
====================================
APP DE ESCRITORIO (una sola ventana con botones) para operar Fuzion FX sin tocar
la terminal: ARRANCAR TODO, DETENER TODO, ESTADO y GENERAR RESUMEN AHORA.

Unifica el colector + los 4 bots + el scheduler del resumen en un solo panel.
Usa Tkinter (viene con Python, no se instala nada). Los procesos se lanzan
DESACOPLADOS (siguen vivos aunque cierres la ventana) y se rastrean por
logs/pids.json (mismo formato que start_all.py).

CUIDADO clave: no arranca un 2º colector si ya hay uno vivo (Pocket Option
permite una sola conexion por SSID); por eso 'arrancar' saltea lo que ya corre.

    python fuzion_fx/scripts/control_panel.py      (o pythonw, sin consola)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# fuzion_fx/ al path (para core/, scripts/).
FUZION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FUZION_ROOT not in sys.path:
    sys.path.insert(0, FUZION_ROOT)

from core.config import bot_ids                                   # noqa: E402
from scripts.daily_summary_scheduler import (                     # noqa: E402
    procesar_bot, TZ_UTC4, RESUM_DIR)

ROOT = FUZION_ROOT
PIDS_FILE = os.path.join(ROOT, "logs", "pids.json")

# Orden de arranque: el COLECTOR primero (unica conexion a PO), luego los 4 bots,
# y por ultimo el scheduler del resumen diario. Todos procesos independientes.
PROCESOS: List[Tuple[str, str]] = [
    ("collector", os.path.join(ROOT, "collector", "po_collector.py"))]
PROCESOS += [(b, os.path.join(ROOT, "bots", f"{b}.py")) for b in bot_ids()]
PROCESOS += [("resumen", os.path.join(ROOT, "scripts",
                                      "daily_summary_scheduler.py"))]


# --------------------------------------------------------------- procesos (logica)
def _vivo(pid: int) -> bool:
    """True si el PID existe y no es zombie. Seguro (psutil solo consulta)."""
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def _cargar_pids() -> Dict[str, int]:
    if not os.path.exists(PIDS_FILE):
        return {}
    try:
        with open(PIDS_FILE, "r", encoding="utf-8") as f:
            return {k: int(v) for k, v in json.load(f).items()}
    except Exception:
        return {}


def _guardar_pids(pids: Dict[str, int]) -> None:
    os.makedirs(os.path.dirname(PIDS_FILE), exist_ok=True)
    with open(PIDS_FILE, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)


def _spawn(script: str) -> int:
    """Lanza un script Python DESACOPLADO de la ventana. Devuelve el PID."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen([sys.executable, script], **kwargs).pid


def arrancar_procesos() -> str:
    """Arranca lo que NO este vivo (no duplica el colector). Devuelve un reporte."""
    pids = _cargar_pids()
    lineas = []
    for nombre, script in PROCESOS:
        if nombre in pids and _vivo(pids[nombre]):
            lineas.append(f"  ya corria: {nombre} (PID {pids[nombre]})")
            continue
        try:
            pid = _spawn(script)
            pids[nombre] = pid
            lineas.append(f"  arrancado: {nombre} -> PID {pid}")
        except Exception as e:
            lineas.append(f"  ERROR al arrancar {nombre}: {e}")
    _guardar_pids(pids)
    return "ARRANCAR TODO:\n" + "\n".join(lineas)


def detener_procesos() -> str:
    """Detiene todos los procesos rastreados. Devuelve un reporte."""
    pids = _cargar_pids()
    if not pids:
        return "DETENER TODO:\n  no habia procesos rastreados (pids.json vacio)."
    try:
        import psutil
    except Exception:
        return "DETENER TODO:\n  falta psutil (pip install psutil)."
    lineas = []
    for nombre, pid in pids.items():
        try:
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=5)
                except psutil.TimeoutExpired:
                    p.kill()
                lineas.append(f"  detenido: {nombre} (PID {pid})")
            else:
                lineas.append(f"  ya no corria: {nombre} (PID {pid})")
        except Exception as e:
            lineas.append(f"  ERROR al detener {nombre}: {e}")
    try:
        os.remove(PIDS_FILE)
    except OSError:
        pass
    return "DETENER TODO:\n" + "\n".join(lineas)


def estado_procesos() -> str:
    """Reporte de que procesos estan CORRIENDO / DETENIDOS."""
    pids = _cargar_pids()
    if not pids:
        return "ESTADO:\n  sin pids.json: nada arrancado todavia."
    lineas = []
    for nombre, _ in PROCESOS:
        pid = pids.get(nombre)
        if pid is None:
            lineas.append(f"  {nombre:<10} ---     NO LANZADO")
        else:
            estado = "CORRIENDO" if _vivo(pid) else "DETENIDO"
            lineas.append(f"  {nombre:<10} {pid:<8} {estado}")
    return "ESTADO:\n" + "\n".join(lineas)


def generar_resumen_hoy() -> str:
    """
    Genera AHORA el resumen del dia EN CURSO (00:00 UTC-4 -> ahora) para los 4
    bots: guarda el .md y lo manda al Telegram de cada bot. Util para ver el dia
    sin esperar a medianoche.
    """
    ahora = datetime.now(TZ_UTC4)
    inicio_dt = datetime(ahora.year, ahora.month, ahora.day, tzinfo=TZ_UTC4)
    inicio, fin = int(inicio_dt.timestamp()), int(ahora.timestamp())
    fecha = inicio_dt.date().isoformat()
    lineas = []
    for bot_id in bot_ids():
        try:
            path = procesar_bot(bot_id, inicio, fin, fecha)
            lineas.append(f"  {bot_id}: {os.path.basename(path)}")
        except Exception as e:
            lineas.append(f"  ERROR {bot_id}: {e}")
    return (f"RESUMEN DE HOY ({fecha}) generado y enviado a Telegram:\n"
            + "\n".join(lineas) + f"\n  Carpeta: {RESUM_DIR}")


# --------------------------------------------------------------- GUI (Tkinter)
def main() -> None:
    import threading
    import tkinter as tk
    from tkinter.scrolledtext import ScrolledText

    ventana = tk.Tk()
    ventana.title("FUZION FX — Panel de control")
    ventana.geometry("560x460")
    ventana.configure(bg="#0f1116")

    tk.Label(ventana, text="FUZION FX", bg="#0f1116", fg="#e6e6e6",
             font=("Segoe UI", 18, "bold")).pack(pady=(12, 0))
    tk.Label(ventana, text="Demo · señales educativas · el acierto no está garantizado",
             bg="#0f1116", fg="#8a8f98", font=("Segoe UI", 9)).pack(pady=(0, 10))

    salida = ScrolledText(ventana, height=12, bg="#0b0d12", fg="#c8f7c5",
                          font=("Consolas", 10), relief="flat")
    salida.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def log(texto: str) -> None:
        salida.insert("end", texto + "\n\n")
        salida.see("end")

    def correr(fn) -> None:
        """Corre una accion en un hilo para no congelar la ventana."""
        def _worker():
            try:
                res = fn()
            except Exception as e:                 # nunca tumbar la ventana
                res = f"ERROR: {e}"
            ventana.after(0, lambda: log(res))
        threading.Thread(target=_worker, daemon=True).start()

    botones = tk.Frame(ventana, bg="#0f1116")
    botones.pack(pady=(0, 12))

    def boton(txt, color, cmd, col):
        b = tk.Button(botones, text=txt, command=cmd, width=20, height=2,
                      bg=color, fg="white", font=("Segoe UI", 10, "bold"),
                      relief="flat", activebackground=color, cursor="hand2")
        b.grid(row=col // 2, column=col % 2, padx=6, pady=6)
        return b

    boton("▶  ARRANCAR TODO", "#1f8b4c", lambda: correr(arrancar_procesos), 0)
    boton("■  DETENER TODO", "#c0392b", lambda: correr(detener_procesos), 1)
    boton("🔄  ESTADO", "#2c6fbb", lambda: correr(estado_procesos), 2)
    boton("📋  RESUMEN AHORA", "#8e44ad", lambda: correr(generar_resumen_hoy), 3)

    log("Bienvenido. Toca ARRANCAR TODO para poner en marcha el colector, los 4 "
        "bots y el resumen diario.\nToca ESTADO para ver que esta corriendo.")
    ventana.mainloop()


if __name__ == "__main__":
    main()
