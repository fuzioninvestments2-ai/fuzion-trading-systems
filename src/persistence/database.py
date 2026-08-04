"""
src/persistence/database.py
===========================
TAREA 3 del manual: base de datos MEJORADA sobre la idea de `bot/history.py`.

PORQUE: `bot/history.py` solo guarda velas. Para medir el sistema (backtest,
win-rate del filtro de proteccion, calibracion) hace falta ademas registrar las
SENALES con su resultado y poder consultar el rendimiento por par/timeframe.
Este modulo unifica ambas cosas en una sola BD tipada:

  - candles : OHLCV por (par, timeframe, ts)          -> alimenta indicadores.
  - signals : cada senal con probabilidad/convergencia y resultado
              WIN / LOSS / PENDING                     -> mide el sistema real.
  - consultas de win-rate por par/timeframe y metricas globales de rendimiento.

SRP: solo persiste y consulta. No conecta a red ni decide trades. Thread-safe
(una conexion con lock) para usarse desde el bot y Telegram a la vez.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

# Estados posibles de una senal. PORQUE: constantes en vez de strings sueltos
# para evitar errores de tipeo y centralizar el vocabulario.
PENDING: str = "PENDING"
WIN: str = "WIN"
LOSS: str = "LOSS"
_RESULTADOS_VALIDOS = frozenset({PENDING, WIN, LOSS})


class Database:
    """BD de velas y senales en SQLite (mejora de HistoryRepository)."""

    def __init__(self, db_path: str = "history.db") -> None:
        # check_same_thread=False + lock: el bot y Telegram comparten conexion.
        try:
            self.conn: sqlite3.Connection = sqlite3.connect(
                db_path, check_same_thread=False)
        except sqlite3.Error as e:
            raise RuntimeError(f"No se pudo abrir la BD en {db_path}: {e}") from e
        self._lock = threading.Lock()
        self._init_schema()

    # ------------------------------------------------------------------ schema
    def _init_schema(self) -> None:
        """Crea tablas e indices si no existen (idempotente)."""
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
            c.execute("""CREATE INDEX IF NOT EXISTS idx_candles
                         ON candles (asset, timeframe, ts)""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset       TEXT    NOT NULL,
                    timeframe   TEXT    NOT NULL,
                    direction   TEXT    NOT NULL,          -- CALL | PUT
                    probability REAL    NOT NULL,          -- 0-100
                    convergence REAL    NOT NULL,          -- 0-100
                    ts_created  INTEGER NOT NULL,          -- creacion (ms)
                    result      TEXT    NOT NULL DEFAULT 'PENDING',
                    ts_resolved INTEGER,                   -- cierre (ms)
                    meta        TEXT                       -- JSON opcional
                )""")
            # Indice para win-rate por par/timeframe filtrando por resultado.
            c.execute("""CREATE INDEX IF NOT EXISTS idx_signals_par
                         ON signals (asset, timeframe, result)""")
            self.conn.commit()

    # ------------------------------------------------------------------ velas
    def save_candle(self, asset: str, timeframe: str,
                    candle: Dict[str, Any]) -> None:
        """Guarda (o reemplaza) una vela OHLCV. `candle` trae timestamp/ohlcv."""
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

    def save_candles(self, asset: str, timeframe: str,
                     candles: Sequence[Dict[str, Any]]) -> int:
        """Guarda varias velas de golpe. Devuelve cuantas se procesaron."""
        rows = [(asset, timeframe, int(c["timestamp"]), float(c["open"]),
                 float(c["high"]), float(c["low"]), float(c["close"]),
                 float(c.get("volume", 0))) for c in candles]
        with self._lock:
            self.conn.executemany(
                """INSERT OR REPLACE INTO candles
                   (asset, timeframe, ts, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows)
            self.conn.commit()
        return len(rows)

    # Alias de compatibilidad: el loader existente (bot/historical_loader.py)
    # llama repo.record_many(asset, timeframe, velas). Se delega en save_candles
    # para poder reutilizarlo sin tocar ese modulo.
    def record_many(self, asset: str, timeframe: str,
                    candles: Sequence[Dict[str, Any]]) -> int:
        return self.save_candles(asset, timeframe, candles)

    def get_candles(self, asset: str, timeframe: str,
                    limit: int = 500) -> pd.DataFrame:
        """Ultimas `limit` velas en orden cronologico (listo para indicadores)."""
        with self._lock:
            df = pd.read_sql_query(
                """SELECT ts AS timestamp, open, high, low, close, volume
                   FROM candles WHERE asset=? AND timeframe=?
                   ORDER BY ts DESC LIMIT ?""",
                self.conn, params=(asset, timeframe, limit))
        return df.iloc[::-1].reset_index(drop=True)

    # ----------------------------------------------------------------- senales
    def save_signal(self, asset: str, timeframe: str, direction: str,
                    probability: float, convergence: float, ts_created: int,
                    meta: Optional[str] = None) -> int:
        """
        Registra una senal nueva como PENDING y devuelve su id.

        PORQUE: el id permite luego resolverla (WIN/LOSS) cuando expire la opcion.
        """
        if direction not in ("CALL", "PUT"):
            raise ValueError(f"direction invalida: {direction} (CALL|PUT)")
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO signals
                   (asset, timeframe, direction, probability, convergence,
                    ts_created, result, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset, timeframe, direction, float(probability),
                 float(convergence), int(ts_created), PENDING, meta))
            self.conn.commit()
            return int(cur.lastrowid)

    def resolve_signal(self, signal_id: int, result: str,
                       ts_resolved: int) -> None:
        """Marca una senal como WIN o LOSS al expirar la opcion."""
        if result not in (WIN, LOSS):
            raise ValueError(f"result invalido: {result} (WIN|LOSS)")
        with self._lock:
            self.conn.execute(
                "UPDATE signals SET result=?, ts_resolved=? WHERE id=?",
                (result, int(ts_resolved), int(signal_id)))
            self.conn.commit()

    def pending_signals(self) -> List[Dict[str, Any]]:
        """Senales aun sin resolver (para cerrarlas cuando venza su expiracion)."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT id, asset, timeframe, direction, probability,
                          convergence, ts_created
                   FROM signals WHERE result=? ORDER BY ts_created""",
                (PENDING,)).fetchall()
        cols = ("id", "asset", "timeframe", "direction", "probability",
                "convergence", "ts_created")
        return [dict(zip(cols, r)) for r in rows]

    # --------------------------------------------------------------- analitica
    def win_rate(self, asset: Optional[str] = None,
                 timeframe: Optional[str] = None) -> Dict[str, Any]:
        """
        Win-rate historico (0-1) sobre senales RESUELTAS (WIN+LOSS), filtrable
        por par y/o timeframe. Devuelve wins, losses, total y ratio.
        """
        conds = ["result IN (?, ?)"]
        params: List[Any] = [WIN, LOSS]
        if asset:
            conds.append("asset=?"); params.append(asset)
        if timeframe:
            conds.append("timeframe=?"); params.append(timeframe)
        where = " WHERE " + " AND ".join(conds)
        with self._lock:
            wins = self.conn.execute(
                f"SELECT COUNT(*) FROM signals{where} AND result=?",
                (*params, WIN)).fetchone()[0]
            total = self.conn.execute(
                f"SELECT COUNT(*) FROM signals{where}", params).fetchone()[0]
        losses = total - wins
        ratio = wins / total if total else 0.0
        return {"asset": asset, "timeframe": timeframe, "wins": wins,
                "losses": losses, "total": total, "win_rate": round(ratio, 4)}

    def win_rate_by_pair(self) -> List[Dict[str, Any]]:
        """Win-rate por cada (par, timeframe) con al menos una senal resuelta."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT asset, timeframe,
                          SUM(result='WIN')  AS wins,
                          SUM(result='LOSS') AS losses
                   FROM signals WHERE result IN ('WIN','LOSS')
                   GROUP BY asset, timeframe
                   ORDER BY wins DESC""").fetchall()
        salida: List[Dict[str, Any]] = []
        for asset, tf, wins, losses in rows:
            total = (wins or 0) + (losses or 0)
            salida.append({"asset": asset, "timeframe": tf, "wins": wins or 0,
                           "losses": losses or 0, "total": total,
                           "win_rate": round((wins or 0) / total, 4) if total
                           else 0.0})
        return salida

    def performance_metrics(self) -> Dict[str, Any]:
        """Metricas globales de rendimiento (resumen para panel/dashboard)."""
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            wins = self.conn.execute(
                "SELECT COUNT(*) FROM signals WHERE result='WIN'").fetchone()[0]
            losses = self.conn.execute(
                "SELECT COUNT(*) FROM signals WHERE result='LOSS'").fetchone()[0]
            pending = self.conn.execute(
                "SELECT COUNT(*) FROM signals WHERE result='PENDING'").fetchone()[0]
            avg_prob = self.conn.execute(
                "SELECT AVG(probability) FROM signals").fetchone()[0]
        resueltas = wins + losses
        return {
            "total_signals": total,
            "resolved": resueltas,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "win_rate": round(wins / resueltas, 4) if resueltas else 0.0,
            "avg_probability": round(avg_prob, 2) if avg_prob is not None else 0.0,
        }

    def close(self) -> None:
        self.conn.close()
