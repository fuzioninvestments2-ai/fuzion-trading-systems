"""
bot/trade_logger.py
===================
Registro de operaciones y sesiones en SQLite (base de datos local).

EL PORQUÉ: para mejorar hay que MEDIR. Guardar cada operación y cada sesión nos
permite calcular estadísticas reales (win rate, profit, rachas) y auditar qué
hizo el bot y por qué. Sin registro, volamos a ciegas.

SRP: este módulo solo lee/escribe la base de datos. No decide trades.
Usa una única conexión (thread-safe) para poder llamarse desde el bot y desde
Telegram sin abrir/cerrar en cada operación.
"""

import json
import sqlite3
from datetime import datetime


class TradeLogger:
    def __init__(self, db_path="trades.db"):
        # check_same_thread=False: permite usarlo desde hilos distintos (Telegram,
        # bucle del bot). Serializamos con la propia conexión.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                asset TEXT,
                direction TEXT,
                amount REAL,
                result TEXT,
                profit REAL,
                confidence REAL,
                strategy TEXT,
                details TEXT
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT,
                end_time TEXT,
                target_profit REAL,
                actual_profit REAL,
                total_trades INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate REAL,
                stop_reason TEXT
            )""")
        self.conn.commit()

    def log_trade(self, trade):
        """Registra una operación. `trade` es un dict con los campos esperados."""
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO trades
            (timestamp, asset, direction, amount, result, profit, confidence,
             strategy, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade.get("timestamp") or datetime.utcnow().isoformat(),
             trade.get("asset", ""),
             trade.get("direction", ""),
             float(trade.get("amount", 0.0)),
             trade.get("result", ""),
             float(trade.get("profit", 0.0)),
             float(trade.get("confidence", 0.0)),
             trade.get("strategy", ""),
             json.dumps(trade.get("details", {}))))
        self.conn.commit()
        return c.lastrowid

    def log_session(self, session):
        """Registra el resumen de una sesión."""
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO sessions
            (start_time, end_time, target_profit, actual_profit, total_trades,
             wins, losses, win_rate, stop_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.get("start_time", ""),
             session.get("end_time", ""),
             float(session.get("target_profit", 0.0)),
             float(session.get("actual_profit", 0.0)),
             int(session.get("total_trades", 0)),
             int(session.get("wins", 0)),
             int(session.get("losses", 0)),
             float(session.get("win_rate", 0.0)),
             session.get("stop_reason", "")))
        self.conn.commit()
        return c.lastrowid

    def get_statistics(self):
        """
        Devuelve estadísticas agregadas de todas las operaciones registradas.
        (win_rate se calcula sobre operaciones con resultado win/loss.)
        """
        c = self.conn.cursor()
        row = c.execute("""
            SELECT
              COUNT(*)                                     AS total_trades,
              SUM(CASE WHEN result='win'  THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
              COALESCE(SUM(profit), 0)                     AS total_profit,
              COALESCE(AVG(confidence), 0)                 AS avg_confidence
            FROM trades""").fetchone()

        total = row["total_trades"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        decided = wins + losses
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / decided) if decided else 0.0,
            "total_profit": round(row["total_profit"], 2),
            "avg_confidence": round(row["avg_confidence"], 3),
        }

    def close(self):
        self.conn.close()
