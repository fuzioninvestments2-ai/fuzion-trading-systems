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

import json

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
                    resolved   INTEGER DEFAULT 0,
                    votes      TEXT,         -- JSON {indicador: CALL/PUT/HOLD}
                    meta       TEXT          -- JSON con los datos de validate_signal
                )""")
            self.conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_pend
                                 ON signals (resolved, expiry_ts)""")
            # Migración: añade columnas nuevas si la tabla es antigua.
            cols = [r[1] for r in self.conn.execute(
                "PRAGMA table_info(signals)").fetchall()]
            if "votes" not in cols:
                self.conn.execute("ALTER TABLE signals ADD COLUMN votes TEXT")
            if "meta" not in cols:
                self.conn.execute("ALTER TABLE signals ADD COLUMN meta TEXT")
            self.conn.commit()

    def record(self, asset, timeframe, direction, entry_price, entry_ts_ms,
               expiry_seconds, votes=None, meta=None):
        """
        Guarda una señal PENDIENTE. `direction` debe ser CALL o PUT (las señales
        HOLD/NO OPERAR no se registran: no hay predicción que medir).

        votes: dict opcional {indicador: CALL/PUT/HOLD} en el momento de la señal.
        Se guarda para poder aprender, al resolverla, QUÉ indicadores acertaron
        de verdad (no solo el backtest).
        """
        if direction not in (CALL, PUT):
            return None
        expiry_ts = int(entry_ts_ms) + int(expiry_seconds) * 1000
        votes_json = json.dumps(votes) if votes else None
        meta_json = json.dumps(meta) if meta else None
        # entry_price puede venir None: el precio de entrada se resuelve luego desde la
        # malla M1 en el BORDE de entrada, así se mide el trade real (no el precio del pico).
        ep = float(entry_price) if entry_price is not None else None
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO signals
                   (asset, timeframe, direction, entry_price, entry_ts, expiry_ts,
                    votes, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset, timeframe, direction, ep,
                 int(entry_ts_ms), expiry_ts, votes_json, meta_json))
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
                """SELECT id, asset, direction, entry_price, entry_ts, expiry_ts
                   FROM signals WHERE resolved=0 AND expiry_ts <= ?""",
                (int(now_ts_ms),)).fetchall()
            n = 0
            for sid, asset, direction, entry, entry_ts, expiry_ts in pend:
                # Si no se guardó el precio de entrada, se toma de la malla M1 en el BORDE
                # de entrada: así entrada y salida son las del trade real (misma ventana
                # que la tabla), no el precio del pico.
                if entry is None:
                    entry = self._price_at(asset, entry_ts)
                    if entry is None:
                        continue                   # aún sin vela en el borde de entrada
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

    def learned_multipliers(self, asset, min_signals=15, min_votes=10):
        """
        Multiplicadores de peso APRENDIDOS de las señales REALES ya resueltas de
        un activo (no del backtest). Para cada señal resuelta se reconstruye la
        dirección real del precio a partir de (dirección, resultado):
            subió = (dirección==CALL) == (resultado==win)
        y se puntúa cada voto de indicador guardado. Devuelve
        {multipliers, stats, señales} o None si no hay muestra suficiente.
        """
        from bot.weight_learning import multipliers_from_tally
        from bot.scoring_strategy import BASE_WEIGHTS

        with self._lock:
            rows = self.conn.execute(
                """SELECT direction, result, votes FROM signals
                   WHERE resolved=1 AND asset=? AND votes IS NOT NULL
                     AND result IN ('win','loss')""", (asset,)).fetchall()
        if len(rows) < min_signals:
            return None

        hits = {k: 0 for k in BASE_WEIGHTS}
        total = {k: 0 for k in BASE_WEIGHTS}
        for direction, result, votes_json in rows:
            try:
                votes = json.loads(votes_json)
            except (TypeError, ValueError):
                continue
            subio = (direction == CALL) == (result == "win")
            for name, side in votes.items():
                if name not in total:
                    continue
                if side == CALL:
                    total[name] += 1
                    if subio:
                        hits[name] += 1
                elif side == PUT:
                    total[name] += 1
                    if not subio:
                        hits[name] += 1

        out = multipliers_from_tally(hits, total, min_votes=min_votes)
        out["señales"] = len(rows)
        return out

    def win_rate_reciente(self, asset, timeframe, ultimas=20):
        """
        Acierto REAL de las ÚLTIMAS `ultimas` señales resueltas de un par+tiempo.
        EL PORQUÉ: el corrector necesita el pulso RECIENTE (no el histórico total)
        para detectar cuándo un par empieza a fallar y silenciarlo a tiempo, sin
        arrastrar el error a las siguientes señales. Devuelve (win_rate, muestra):
        win_rate None si no hay ninguna decidida todavía.
        """
        with self._lock:
            rows = self.conn.execute(
                """SELECT result FROM signals
                   WHERE resolved=1 AND asset=? AND timeframe=?
                     AND result IN ('win','loss')
                   ORDER BY expiry_ts DESC LIMIT ?""",
                (asset, timeframe, int(ultimas))).fetchall()
        muestra = len(rows)
        if muestra == 0:
            return None, 0
        wins = sum(1 for (r,) in rows if r == "win")
        return wins / muestra, muestra

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
