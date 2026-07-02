"""
bot/history.py
==============
Repositorio de HISTORIAL de precios (velas) en SQLite.

EL PORQUÉ: para tener un sistema mejor hay que ACUMULAR datos propios. Cada vela
que recibamos (simulada hoy, real cuando conectemos Pocket Option) se guarda
aquí. Con el tiempo tendrás un "repositorio amplio" para calibrar la estrategia
y hacer backtests sobre TUS datos reales.

SRP: este módulo solo guarda/consulta velas. No decide trades ni conecta a red.
Es thread-safe (una sola conexión con lock) para usarse desde el bot y Telegram.
"""

import sqlite3
import threading

import pandas as pd


class HistoryRepository:
    def __init__(self, db_path="history.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    asset      TEXT,
                    timeframe  TEXT,
                    ts         INTEGER,   -- inicio de la vela (ms)
                    open       REAL,
                    high       REAL,
                    low        REAL,
                    close      REAL,
                    volume     REAL,
                    PRIMARY KEY (asset, timeframe, ts)
                )""")
            # Índice para consultas rápidas por activo/tiempo ordenadas por hora.
            c.execute("""CREATE INDEX IF NOT EXISTS idx_candles
                         ON candles (asset, timeframe, ts)""")
            self.conn.commit()

    def record_candle(self, asset, timeframe, candle):
        """
        Guarda una vela. `candle` es un dict con open/high/low/close/volume/
        timestamp. Si ya existe esa vela (mismo asset+timeframe+ts), la
        reemplaza (INSERT OR REPLACE) para no duplicar.
        """
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO candles
                   (asset, timeframe, ts, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset, timeframe, int(candle["timestamp"]),
                 float(candle["open"]), float(candle["high"]),
                 float(candle["low"]), float(candle["close"]),
                 float(candle.get("volume", 0))))
            self.conn.commit()

    def record_many(self, asset, timeframe, candles):
        """Guarda varias velas de golpe (más eficiente)."""
        rows = [(asset, timeframe, int(c["timestamp"]), float(c["open"]),
                 float(c["high"]), float(c["low"]), float(c["close"]),
                 float(c.get("volume", 0))) for c in candles]
        with self._lock:
            self.conn.executemany(
                """INSERT OR REPLACE INTO candles
                   (asset, timeframe, ts, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows)
            self.conn.commit()

    def get_recent(self, asset, timeframe, limit=500):
        """
        Devuelve las últimas `limit` velas de un activo/tiempo como DataFrame,
        en orden cronológico (la más reciente al final) — listo para indicadores.
        """
        with self._lock:
            df = pd.read_sql_query(
                """SELECT ts AS timestamp, open, high, low, close, volume
                   FROM candles WHERE asset=? AND timeframe=?
                   ORDER BY ts DESC LIMIT ?""",
                self.conn, params=(asset, timeframe, limit))
        # Vino de más reciente a más antiguo; lo invertimos a cronológico.
        return df.iloc[::-1].reset_index(drop=True)

    def count(self, asset=None, timeframe=None):
        """Cuenta velas guardadas (total, o de un activo/tiempo concreto)."""
        q = "SELECT COUNT(*) FROM candles"
        params = []
        conds = []
        if asset:
            conds.append("asset=?"); params.append(asset)
        if timeframe:
            conds.append("timeframe=?"); params.append(timeframe)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        with self._lock:
            return self.conn.execute(q, params).fetchone()[0]

    def assets_tracked(self):
        """Lista de (asset, timeframe) con cuántas velas hay de cada uno."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT asset, timeframe, COUNT(*) AS n FROM candles
                   GROUP BY asset, timeframe ORDER BY n DESC""").fetchall()
        return [{"asset": a, "timeframe": tf, "velas": n} for a, tf, n in rows]

    def close(self):
        self.conn.close()
