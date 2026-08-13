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
                    entry_ts      INTEGER,     -- borde de vela que OPERA el humano
                    resolved      INTEGER DEFAULT 0,
                    result        TEXT,        -- win / loss / tie / NULL
                    pnl           REAL DEFAULT 0
                )""")
            self.conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_setup
                                 ON signals (setup_id, resolved)""")
            # Migracion: agregar entry_ts a bases viejas (sin la columna). Guarda el
            # MISMO borde de entrada que la tarjeta le anuncia al humano, para que la
            # liquidacion use EXACTAMENTE esa vela (antes se recalculaba desde ts y
            # podia caer en otra vela -> win/loss y horarios cruzados).
            cols = {r[1] for r in self.conn.execute(
                "PRAGMA table_info(signals)").fetchall()}
            if "entry_ts" not in cols:
                self.conn.execute("ALTER TABLE signals ADD COLUMN entry_ts INTEGER")
            # fuerza = convergencia multi-temporalidad (0..1) al emitir. Se guarda
            # para MEDIR el acierto por fuerza (probar que la confluencia alta gana).
            if "fuerza" not in cols:
                self.conn.execute("ALTER TABLE signals ADD COLUMN fuerza REAL")
            self.conn.commit()

    def save_signal(self, rec: Dict[str, Any]) -> int:
        """Guarda una senal emitida (pendiente de resultado). Devuelve su id.

        entry_ts = borde de vela que el humano opera (el que anuncia la tarjeta).
        Se persiste para liquidar contra ESA vela exacta. Si el bot no lo provee,
        None (la liquidacion cae al calculo legado desde ts).
        """
        ts = int(rec.get("ts") or time.time())
        entry_ts = rec.get("entry_ts")
        entry_ts = int(entry_ts) if entry_ts is not None else None
        fuerza = rec.get("fuerza")
        fuerza = float(fuerza) if fuerza is not None else None
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO signals
                   (ts, pair, timeframe, direction, setup_id, confirmations,
                    price, atr, entry_ts, fuerza)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, rec.get("pair", ""), rec.get("timeframe", ""),
                 rec.get("direction", ""), rec.get("setup_id"),
                 int(rec.get("confirmations", 0)), float(rec.get("price", 0.0)),
                 float(rec.get("atr", 0.0)), entry_ts, fuerza))
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
                """SELECT id, pair, timeframe, direction, price, ts, entry_ts
                   FROM signals WHERE resolved=0 AND ts <= ?
                   ORDER BY ts ASC""", (int(cutoff_ts),)).fetchall()
        return [{"id": r[0], "pair": r[1], "timeframe": r[2], "direction": r[3],
                 "price": r[4], "ts": r[5], "entry_ts": r[6]} for r in rows]

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

    def win_rate_by_fuerza(self, umbral: float = 0.45) -> Dict[str, Any]:
        """
        Acierto separando señales FUERTES (fuerza >= umbral) de DEBILES (< umbral),
        sobre las resueltas con resultado real. Sirve para PROBAR con los datos
        propios que la confluencia alta gana mas (y calibrar el umbral del badge).
        Las señales sin fuerza registrada (viejas) se ignoran.
        """
        with self._lock:
            rows = self.conn.execute(
                """SELECT fuerza, result FROM signals
                   WHERE resolved=1 AND result IN ('win','loss')
                     AND fuerza IS NOT NULL""").fetchall()

        def _tally(sel):
            t = len(sel)
            w = sum(1 for _, r in sel if r == "win")
            return {"trades": t, "wins": w,
                    "win_pct": round(100.0 * w / t, 1) if t else 0.0}

        fuertes = [(f, r) for f, r in rows if f >= umbral]
        debiles = [(f, r) for f, r in rows if f < umbral]
        return {"umbral": umbral, "fuertes": _tally(fuertes),
                "debiles": _tally(debiles)}

    def signals_in_range(self, start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
        """Senales EMITIDAS con ts en [start_ts, end_ts) (para el resumen diario)."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT ts, pair, direction, resolved, result, pnl
                   FROM signals WHERE ts >= ? AND ts < ? ORDER BY ts ASC""",
                (int(start_ts), int(end_ts))).fetchall()
        return [{"ts": r[0], "pair": r[1], "direction": r[2], "resolved": r[3],
                 "result": r[4], "pnl": r[5]} for r in rows]

    def trailing_losses(self, pair: str) -> int:
        """
        Perdidas CONSECUTIVAS al final del historial resuelto del par. Sirve para
        derivar el modo recuperacion desde la DB (el estado en memoria del
        RiskManager no lo ve un proceso separado como el scheduler del resumen).
        Una ganadora corta la racha (igual que RiskManager.register_result).
        """
        with self._lock:
            rows = self.conn.execute(
                """SELECT result FROM signals
                   WHERE pair=? AND resolved=1 AND result IN ('win','loss')
                   ORDER BY ts DESC, id DESC""", (pair,)).fetchall()
        n = 0
        for (r,) in rows:
            if r == "loss":
                n += 1
            else:
                break                              # una ganadora corta la racha
        return n

    def emitted_count(self) -> int:
        """Total de senales emitidas de toda la historia (acumulado)."""
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()
        return int(row[0])

    def close(self) -> None:
        with self._lock:
            self.conn.close()
