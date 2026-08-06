"""
src/core/results_store.py
=========================
FASE 2: persistencia del USER performance (resultados que el usuario reporta con
los botones de la tarjeta). Es el hueco que faltaba: hasta ahora vivian solo en
memoria (`FuzionTradingSystem.signal_results`) y se perdian al reiniciar.

NO duplica a `bot.signal_log.SignalTracker`: ese persiste el SIGNAL performance
(acierto sintetico del motor, tabla `signals`). Aqui se guarda lo OTRO: la plata
real del usuario (tabla `user_results`), la unica que alimenta al RiskManager.

Sigue el patron de SignalTracker: reutiliza la conexion y el lock del repo (una
sola conexion SQLite, sin contencion). Implementa `save_result(rec)`, la interfaz
que `FuzionTradingSystem._persist` prefiere.

SRP: solo persiste/consulta resultados de usuario. Sin red. Se prueba con una
conexion sqlite en memoria.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ResultsStore:
    def __init__(self, repo: Any) -> None:
        """repo: objeto con `.conn` (sqlite3) y `._lock` (como HistoryRepository)."""
        self.conn = repo.conn
        self._lock = repo._lock
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_results (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    pair      TEXT,
                    outcome   TEXT,       -- win / loss / skip
                    pnl       REAL,
                    stake     REAL,
                    traded    INTEGER,    -- 1 si el usuario realmente opero
                    source    TEXT        -- "user"
                )""")
            self.conn.execute("""CREATE INDEX IF NOT EXISTS idx_user_results_pair
                                 ON user_results (pair)""")
            self.conn.commit()

    def save_result(self, rec: Dict[str, Any]) -> Optional[int]:
        """
        Persiste un registro de resultado de usuario (el dict que arma
        FuzionTradingSystem.on_user_reported_result). Devuelve el id insertado.
        """
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO user_results
                   (signal_id, pair, outcome, pnl, stake, traded, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(rec.get("signal_id", "")), rec.get("pair", ""),
                 rec.get("outcome", ""), float(rec.get("pnl", 0.0)),
                 float(rec.get("stake", 0.0)),
                 1 if rec.get("traded") else 0, rec.get("source", "user")))
            self.conn.commit()
            return cur.lastrowid

    def recent(self, pair: Optional[str] = None,
               limit: int = 50) -> List[Dict[str, Any]]:
        """Ultimos resultados (global o por par), del mas nuevo al mas viejo."""
        with self._lock:
            if pair is None:
                rows = self.conn.execute(
                    """SELECT signal_id, pair, outcome, pnl, stake, traded
                       FROM user_results ORDER BY id DESC LIMIT ?""",
                    (int(limit),)).fetchall()
            else:
                rows = self.conn.execute(
                    """SELECT signal_id, pair, outcome, pnl, stake, traded
                       FROM user_results WHERE pair=? ORDER BY id DESC LIMIT ?""",
                    (pair, int(limit))).fetchall()
        return [{"signal_id": r[0], "pair": r[1], "outcome": r[2], "pnl": r[3],
                 "stake": r[4], "traded": bool(r[5])} for r in rows]

    def realized_pnl(self, pair: Optional[str] = None) -> float:
        """PnL realizado acumulado (global o por par), solo trades operados."""
        with self._lock:
            if pair is None:
                row = self.conn.execute(
                    "SELECT COALESCE(SUM(pnl), 0.0) FROM user_results WHERE traded=1"
                ).fetchone()
            else:
                row = self.conn.execute(
                    "SELECT COALESCE(SUM(pnl), 0.0) FROM user_results "
                    "WHERE traded=1 AND pair=?", (pair,)).fetchone()
        return float(row[0])
