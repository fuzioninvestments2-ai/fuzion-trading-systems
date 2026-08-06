"""
core/results_store.py (fuzion_fx)
=================================
Persistencia sqlite POR BOT (cada bot su archivo: f1_memory.db, ...). Guarda las
senales emitidas y su resultado, que alimenta el aprendizaje por setup y el
win-rate. Cada proceso abre su propia conexion (procesos independientes).

Sin red. Se prueba con sqlite en memoria.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


class ResultsStore:
    def __init__(self, db_path: str) -> None:
        # ":memory:" para tests; en produccion crea la carpeta si falta.
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db_path = db_path
        # check_same_thread=False: el loop async y el registro pueden vivir en
        # hilos distintos; se serializa con un lock propio.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts            INTEGER,
                    pair          TEXT,
                    timeframe     TEXT,
                    direction     TEXT,        -- CALL / PUT
                    setup_id      TEXT,        -- que confirmaron (para aprendizaje)
                    confirmations INTEGER,
                    price         REAL,
                    atr           REAL,
                    resolved      INTEGER DEFAULT 0,
                    result        TEXT,        -- win / loss / tie / NULL
                    pnl           REAL DEFAULT 0
                )""")
            self.conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_setup
                                 ON signals (setup_id, resolved)""")
            self.conn.commit()

    def save_signal(self, rec: Dict[str, Any]) -> int:
        """Guarda una senal emitida (pendiente de resultado). Devuelve su id."""
        ts = int(rec.get("ts") or time.time())
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO signals
                   (ts, pair, timeframe, direction, setup_id, confirmations,
                    price, atr)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, rec.get("pair", ""), rec.get("timeframe", ""),
                 rec.get("direction", ""), rec.get("setup_id"),
                 int(rec.get("confirmations", 0)), float(rec.get("price", 0.0)),
                 float(rec.get("atr", 0.0))))
            self.conn.commit()
            return cur.lastrowid

    def resolve_signal(self, signal_id: int, result: str, pnl: float = 0.0) -> None:
        """Marca una senal con su resultado (win/loss/tie) y su pnl."""
        with self._lock:
            self.conn.execute(
                "UPDATE signals SET resolved=1, result=?, pnl=? WHERE id=?",
                (result, float(pnl), int(signal_id)))
            self.conn.commit()

    def pending_older_than(self, cutoff_ts: int) -> List[Dict[str, Any]]:
        """
        Senales sin resolver cuya vela de entrada (ts) es <= cutoff_ts (ya
        vencieron y su resultado se puede conocer). Para el feedback loop.
        """
        with self._lock:
            rows = self.conn.execute(
                """SELECT id, pair, timeframe, direction, price, ts
                   FROM signals WHERE resolved=0 AND ts <= ?
                   ORDER BY ts ASC""", (int(cutoff_ts),)).fetchall()
        return [{"id": r[0], "pair": r[1], "timeframe": r[2], "direction": r[3],
                 "price": r[4], "ts": r[5]} for r in rows]

    def setup_stats(self, setup_id: str) -> Dict[str, Any]:
        """{trades, wins, losses, win_pct} de un setup ya resuelto."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT result FROM signals
                   WHERE setup_id=? AND resolved=1 AND result IN ('win','loss')""",
                (setup_id,)).fetchall()
        trades = len(rows)
        wins = sum(1 for (r,) in rows if r == "win")
        win_pct = (100.0 * wins / trades) if trades else 0.0
        return {"trades": trades, "wins": wins, "losses": trades - wins,
                "win_pct": round(win_pct, 1)}

    def win_rate(self, pair: Optional[str] = None) -> Dict[str, Any]:
        """Win-rate global o por par (senales resueltas)."""
        with self._lock:
            if pair is None:
                rows = self.conn.execute(
                    """SELECT result FROM signals
                       WHERE resolved=1 AND result IN ('win','loss')""").fetchall()
            else:
                rows = self.conn.execute(
                    """SELECT result FROM signals
                       WHERE resolved=1 AND result IN ('win','loss') AND pair=?""",
                    (pair,)).fetchall()
        trades = len(rows)
        wins = sum(1 for (r,) in rows if r == "win")
        return {"trades": trades, "wins": wins,
                "win_pct": round(100.0 * wins / trades, 1) if trades else 0.0}

    def close(self) -> None:
        with self._lock:
            self.conn.close()
