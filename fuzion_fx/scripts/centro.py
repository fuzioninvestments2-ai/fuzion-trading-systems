"""
scripts/centro.py (fuzion_fx) — CENTRO DE CONTROL unificado
===========================================================
UN SOLO arranque para TODO el sistema:
  1) AUTO-ACTUALIZA el codigo (git pull) — implementacion automatica, best-effort.
  2) Levanta el VIGILANTE (que arranca y mantiene vivos colector + 4 bots + panel,
     leyendo el registro de servicios; crecer = agregar una entrada a servicios.py).
  3) Abre la ventana de la APP (panel) si se pide.

Pensado para el lanzador FUZION.vbs (doble clic). Robusto: si algo falla (sin red,
sin git), NO frena el arranque del sistema.

    python fuzion_fx/scripts/centro.py            # actualiza + arranca + abre app
    python fuzion_fx/scripts/centro.py --no-app   # sin abrir ventana
    python fuzion_fx/scripts/centro.py --no-update # sin git pull
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

_AQUI = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_AQUI) not in sys.path:
    sys.path.insert(0, os.path.dirname(_AQUI))

from scripts.servicios import ROOT                              # noqa: E402
from scripts.start_all import lanzar_servicio, leer_pids        # noqa: E402
from scripts.vigilante import vigilante_ya_corriendo            # noqa: E402

REPO = os.path.dirname(ROOT)                                    # raiz del repo (con .git)
PANEL_URL = "http://127.0.0.1:8770"
log = logging.getLogger("centro")


def auto_actualizar() -> None:
    """git pull best-effort: nunca frena el arranque (sin red/git -> se ignora)."""
    if not os.path.isdir(os.path.join(REPO, ".git")):
        log.info("No es repo git: sin auto-actualizacion.")
        return
    try:
        r = subprocess.run(["git", "pull", "--ff-only"], cwd=REPO,
                           capture_output=True, text=True, timeout=60)
        log.info("git pull: %s", (r.stdout or r.stderr).strip().splitlines()[-1:]
                 or ["sin cambios"])
    except Exception as exc:
        log.warning("Auto-actualizacion omitida (%s).", exc)


def arrancar_vigilante() -> None:
    """Levanta el vigilante si no hay uno vivo. El vigilante arranca y cuida el
    resto de los servicios (colector + 4 bots + panel) desde el registro."""
    if vigilante_ya_corriendo():
        log.info("Vigilante ya activo.")
        return
    vig = os.path.join(_AQUI, "vigilante.py")
    subprocess.Popen([sys.executable, vig],
                     creationflags=(subprocess.DETACHED_PROCESS
                                    | subprocess.CREATE_NEW_PROCESS_GROUP)
                     if os.name == "nt" else 0,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("Vigilante lanzado (arranca y cuida colector + bots + panel).")


def _navegador() -> str:
    """Ruta a Chrome o Edge (rutas tipicas + PATH). '' si no hay ninguno."""
    import shutil
    cands = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which("chrome") or shutil.which("msedge") or ""


def abrir_app() -> None:
    """Abre el panel como ventana de app (Chrome/Edge --app). Best-effort."""
    if os.name != "nt":
        return
    nav = _navegador()
    if nav:
        subprocess.Popen([nav, f"--app={PANEL_URL}", "--window-size=1440,1000"])
    else:
        import webbrowser
        webbrowser.open(PANEL_URL)          # sin Chrome/Edge: ventana normal


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--no-update" not in sys.argv:
        auto_actualizar()
    arrancar_vigilante()
    if "--no-app" not in sys.argv:
        time.sleep(3)                              # que el panel levante antes de abrir
        abrir_app()
    log.info("Centro de Control listo. Servicios: %d.", len(leer_pids()) or 6)


if __name__ == "__main__":
    main()
