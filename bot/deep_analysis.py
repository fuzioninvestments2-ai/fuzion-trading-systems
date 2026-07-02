"""
bot/deep_analysis.py
====================
Motor de ANÁLISIS PROFUNDO: la "ecuación" multi-temporalidad, sin ruido.

Idea (traducida del planteamiento del usuario):
  - Un PANEL de analistas, uno por temporalidad (tiempo mínimo … tiempo máximo).
  - Cada uno lee las velas de SU tiempo y opina (sube/baja/neutral).
  - Antes de leer, se FILTRA el ruido (micro-movimientos falsos) para que los
    indicadores lean puntos limpios, no basura.
  - El veredicto final solo es fuerte cuando VARIAS temporalidades COINCIDEN
    (el tiempo corto para la entrada y el largo para la tendencia).
  - Si las temporalidades se CONTRADICEN -> NO operar (el mercado no es claro).

⚠️ HONESTIDAD: esto no adivina la fórmula secreta de Pocket Option (imposible).
Lo que hace es DISCIPLINA: operar solo cuando hay confluencia real de tiempos,
y callar cuando no. No garantiza acierto.

SRP: este módulo solo analiza. No conecta a red ni opera. Se prueba sin internet.
"""

from bot.candles import CandleBuilder
from bot.scoring_strategy import ScoringStrategy, CALL, PUT
from bot.config import TradingConfig

# Temporalidades por defecto (segundos): corto, medio, largo = "mín … máx".
DEFAULT_TIMEFRAMES = (15, 60, 300)     # 15s, 1m, 5m

# Todas las temporalidades que el usuario quiere disponibles (segundos):
ALL_TIMEFRAMES = {
    "5s": 5, "10s": 10, "15s": 15, "30s": 30,
    "1m": 60, "2m": 120, "3m": 180, "4m": 240, "5m": 300,
    "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1D": 86400,
}


# Frases educativas por indicador y dirección (para explicar la lectura, como
# hacen los bots que "enseñan" al trader).
_EXPLICA = {
    ("rsi", CALL): "RSI en sobreventa (posible rebote al alza)",
    ("rsi", PUT): "RSI en sobrecompra (posible caída)",
    ("macd", CALL): "MACD con impulso alcista",
    ("macd", PUT): "MACD con impulso bajista",
    ("bollinger", CALL): "precio en la banda BAJA de Bollinger (rebote)",
    ("bollinger", PUT): "precio en la banda ALTA de Bollinger (rechazo)",
    ("moving_averages", CALL): "medias móviles apuntando al alza",
    ("moving_averages", PUT): "medias móviles apuntando a la baja",
    ("stochastic", CALL): "estocástico girando al alza",
    ("stochastic", PUT): "estocástico girando a la baja",
}


def _explicar(por_tiempo, side):
    """
    Arma una explicación en palabras de POR QUÉ el bot ve esa dirección,
    juntando los indicadores que apoyan `side` en los tiempos alineados.
    """
    razones = []
    for tf, v in por_tiempo.items():
        if v.get("dir") != side:
            continue
        for ind, voto in v.get("votes", {}).items():
            if voto == side and (ind, side) in _EXPLICA:
                frase = _EXPLICA[(ind, side)]
                if frase not in razones:
                    razones.append(frase)
    if not razones:
        return "Varios tiempos coinciden en la dirección."
    return "; ".join(razones[:4]) + "."


class DeepAnalyzer:
    def __init__(self, timeframes=DEFAULT_TIMEFRAMES, noise_alpha=0.35,
                 min_candles=6, min_conf=0.25):
        """
        timeframes : tuple de segundos (de menor a mayor).
        noise_alpha: suavizado del filtro de ruido (0-1). Más bajo = más suave.
        min_candles: velas mínimas para que una temporalidad "opine".
        min_conf   : confianza mínima para que un tiempo dé dirección (por debajo
                     de esto opina NEUTRAL). Es el umbral que la CALIBRACIÓN
                     ajusta con el historial de cada activo.
        """
        self.timeframes = tuple(timeframes)
        self.noise_alpha = float(noise_alpha)
        self.min_candles = int(min_candles)
        self.min_conf = float(min_conf)
        cfg = TradingConfig(stack_method="aggressive")
        cfg.min_confidence = 0.25
        self.cfg = cfg

    def _filtrar_ruido(self, ticks):
        """
        Suaviza los precios con una media exponencial para quitar micro-ruido.
        EL PORQUÉ: un tick suelto puede ser un salto falso; suavizando, los
        indicadores leen la tendencia real y no cada temblor.
        """
        out = []
        s = None
        for ts, p in ticks:
            s = p if s is None else self.noise_alpha * p + (1 - self.noise_alpha) * s
            out.append((ts, s))
        return out

    def _opinar_df(self, df):
        """Un 'analista' opina sobre un DataFrame de velas ya construido."""
        velas = 0 if df is None else len(df)
        if df is None or velas < self.min_candles:
            return {"dir": "NEUTRAL", "conf": 0.0, "velas": velas, "votes": {}}
        _, _, d = ScoringStrategy(self.cfg).analyze(df)
        call_s, put_s = d.get("call_score", 0.0), d.get("put_score", 0.0)
        conf = d.get("confidence", 0.0)
        # Solo opina dirección si supera el umbral aprendido; si no, NEUTRAL.
        if conf < self.min_conf:
            direction = "NEUTRAL"
        else:
            direction = CALL if call_s > put_s else PUT if put_s > call_s else "NEUTRAL"
        return {"dir": direction, "conf": round(conf, 3), "velas": velas,
                "votes": d.get("votes", {})}

    def _opinar_temporalidad(self, tf_seconds, ticks_suaves):
        """Construye las velas de SU tiempo desde ticks y opina."""
        cb = CandleBuilder(tf_seconds)
        for ts, p in ticks_suaves:
            cb.add_tick(p, ts * 1000.0)
        return self._opinar_df(cb.to_dataframe(include_forming=True))

    def _combinar(self, por_tiempo):
        """
        La ECUACIÓN: combina las opiniones de TODA la escalera de tiempos por
        MAYORÍA/alineación, y genera una explicación educativa.
        """
        ups = [tf for tf, v in por_tiempo.items() if v["dir"] == CALL]
        downs = [tf for tf, v in por_tiempo.items() if v["dir"] == PUT]
        opinan = len(ups) + len(downs)
        u, dn = len(ups), len(downs)

        def _avg(tfs):
            vals = [por_tiempo[t]["conf"] for t in tfs]
            return round(sum(vals) / len(vals), 3) if vals else 0.0

        base = {"por_tiempo": por_tiempo}

        if opinan == 0:
            base.update(veredicto="🚫 NO OPERAR", direccion="⏸️ sin datos",
                        fuerza=0.0, explicacion="Aún no hay lectura clara.")
            return base

        # ¿Hay una dirección dominante y alineada?
        if u > 0 and dn > 0:
            # Mezcla: solo pasa si una lado DOMINA claramente (3x y >=3 tiempos).
            if u >= 3 and u >= 3 * dn:
                return self._resultado(base, CALL, ups, opinan, "🟡 OPCIONAL",
                                       por_tiempo)
            if dn >= 3 and dn >= 3 * u:
                return self._resultado(base, PUT, downs, opinan, "🟡 OPCIONAL",
                                       por_tiempo)
            base.update(veredicto="🚫 NO OPERAR", direccion="⚠️ conflicto",
                        fuerza=0.0,
                        explicacion="Los tiempos se contradicen: no hay "
                                    "alineación. Mejor esperar.")
            return base

        # Todos los que opinan van al mismo lado.
        if u > 0:
            v = "✅ OPERAR" if u >= max(3, int(opinan * 0.6)) else "🟡 OPCIONAL"
            return self._resultado(base, CALL, ups, opinan, v, por_tiempo)
        v = "✅ OPERAR" if dn >= max(3, int(opinan * 0.6)) else "🟡 OPCIONAL"
        return self._resultado(base, PUT, downs, opinan, v, por_tiempo)

    def _resultado(self, base, side, tfs, opinan, veredicto, por_tiempo):
        conf = round(sum(por_tiempo[t]["conf"] for t in tfs) / len(tfs), 3)
        flecha = "⬆️ UP (CALL)" if side == CALL else "⬇️ DOWN (PUT)"
        base.update(veredicto=veredicto, direccion=flecha, fuerza=conf,
                    coinciden=f"{len(tfs)}/{opinan} tiempos",
                    explicacion=_explicar(por_tiempo, side))
        return base

    def analyze(self, ticks):
        """ticks: [(timestamp_segundos, precio), ...] en orden cronológico."""
        if not ticks:
            return {"veredicto": "SIN DATOS", "direccion": "NEUTRAL",
                    "fuerza": 0.0, "por_tiempo": {}}
        suaves = self._filtrar_ruido(ticks)
        por_tiempo = {tf: self._opinar_temporalidad(tf, suaves)
                      for tf in self.timeframes}
        return self._combinar(por_tiempo)

    def analyze_frames(self, frames):
        """
        frames: dict {tf_segundos: DataFrame de velas}. Permite mezclar tiempos
        cortos (desde ticks) y largos (desde historial acumulado). Es el modo
        de "lectura continua": los tiempos largos usan las velas que el bot ha
        ido acumulando.
        """
        if not frames:
            return {"veredicto": "SIN DATOS", "direccion": "NEUTRAL",
                    "fuerza": 0.0, "por_tiempo": {}}
        por_tiempo = {tf: self._opinar_df(df) for tf, df in frames.items()}
        return self._combinar(por_tiempo)
