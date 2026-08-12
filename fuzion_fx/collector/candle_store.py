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
from typing import Dict, List, Optional, Tuple


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
        # candles_real: velas OHLC REALES que PO envia por on_history (fuente de
        # verdad). Tabla SEPARADA de `candles` (ticks ralos, backup) para que el
        # OHLC real sea identificable y priorizable en la lectura de senales y en
        # la resolucion. Misma forma y PRIMARY KEY (se reescribe al reenviarse).
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS candles_real (
                pair    TEXT,
                tf      INTEGER,
                ts      INTEGER,
                open    REAL,
                high    REAL,
                low     REAL,
                close   REAL,
                volume  REAL DEFAULT 0,
                PRIMARY KEY (pair, tf, ts)
            )""")
        # payouts: pago REAL (%) por par, que PO manda en updateAssets. El colector
        # (unica conexion) lo escribe; los 4 bots lo leen para NO emitir en activos
        # con pago bajo (el usuario exige pago >= 72%). ts = ultima actualizacion.
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS payouts (
                pair    TEXT PRIMARY KEY,
                payout  REAL,
                ts      INTEGER
            )""")
        self.conn.commit()

    def upsert_payout(self, pair: str, payout: float, ts: int) -> None:
        """Guarda/actualiza el pago real (%) de un par."""
        self.conn.execute(
            """INSERT INTO payouts (pair, payout, ts) VALUES (?, ?, ?)
               ON CONFLICT(pair) DO UPDATE SET payout=excluded.payout,
                 ts=excluded.ts""",
            (pair, float(payout), int(ts)))
        self.conn.commit()

    def get_payout(self, pair: str) -> Optional[float]:
        """Pago real (%) del par, o None si el colector aun no lo recibio."""
        row = self.conn.execute(
            "SELECT payout FROM payouts WHERE pair=? LIMIT 1", (pair,)).fetchone()
        return float(row[0]) if row else None

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

    def upsert_real_candle(self, pair: str, tf: int, ts: int, o: float, h: float,
                           l: float, c: float, volume: float = 0.0) -> None:
        """
        Inserta o actualiza una vela REAL (OHLC de PO por on_history). A diferencia
        del tick, aca se reescribe TODO (incluido open): PO reenvia la vela ya
        cerrada y su version mas reciente es la buena.
        """
        self.conn.execute(
            """INSERT INTO candles_real (pair, tf, ts, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(pair, tf, ts) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            (pair, int(tf), int(ts), float(o), float(h), float(l), float(c),
             float(volume)))
        self.conn.commit()

    def _get_candles(self, tabla: str, pair: str, tf: int,
                     count: int) -> Optional[Dict[str, List[float]]]:
        """Lectura comun de velas (tabla `candles` o `candles_real`)."""
        rows = self.conn.execute(
            f"""SELECT ts, open, high, low, close, volume FROM {tabla}
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

    def get_candles(self, pair: str, tf: int,
                    count: int = 200) -> Optional[Dict[str, List[float]]]:
        """Ultimas `count` velas de TICKS (backup) del par+tf. None si no hay."""
        return self._get_candles("candles", pair, int(tf), int(count))

    def get_real_candles(self, pair: str, tf: int,
                         count: int = 200) -> Optional[Dict[str, List[float]]]:
        """Ultimas `count` velas REALES (fuente de verdad) del par+tf. None si no hay."""
        return self._get_candles("candles_real", pair, int(tf), int(count))

    def price_at(self, pair: str, tf: int, ts: int) -> Optional[float]:
        """Cierre de la primera vela (tick) con ts >= al pedido. Backup/legado."""
        row = self.conn.execute(
            """SELECT close FROM candles WHERE pair=? AND tf=? AND ts >= ?
               ORDER BY ts ASC LIMIT 1""", (pair, int(tf), int(ts))).fetchone()
        return float(row[0]) if row else None

    def price_at_real(self, pair: str, tf: int, ts: int) -> Optional[float]:
        """
        Cierre de la vela REAL cuyo bucket CONTIENE `ts` (para resolver contra el
        precio real de PO al vencimiento). bucket = ts - (ts % tf), misma
        convencion que el aggregator. None si no hay esa vela real (no se
        interpola ni se busca una lejana: sin dato real -> lo maneja el caller).
        """
        tf = int(tf)
        bucket = int(ts) - (int(ts) % tf) if tf > 0 else int(ts)
        row = self.conn.execute(
            """SELECT close FROM candles_real WHERE pair=? AND tf=? AND ts=?
               LIMIT 1""", (pair, tf, bucket)).fetchone()
        return float(row[0]) if row else None

    def real_candle_at(self, pair: str, tf: int, bucket: int
                       ) -> Optional[Tuple[float, float]]:
        """
        (open, close) de la vela REAL en el bucket EXACTO `bucket` (un multiplo de
        tf). Es la vela que el humano opera de punta a punta: entra en open (borde)
        y vence en close (borde+tf). None si no hay esa vela real. No interpola.
        """
        row = self.conn.execute(
            """SELECT open, close FROM candles_real WHERE pair=? AND tf=? AND ts=?
               LIMIT 1""", (pair, int(tf), int(bucket))).fetchone()
        return (float(row[0]), float(row[1])) if row else None

    def close(self) -> None:
        self.conn.close()
