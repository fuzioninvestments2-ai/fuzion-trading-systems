"""
bot/auto_optimize.py
====================
AUTO-OPTIMIZACIÓN: el bot aprende de SUS PROPIOS resultados reales y ajusta el
peso de cada temporalidad. Cierra el bucle "operar -> medir -> ajustar" como un
trader que revisa su bitácora y confía más en lo que le funciona.

Regla (de la guía del usuario):
  - Ventana deslizante: últimos N resultados reales (por defecto 200).
  - Si una temporalidad acierta > 65%  -> su peso += 0.05  (tope 0.30)
  - Si acierta < 45%                    -> su peso -= 0.05  (piso 0.02)
  - Entre 45% y 65%: se deja igual (zona neutra, no toca).
  - Hace falta muestra mínima por temporalidad para no ajustar con ruido.

Es INCREMENTAL (empuja poco a poco, no recalcula de cero) y se PERSISTE en la
misma BD del bot, así cada bot (OTC / real) aprende por separado (usan BD
distintas). El peso se usa luego para dar MÁS voz a las temporalidades que
aciertan en la lectura.

⚠️ HONESTIDAD: esto MIDE y se adapta; no adivina. Un acierto pasado no garantiza
el futuro. Es disciplina basada en datos propios, no una promesa.

SRP: solo calcula y guarda pesos por temporalidad. Sin red. Testeable con asserts.
"""

# Parámetros de la regla (ajustables). Derivan de la guía del usuario.
VENTANA = 200          # últimos N resultados reales que se miran
UMBRAL_SUBE = 0.65     # acierto por encima -> subir peso
UMBRAL_BAJA = 0.45     # acierto por debajo -> bajar peso
PASO = 0.05            # cuánto se mueve el peso por ronda
PESO_MIN = 0.02        # piso (nunca lo apagamos del todo)
PESO_MAX = 0.30        # techo (que ninguna temporalidad domine sola)
PESO_INICIAL = 0.10    # peso de partida de una temporalidad nueva
MUESTRA_MIN = 10       # resultados mínimos de esa temporalidad para ajustar


def winrate_por_timeframe(tracker, window=VENTANA, asset=None):
    """
    Acierto real por temporalidad sobre los últimos `window` resultados resueltos.
    Devuelve {timeframe: {'wins':int,'total':int,'win_rate':float}}.
    Lee del registro de señales del bot (SignalTracker), sin red.
    """
    cond = "resolved=1 AND result IN ('win','loss')"
    params = []
    if asset:
        cond += " AND asset=?"
        params.append(asset)
    with tracker._lock:
        filas = tracker.conn.execute(
            f"""SELECT timeframe, result FROM signals
                WHERE {cond} ORDER BY id DESC LIMIT ?""",
            params + [int(window)]).fetchall()
    tally = {}
    for tf, result in filas:
        d = tally.setdefault(tf, {"wins": 0, "total": 0})
        d["total"] += 1
        if result == "win":
            d["wins"] += 1
    for tf, d in tally.items():
        d["win_rate"] = (d["wins"] / d["total"]) if d["total"] else None
    return tally


def _nuevo_peso(peso_actual, win_rate):
    """Aplica la regla de ajuste a UN peso. Sin efectos secundarios (testeable)."""
    if win_rate is None:
        return peso_actual
    if win_rate > UMBRAL_SUBE:
        return round(min(PESO_MAX, peso_actual + PASO), 4)
    if win_rate < UMBRAL_BAJA:
        return round(max(PESO_MIN, peso_actual - PASO), 4)
    return peso_actual                      # zona neutra: no se toca


class TimeframeOptimizer:
    """
    Guarda y ajusta el peso por temporalidad en la BD del bot. Como cada bot usa
    su propia BD, el aprendizaje queda separado (OTC no contamina al real).
    """

    def __init__(self, tracker):
        self.tracker = tracker
        self.conn = tracker.conn
        self._lock = tracker._lock
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tf_weights (
                    asset     TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    weight    REAL NOT NULL,
                    PRIMARY KEY (asset, timeframe)
                )""")
            self.conn.commit()

    def pesos(self, asset="*"):
        """Pesos guardados de un activo ('*' = global). {timeframe: peso}."""
        with self._lock:
            filas = self.conn.execute(
                "SELECT timeframe, weight FROM tf_weights WHERE asset=?",
                (asset,)).fetchall()
        return {tf: float(w) for tf, w in filas}

    def _guardar(self, asset, timeframe, peso):
        with self._lock:
            self.conn.execute(
                """INSERT INTO tf_weights (asset, timeframe, weight)
                   VALUES (?, ?, ?)
                   ON CONFLICT(asset, timeframe) DO UPDATE SET weight=excluded.weight""",
                (asset, timeframe, float(peso)))
            self.conn.commit()

    def optimizar(self, asset=None, window=VENTANA):
        """
        Revisa los últimos `window` resultados y ajusta el peso de cada
        temporalidad según su acierto. `asset=None` -> global (clave '*').
        Devuelve {timeframe: {'win_rate','muestra','peso_antes','peso_despues'}}.
        Solo ajusta las temporalidades con muestra suficiente (MUESTRA_MIN).
        """
        clave = asset or "*"
        winrates = winrate_por_timeframe(self.tracker, window=window, asset=asset)
        pesos = self.pesos(clave)
        cambios = {}
        for tf, d in winrates.items():
            if d["total"] < MUESTRA_MIN:
                continue                     # poca muestra: no ajustamos con ruido
            antes = pesos.get(tf, PESO_INICIAL)
            despues = _nuevo_peso(antes, d["win_rate"])
            if despues != antes or tf not in pesos:
                self._guardar(clave, tf, despues)
            cambios[tf] = {"win_rate": round(d["win_rate"], 4),
                           "muestra": d["total"],
                           "peso_antes": antes, "peso_despues": despues}
        return cambios
