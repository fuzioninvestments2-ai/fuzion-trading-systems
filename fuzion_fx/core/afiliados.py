"""
core/afiliados.py (fuzion_fx)
=============================
Registro de AFILIADOS (membresia MENSUAL): a quien se le reparten las senales
educativas, que temporalidades recibe cada uno, y el control del cobro mensual.

MODELO: el afiliado paga el ACCESO/asesoria por mes (no la senal suelta). El
sistema NO mueve cripto: solo REGISTRA el cobro y el vencimiento (el pago lo
recibis vos en tu wallet). 'marcar_pagado' extiende la membresia 30 dias.

HONESTIDAD: las senales que se reparten llevan el mismo sello educativo; no se
promete acierto. Un afiliado paga acceso, no ganancias garantizadas.

sqlite (data/db/afiliados.db). Sin red. Se prueba con base en memoria/temporal.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "db", "afiliados.db")
COBRO_PATH = os.path.join(ROOT, "config", "cobro.json")
DIA = 86400
MES = 30 * DIA


def leer_cobro(path: Optional[str] = None) -> Dict[str, Any]:
    """Config de cobro del DUENO: wallet (cripto), precio mensual y moneda. El
    sistema solo lo MUESTRA; el pago lo recibis vos en tu wallet."""
    import json
    path = path or COBRO_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"wallet": str(d.get("wallet", "")),
                "precio": float(d.get("precio", 0) or 0),
                "moneda": str(d.get("moneda", "USDT"))}
    except (OSError, ValueError):
        return {"wallet": "", "precio": 0.0, "moneda": "USDT"}


def set_cobro(wallet: str, precio: float, moneda: str = "USDT",
              path: Optional[str] = None) -> None:
    import json
    path = path or COBRO_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"wallet": wallet, "precio": float(precio or 0),
                   "moneda": moneda}, f)


def _conn(db_path: str) -> sqlite3.connect:
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    c = sqlite3.connect(db_path)
    c.execute("""CREATE TABLE IF NOT EXISTS afiliados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT, chat_id TEXT, timeframes TEXT,
        fee REAL DEFAULT 0, alta INTEGER, vence INTEGER, nota TEXT DEFAULT '')""")
    return c


def _fila(r) -> Dict[str, Any]:
    return {"id": r[0], "nombre": r[1], "chat_id": r[2],
            "timeframes": [t for t in (r[3] or "").split(",") if t],
            "fee": float(r[4] or 0), "alta": r[5], "vence": r[6], "nota": r[7] or ""}


def alta(nombre: str, chat_id: str, timeframes: List[str], fee: float = 0.0,
         dias: int = 30, now: Optional[float] = None, db_path: str = DB_PATH) -> int:
    """Da de alta un afiliado con membresia de `dias`. Devuelve su id."""
    now = int(time.time() if now is None else now)
    c = _conn(db_path)
    try:
        cur = c.execute(
            "INSERT INTO afiliados (nombre, chat_id, timeframes, fee, alta, vence) "
            "VALUES (?,?,?,?,?,?)",
            (nombre, str(chat_id), ",".join(timeframes), float(fee), now,
             now + int(dias) * DIA))
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def marcar_pagado(afiliado_id: int, dias: int = 30, now: Optional[float] = None,
                  db_path: str = DB_PATH) -> Optional[int]:
    """
    Registra un pago: extiende la membresia `dias`. Si ya estaba vigente, se suma
    al vencimiento; si estaba vencida, arranca desde ahora. Devuelve el nuevo
    vencimiento (epoch) o None si el afiliado no existe.
    """
    now = int(time.time() if now is None else now)
    c = _conn(db_path)
    try:
        row = c.execute("SELECT vence FROM afiliados WHERE id=?",
                        (int(afiliado_id),)).fetchone()
        if row is None:
            return None
        base = max(int(row[0] or now), now)         # si vencio, desde hoy
        nuevo = base + int(dias) * DIA
        c.execute("UPDATE afiliados SET vence=? WHERE id=?", (nuevo, int(afiliado_id)))
        c.commit()
        return nuevo
    finally:
        c.close()


def set_timeframes(afiliado_id: int, timeframes: List[str],
                   db_path: str = DB_PATH) -> None:
    c = _conn(db_path)
    try:
        c.execute("UPDATE afiliados SET timeframes=? WHERE id=?",
                  (",".join(timeframes), int(afiliado_id)))
        c.commit()
    finally:
        c.close()


def baja(afiliado_id: int, db_path: str = DB_PATH) -> None:
    c = _conn(db_path)
    try:
        c.execute("DELETE FROM afiliados WHERE id=?", (int(afiliado_id),))
        c.commit()
    finally:
        c.close()


def listar(now: Optional[float] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Todos los afiliados con estado (activo si vence>=now) y dias restantes."""
    now = int(time.time() if now is None else now)
    if not os.path.exists(db_path) and db_path != ":memory:":
        return []
    c = _conn(db_path)
    try:
        rows = c.execute("SELECT id,nombre,chat_id,timeframes,fee,alta,vence,nota "
                         "FROM afiliados ORDER BY vence ASC").fetchall()
    finally:
        c.close()
    out = []
    for r in rows:
        d = _fila(r)
        d["activo"] = int(d["vence"] or 0) >= now
        d["dias_restantes"] = max(0, (int(d["vence"] or 0) - now) // DIA)
        out.append(d)
    return out


def destinatarios_para(bot_id: str, now: Optional[float] = None,
                       db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Afiliados ACTIVOS que reciben la temporalidad `bot_id` (para repartir la senal).
    Devuelve [{id, nombre, chat_id}]. Vacio si no hay base o ninguno califica.
    """
    return [{"id": a["id"], "nombre": a["nombre"], "chat_id": a["chat_id"]}
            for a in listar(now, db_path)
            if a["activo"] and bot_id in a["timeframes"]]


def resumen(now: Optional[float] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Totales para el panel: cuantos activos/vencidos y cobro mensual estimado."""
    afs = listar(now, db_path)
    activos = [a for a in afs if a["activo"]]
    return {"total": len(afs), "activos": len(activos),
            "vencidos": len(afs) - len(activos),
            "ingreso_mensual": round(sum(a["fee"] for a in activos), 2)}
