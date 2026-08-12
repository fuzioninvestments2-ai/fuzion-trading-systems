"""
dashboard/panel_data.py (fuzion_fx)
===================================
Capa de DATOS del tablero: lee las bases reales (po_candles.db + f*_memory.db) y
el calendario de noticias, y arma un unico dict con TODO lo que muestra la app:
estado de procesos, win-rate REAL por bot (sin contar NULAS), pagos y cuales
pasan el filtro, ultimas transacciones y estado de noticias.

Honestidad: el win-rate cuenta SOLO win/loss resueltos reales; las NULAS (sin
dato) y las pendientes se muestran aparte, nunca infladas.

Sin red. Funciones puras-ish (aceptan rutas) -> testeables con bases temporales.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_CANDLES = os.path.join(ROOT, "data", "db", "po_candles.db")
NEWS_PATH = os.path.join(ROOT, "config", "news.json")

# (bot_id, etiqueta, timeframe_seg). El db de cada bot: f<N>_memory.db.
BOTS = [("f1_m1", "1M", 60), ("f2_m2", "2M", 120),
        ("f3_m3", "3M", 180), ("f4_m5", "5M", 300)]
TF_BOT = {60: "f1_m1", 120: "f2_m2", 180: "f3_m3", 300: "f4_m5"}

PAGO_MIN_DEFAULT = 72.0
# Orden del escaner: primero lo que esta LISTO para operar.
_RANK_ESTADO = {"LISTO": 0, "OBSERVANDO": 1, "-": 2, "sin datos": 3}


def _db_bot(bot_id: str) -> str:
    """f1_m1 -> data/db/f1_memory.db."""
    prefijo = bot_id.split("_")[0]
    return os.path.join(ROOT, "data", "db", f"{prefijo}_memory.db")


def _query(db: str, sql: str, params=()) -> List[tuple]:
    """Consulta segura: [] si el archivo o la tabla no existen todavia."""
    if not os.path.exists(db):
        return []
    try:
        conn = sqlite3.connect(db, timeout=5.0)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def winrate_bot(bot_id: str, db: Optional[str] = None) -> Dict[str, Any]:
    """
    Metricas REALES de un bot: emitidas, resueltas win/loss, wins, nulas,
    pendientes y win_pct (wins/(wins+losses); None sin muestra).
    """
    db = db or _db_bot(bot_id)
    filas = _query(db, "SELECT resolved, result FROM signals")
    emitidas = len(filas)
    wins = sum(1 for r, res in filas if r and res == "win")
    losses = sum(1 for r, res in filas if r and res == "loss")
    nulas = sum(1 for r, res in filas if r and res == "NULL")
    pendientes = sum(1 for r, res in filas if not r)
    resueltas = wins + losses
    win_pct = round(100.0 * wins / resueltas, 1) if resueltas else None
    return {"bot": bot_id, "emitidas": emitidas, "wins": wins, "losses": losses,
            "nulas": nulas, "pendientes": pendientes, "resueltas": resueltas,
            "win_pct": win_pct}


def pagos(db_candles: Optional[str] = None, min_pct: float = PAGO_MIN_DEFAULT
          ) -> List[Dict[str, Any]]:
    """Pago real por par (desc) + si pasa el filtro (>= min_pct)."""
    db_candles = db_candles or DB_CANDLES      # resuelve al LLAMAR (permite override)
    filas = _query(db_candles, "SELECT pair, payout FROM payouts ORDER BY payout DESC")
    return [{"pair": p, "payout": round(float(v), 1), "pasa": float(v) >= min_pct}
            for p, v in filas]


def ultimas_transacciones(n: int = 25) -> List[Dict[str, Any]]:
    """Ultimas `n` senales de los 4 bots juntas, mas nuevas primero."""
    filas: List[Dict[str, Any]] = []
    for bot_id, etiqueta, _ in BOTS:
        rows = _query(_db_bot(bot_id),
                      """SELECT ts, pair, direction, resolved, result, price
                         FROM signals ORDER BY ts DESC LIMIT ?""", (int(n),))
        for ts, pair, direction, resolved, result, price in rows:
            filas.append({"ts": int(ts or 0), "bot": etiqueta, "pair": pair,
                          "direction": direction,
                          "estado": ("pendiente" if not resolved else
                                     (result or "?")),
                          "price": price})
    filas.sort(key=lambda f: f["ts"], reverse=True)
    return filas[:n]


def reporte_ordenes(bot: Optional[str] = None, resultado: Optional[str] = None,
                    limite: int = 200) -> Dict[str, Any]:
    """
    REPORTE de ordenes (senales) de los 4 bots con detalle y totales. Filtros:
    bot (etiqueta '1M'..'5M' o id) y resultado (win/loss/NULL/pendiente). Devuelve
    {filas, resumen}. resumen = conteos + pnl total (sintetico, de aprendizaje).
    """
    filas: List[Dict[str, Any]] = []
    for bot_id, etiqueta, _ in BOTS:
        if bot and bot not in (etiqueta, bot_id):
            continue
        rows = _query(_db_bot(bot_id),
                      """SELECT ts, pair, direction, resolved, result, price, pnl
                         FROM signals ORDER BY ts DESC LIMIT ?""", (int(limite),))
        for ts, pair, direction, resolved, result, price, pnl in rows:
            estado = "pendiente" if not resolved else (result or "?")
            if resultado and estado != resultado:
                continue
            filas.append({"ts": int(ts or 0), "bot": etiqueta, "pair": pair,
                          "direction": direction, "estado": estado,
                          "price": price, "pnl": round(float(pnl or 0), 2)})
    filas.sort(key=lambda f: f["ts"], reverse=True)
    filas = filas[:limite]
    wins = sum(1 for f in filas if f["estado"] == "win")
    losses = sum(1 for f in filas if f["estado"] == "loss")
    nulas = sum(1 for f in filas if f["estado"] == "NULL")
    pend = sum(1 for f in filas if f["estado"] == "pendiente")
    return {"filas": filas, "resumen": {
        "total": len(filas), "wins": wins, "losses": losses, "nulas": nulas,
        "pendientes": pend, "pnl": round(sum(f["pnl"] for f in filas), 2),
        "win_pct": round(100.0 * wins / (wins + losses), 1) if (wins + losses) else None}}


def estado_procesos() -> List[Dict[str, Any]]:
    """Procesos (colector + bots + resumen) y si estan vivos. Sin dependencias."""
    try:
        from scripts.start_all import leer_pids
        from scripts.vigilante import _proceso_vivo, vigilante_ya_corriendo
    except Exception:
        return []
    pids = leer_pids()
    out = [{"nombre": nombre, "pid": pid, "vivo": _proceso_vivo(pid)}
           for nombre, pid in pids.items()]
    out.append({"nombre": "vigilante", "pid": None,
                "vivo": vigilante_ya_corriendo()})
    return out


def estado_noticias(now_ts: Optional[float] = None, buffer_min: float = 5.0,
                    news_path: Optional[str] = None) -> Dict[str, Any]:
    """Bloqueo por noticia ahora (global) + proximo evento de alto impacto."""
    from core.news_guard import cargar_eventos, en_bloqueo, proximo_evento
    news_path = news_path or NEWS_PATH         # resuelve al LLAMAR
    now_ts = time.time() if now_ts is None else now_ts
    eventos = cargar_eventos(news_path)
    bloqueo, evento = en_bloqueo(now_ts, eventos, buffer_min, pair=None)
    prox = proximo_evento(now_ts, eventos)
    return {
        "bloqueo": bloqueo,
        "evento": ({"titulo": evento["titulo"], "ts": evento["ts"]}
                   if evento else None),
        "proximo": ({"titulo": prox["titulo"], "ts": prox["ts"],
                     "monedas": prox.get("monedas", [])} if prox else None),
        "buffer_min": buffer_min,
    }


def candles_json(pair: str, tf: int, n: int = 90,
                 db_candles: Optional[str] = None) -> Dict[str, List[float]]:
    """
    Velas REALES del par+tf en JSON (ts/open/high/low/close) para el grafico VIVO
    del navegador. Cae a los ticks solo si no hay reales. {} si no hay nada.
    """
    db = db_candles or DB_CANDLES
    if not os.path.exists(db):
        return {}
    from collector.candle_store import CandleStore
    store = CandleStore(db)
    try:
        c = (store.get_real_candles(pair, int(tf), int(n))
             or store.get_candles(pair, int(tf), int(n)))
    finally:
        store.close()
    return c or {}


def escaner(tf: int, now_ts: Optional[float] = None,
            db_candles: Optional[str] = None,
            news_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    ESCANER de oportunidades: corre el motor sobre las velas reales de TODOS los
    pares a un timeframe y marca su estado, ordenando primero lo que esta LISTO
    (senal viva + pago >= 72% + sin bloqueo de noticia). No garantiza acierto:
    muestra donde se estan alineando las condiciones.
    """
    now_ts = time.time() if now_ts is None else now_ts
    from core.config import get_bot_config
    from core.signal_engine import SignalEngine, NEUTRAL
    from core.news_guard import cargar_eventos, en_bloqueo
    cfg = get_bot_config(TF_BOT.get(int(tf), "f4_m5"))
    eng = SignalEngine(cfg["indicators"], cfg["signal"])
    buffer = float(cfg["risk"].get("news_buffer_minutes", 5))
    eventos = cargar_eventos(news_path or NEWS_PATH)
    pagos_map = {p["pair"]: p for p in pagos(db_candles)}

    filas: List[Dict[str, Any]] = []
    for pair in cfg["pairs"]:
        c = candles_json(pair, tf, 120, db_candles)
        pay = pagos_map.get(pair, {}).get("payout")
        pasa_pago = pay is not None and pay >= PAGO_MIN_DEFAULT
        if not c or len(c.get("close", [])) < 30:
            filas.append({"pair": pair, "signal": "NEUTRAL", "confirmations": 0,
                          "confirming": [], "payout": pay, "pasa_pago": pasa_pago,
                          "bloqueo": False, "estado": "sin datos"})
            continue
        try:
            res = eng.analyze(c)
        except Exception:
            res = {"signal": NEUTRAL, "confirmations": 0, "confirming": []}
        bloqueo, _ = en_bloqueo(now_ts, eventos, buffer, pair)
        sig = res.get("signal", NEUTRAL)
        if sig != NEUTRAL and pasa_pago and not bloqueo:
            estado = "LISTO"
        elif sig != NEUTRAL:
            estado = "OBSERVANDO"                # senal pero pago bajo o noticia
        else:
            estado = "-"
        filas.append({"pair": pair, "signal": sig,
                      "confirmations": int(res.get("confirmations", 0)),
                      "confirming": res.get("confirming", []),
                      "payout": pay, "pasa_pago": pasa_pago, "bloqueo": bloqueo,
                      "estado": estado})
    filas.sort(key=lambda f: (_RANK_ESTADO.get(f["estado"], 9),
                              -f["confirmations"], -(f["payout"] or 0)))
    return filas


def resumen_general(now_ts: Optional[float] = None) -> Dict[str, Any]:
    """Todo el estado en un dict, listo para la API del tablero."""
    now_ts = time.time() if now_ts is None else now_ts
    bots = [{"etiqueta": et, "tf": tf, **winrate_bot(bid)}
            for bid, et, tf in BOTS]
    tot_w = sum(b["wins"] for b in bots)
    tot_l = sum(b["losses"] for b in bots)
    global_pct = round(100.0 * tot_w / (tot_w + tot_l), 1) if (tot_w + tot_l) else None
    lista_pagos = pagos()
    from core import control
    return {
        "ts": int(now_ts),
        "pausado": control.esta_pausado(),
        "telegram": control.estado_telegram([b for b, _, _ in BOTS]),
        "bots": bots,
        "global": {"wins": tot_w, "losses": tot_l, "win_pct": global_pct,
                   "nulas": sum(b["nulas"] for b in bots),
                   "pendientes": sum(b["pendientes"] for b in bots)},
        "pagos": lista_pagos,
        "pagos_ok": sum(1 for p in lista_pagos if p["pasa"]),
        "transacciones": ultimas_transacciones(25),
        "procesos": estado_procesos(),
        "noticias": estado_noticias(now_ts),
    }
