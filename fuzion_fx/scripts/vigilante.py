"""
scripts/vigilante.py (fuzion_fx) — HERRAMIENTA PROPIA: supervisor 24/7
======================================================================
Mantiene el sistema trabajando SOLO: arranca lo que falte, vigila el colector y
los 4 bots y, si algo se cae o el colector queda MUDO (deja de escribir velas),
lo REINICIA sin intervencion. Avisa por Telegram los cambios de estado (caidas,
reinicios, falta de pagos), sin spamear (solo cuando algo cambia).

PORQUE (Regla 3 del proyecto: robustez + reconexion): PO se cae, el socket queda
mudo, un proceso muere. Sin vigilante hay que estar encima; con vigilante el
sistema se cuida solo. Reutiliza el arranque de start_all (no duplica).

Diseno: el nucleo de decision `evaluar_salud` es PURO (sin red, sin SO, sin
sqlite) -> testeable. El loop solo lee el estado real y aplica las acciones.

    python fuzion_fx/scripts/vigilante.py
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts.start_all import (PROCESOS, SCRIPT_DE, ROOT,          # noqa: E402
                               lanzar_proceso, leer_pids, guardar_pids)

DB_PATH = os.path.join(ROOT, "data", "db", "po_candles.db")
INTERVALO_SEG = 20                     # cada cuanto revisa
MUDO_SEG = 180                         # colector vivo pero sin escribir hace tanto -> mudo
GRACIA_PAGOS_SEG = 120                 # margen tras arrancar antes de alertar por pagos

log = logging.getLogger("vigilante")


# --------------------------------------------------------------- nucleo puro
def evaluar_salud(snapshot: Dict[str, Any], umbrales: Dict[str, Any]
                  ) -> Dict[str, List[str]]:
    """
    Decide QUE reiniciar y QUE alertar a partir de un snapshot (sin tocar SO/red).

    snapshot = {
      "procesos": {"collector": bool, "f1_m1": bool, ...},  # vivo?
      "db_mtime_age": float|None,   # seg desde la ultima escritura de po_candles.db
      "pagos": int,                 # cuantos pares tienen pago cargado
      "uptime": float,              # seg desde que arranco el vigilante
    }
    Devuelve {"reiniciar": [nombres], "alertas": [textos]}.
    """
    reiniciar: List[str] = []
    alertas: List[str] = []

    procesos = snapshot.get("procesos", {})
    for nombre, vivo in procesos.items():
        if not vivo:
            reiniciar.append(nombre)
            alertas.append(f"{nombre} caido → reiniciando")

    # Colector VIVO pero que no escribe hace rato = socket mudo -> reiniciar.
    # OJO: el mtime de la db puede ser viejo (del colector anterior) mientras el
    # nuevo recien arranca y todavia no escribio. Por eso el "silencio" real es el
    # MINIMO entre el tiempo sin escribir (age) y el tiempo que lleva vivo este
    # colector (col_uptime): asi no se lo declara mudo apenas arranca.
    col_vivo = procesos.get("collector", False)
    age = snapshot.get("db_mtime_age")
    col_uptime = snapshot.get("col_uptime")
    if col_vivo and age is not None:
        silencio = age if col_uptime is None else min(age, col_uptime)
        if silencio > umbrales.get("mudo_seg", MUDO_SEG):
            if "collector" not in reiniciar:
                reiniciar.append("collector")
            alertas.append(f"colector MUDO ({int(silencio)}s sin escribir) → "
                           f"reiniciando")

    # Sin pagos cargados: los bots no emiten (filtro de pago). Solo alerta.
    if (snapshot.get("pagos", 0) == 0
            and snapshot.get("uptime", 0) > umbrales.get("gracia_pagos_seg",
                                                          GRACIA_PAGOS_SEG)):
        alertas.append("sin pagos cargados aún: los bots no emiten hasta que PO "
                       "envíe los payouts (revisar conexión del colector)")

    return {"reiniciar": reiniciar, "alertas": alertas}


# --------------------------------------------------------------- estado real (SO/db)
def _proceso_vivo(pid: Optional[int]) -> bool:
    """True si el PID esta vivo. Multiplataforma sin dependencias de terceros."""
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                    # existe pero no es nuestro
    return True


def _db_mtime_age(db_path: str, ahora: float) -> Optional[float]:
    """Segundos desde la ultima escritura de la db (mtime). None si no existe."""
    try:
        return ahora - os.path.getmtime(db_path)
    except OSError:
        return None


def _pagos_count(db_path: str) -> int:
    """Cuantos pares tienen pago cargado. 0 si la tabla/archivo aun no existe."""
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _snapshot(pids: Dict[str, int], arranque: float, arranque_colector: float,
              ahora: float) -> Dict[str, Any]:
    procesos = {nombre: _proceso_vivo(pids.get(nombre)) for nombre, _ in PROCESOS}
    return {
        "procesos": procesos,
        "db_mtime_age": _db_mtime_age(DB_PATH, ahora),
        "col_uptime": ahora - arranque_colector,   # seg vivo del colector actual
        "pagos": _pagos_count(DB_PATH),
        "uptime": ahora - arranque,
    }


def _notifier():
    """Notifier comun para alertas (token/canal de telegram en config). None si
    no hay credenciales -> se cae a log (no rompe)."""
    try:
        from core.config import load_config
        from telegram.notifier import TelegramNotifier
        tg = load_config().get("telegram", {})
        token = tg.get("bot_token")
        canal = tg.get("channel_id")
        if token and canal:
            return TelegramNotifier(token, canal)
    except Exception:
        pass
    return None


def _setup_logging() -> None:
    """
    Loguea a ARCHIVO (logs/vigilante.log) siempre, y a consola solo si hay una.
    Asi el vigilante puede correr INVISIBLE (pythonw, sin ventana) sin romper: con
    pythonw no hay stderr, y un StreamHandler a stderr=None fallaria.
    """
    logs_dir = os.path.join(ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers: list = [logging.FileHandler(os.path.join(logs_dir, "vigilante.log"),
                                          encoding="utf-8")]
    if sys.stderr is not None:                 # hay consola -> tambien a pantalla
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def main() -> None:
    _setup_logging()
    notifier = _notifier()
    arranque = time.time()
    arranque_colector = arranque       # cuando arranco el colector actual (grace)
    pids = leer_pids()

    # Arranque: asegurar que TODO este corriendo (levanta lo que falte).
    for nombre, script in PROCESOS:
        if not _proceso_vivo(pids.get(nombre)):
            pids[nombre] = lanzar_proceso(script)
            log.info("Arrancado %s -> PID %d", nombre, pids[nombre])
    guardar_pids(pids)
    log.info("Vigilante activo: revisa cada %ds (colector mudo > %ds).",
             INTERVALO_SEG, MUDO_SEG)

    umbrales = {"mudo_seg": MUDO_SEG, "gracia_pagos_seg": GRACIA_PAGOS_SEG}
    alertas_previas: set = set()
    try:
        while True:
            ahora = time.time()
            snap = _snapshot(pids, arranque, arranque_colector, ahora)
            plan = evaluar_salud(snap, umbrales)

            for nombre in plan["reiniciar"]:
                script = SCRIPT_DE.get(nombre)
                if script:
                    pids[nombre] = lanzar_proceso(script)
                    guardar_pids(pids)
                    log.warning("Reiniciado %s -> PID %d", nombre, pids[nombre])
                    if nombre == "collector":
                        arranque_colector = ahora   # reinicia el grace del colector

            # Alertar SOLO lo nuevo (evita spamear el mismo problema cada 20s).
            nuevas = [a for a in plan["alertas"] if a not in alertas_previas]
            for a in nuevas:
                log.warning("ALERTA: %s", a)
                if notifier:
                    notifier.send_alert(f"🛡️ *Vigilante Fuzion FX*\n{a}")
            alertas_previas = set(plan["alertas"])

            time.sleep(INTERVALO_SEG)
    except KeyboardInterrupt:
        log.info("Vigilante detenido (los procesos siguen corriendo).")


if __name__ == "__main__":
    main()
