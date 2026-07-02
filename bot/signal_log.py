"""
bot/signal_log.py
=================
Registro y RESOLUCIÓN de las señales que da el bot: cierra el "ciclo de
aprendizaje real".

EL PORQUÉ: hasta ahora el bot aprendía del BACKTEST (simular la estrategia sobre
el histórico). Eso está bien, pero lo más honesto es medir lo que el bot REALMENTE
predijo: cada vez que dice OPERAR/OPCIONAL con dirección, guardamos la señal; más
tarde, con los precios ya conocidos, miramos si ACERTÓ. Así obtenemos un win-rate
REAL del bot (no de un backtest), y podemos mejorar con datos propios.

Modelo (opción binaria): una señal CALL gana si el precio SUBIÓ al vencimiento;
PUT gana si BAJÓ. El precio de vencimiento se toma de la primera vela M1 cuyo
tiempo es >= al vencimiento (usa el historial acumulado, precios reales).

⚠️ HONESTIDAD: esto MIDE, no promete. Un win-rate pasado no garantiza el futuro,
y en OTC (sintético) hay que tomarlo con cautela. Pero medir de verdad es el
primer paso para mejorar de verdad.

SRP: solo registra/resuelve/consulta señales. Reutiliza la conexión y el lock del
HistoryRepository (una sola conexión SQLite = sin contención de bloqueos).
"""

CALL = "CALL"
PUT = "PUT"


class SignalTracker:
    def __init__(self, repo):
        """repo: HistoryRepository (se reutiliza su conexión y su lock)."""
        self.repo = repo
        self.conn = repo.conn
        self._lock = repo._lock
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset      TEXT,
                    timeframe  TEXT,
                    direction  TEXT,        -- CALL / PUT
                    entry_price REAL,
                    entry_ts   INTEGER,     -- ms
                    expiry_ts  INTEGER,     -- ms (cuándo se decide el resultado)
                    result     TEXT,        -- win / loss / tie / NULL (pendiente)
                    resolved   INTEGER DEFAULT 0
                )""")
            self.conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_pend
                                 ON signals (resolved, expiry_ts)""")
            self.conn.commit()

    def record(self, asset, timeframe, direction, entry_price, entry_ts_ms,
               expiry_seconds):
        """
        Guarda una señal PENDIENTE. `direction` debe ser CALL o PUT (las señales
        HOLD/NO OPERAR no se registran: no hay predicción que medir).
        """
        if direction not in (CALL, PUT):
            return None
        expiry_ts = int(entry_ts_ms) + int(expiry_seconds) * 1000
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO signals
                   (asset, timeframe, direction, entry_price, entry_ts, expiry_ts)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (asset, timeframe, direction, float(entry_price),
                 int(entry_ts_ms), expiry_ts))
            self.conn.commit()
            return cur.lastrowid

    def _price_at(self, asset, ts_ms):
        """
        Precio de cierre de la primera vela M1 con tiempo >= ts_ms (el precio al
        vencimiento). None si aún no hay vela tan reciente (señal no resoluble).
        """
        row = self.conn.execute(
            """SELECT close FROM candles
               WHERE asset=? AND timeframe='M1' AND ts >= ?
               ORDER BY ts ASC LIMIT 1""", (asset, int(ts_ms))).fetchone()
        return float(row[0]) if row else None

    def resolve_pending(self, now_ts_ms):
        """
        Resuelve las señales vencidas (expiry_ts <= ahora) cuyo resultado ya se
        puede conocer con el historial acumulado. Devuelve cuántas resolvió.
        """
        with self._lock:
            pend = self.conn.execute(
                """SELECT id, asset, direction, entry_price, expiry_ts
                   FROM signals WHERE resolved=0 AND expiry_ts <= ?""",
                (int(now_ts_ms),)).fetchall()
            n = 0
            for sid, asset, direction, entry, expiry_ts in pend:
                exit_price = self._price_at(asset, expiry_ts)
                if exit_price is None:
                    continue                       # aún sin vela de vencimiento
                if exit_price == entry:
                    result = "tie"
                elif direction == CALL:
                    result = "win" if exit_price > entry else "loss"
                else:                              # PUT
                    result = "win" if exit_price < entry else "loss"
                self.conn.execute(
                    "UPDATE signals SET result=?, resolved=1 WHERE id=?",
                    (result, sid))
                n += 1
            if n:
                self.conn.commit()
            return n

    def stats(self, asset=None):
        """
        Win-rate REAL de las señales resueltas (global o por activo). Devuelve
        {wins, losses, ties, decididas, win_rate, pendientes}.
        """
        cond, params = "resolved=1", []
        if asset:
            cond += " AND asset=?"; params.append(asset)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT result, COUNT(*) FROM signals WHERE {cond}
                    GROUP BY result""", params).fetchall()
            pcond, pparams = "resolved=0", []
            if asset:
                pcond += " AND asset=?"; pparams.append(asset)
            pend = self.conn.execute(
                f"SELECT COUNT(*) FROM signals WHERE {pcond}", pparams).fetchone()[0]
        d = {r: c for r, c in rows}
        wins, losses, ties = d.get("win", 0), d.get("loss", 0), d.get("tie", 0)
        decididas = wins + losses
        win_rate = (wins / decididas) if decididas else None
        return {"wins": wins, "losses": losses, "ties": ties,
                "decididas": decididas,
                "win_rate": round(win_rate, 4) if win_rate is not None else None,
                "pendientes": pend}
