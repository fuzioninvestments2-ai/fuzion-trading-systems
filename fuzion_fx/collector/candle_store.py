"""
collector/candle_store.py (fuzion_fx)
=====================================
Base de velas COMPARTIDA (po_candles.db). El colector escribe; los 4 bots leen.

Tabla candles(pair, tf, ts, open, high, low, close, volume) con PRIMARY KEY
(pair, tf, ts): asi una vela se puede reescribir mientras se forma (upsert) sin
duplicar. `tf` es el timeframe en SEGUNDOS (60/120/180/300) para ser inequivoco.

Concurrencia: varios procesos abren el MISMO archivo sqlite. Se usa WAL (varios
lectores + un escritor sin bloquear) y timeout para reintentar si esta ocupado.

Sin red. Se prueba con sqlite en memoria/archivo temporal.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Optional


class CandleStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db_path = db_path
        # timeout: si otro proceso escribe, espera en vez de fallar al toque.
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self._init_schema()

    def _init_schema(self) -> None:
        # WAL: lectores concurrentes (los 4 bots) mientras el colector escribe.
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                pair    TEXT,
                tf      INTEGER,          -- timeframe en segundos
                ts      INTEGER,          -- inicio de la vela (epoch seg)
                open    REAL,
                high    REAL,
                low     REAL,
                close   REAL,
                volume  REAL DEFAULT 0,
                PRIMARY KEY (pair, tf, ts)
            )""")
        self.conn.commit()

    def upsert_candle(self, pair: str, tf: int, ts: int, o: float, h: float,
                      l: float, c: float, volume: float = 0.0) -> None:
        """Inserta o actualiza una vela (para la que se esta formando)."""
        self.conn.execute(
            """INSERT INTO candles (pair, tf, ts, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(pair, tf, ts) DO UPDATE SET
                 high=excluded.high, low=excluded.low, close=excluded.close,
                 volume=excluded.volume""",
            (pair, int(tf), int(ts), float(o), float(h), float(l), float(c),
             float(volume)))
        self.conn.commit()

    def get_candles(self, pair: str, tf: int,
                    count: int = 200) -> Optional[Dict[str, List[float]]]:
        """
        Ultimas `count` velas del par+tf en orden CRONOLOGICO
        {open,high,low,close,volume}. None si no hay ninguna.
        """
        rows = self.conn.execute(
            """SELECT ts, open, high, low, close, volume FROM candles
               WHERE pair=? AND tf=? ORDER BY ts DESC LIMIT ?""",
            (pair, int(tf), int(count))).fetchall()
        if not rows:
            return None
        rows = rows[::-1]                          # a cronologico (viejo -> nuevo)
        return {
            "ts": [r[0] for r in rows],
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        }

    def price_at(self, pair: str, tf: int, ts: int) -> Optional[float]:
        """Cierre de la primera vela con ts >= al pedido (para resolver senales)."""
        row = self.conn.execute(
            """SELECT close FROM candles WHERE pair=? AND tf=? AND ts >= ?
               ORDER BY ts ASC LIMIT 1""", (pair, int(tf), int(ts))).fetchone()
        return float(row[0]) if row else None

    def close(self) -> None:
        self.conn.close()
