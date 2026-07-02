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
from bot.scoring_strategy import ScoringStrategy, CALL, PUT, weights_for
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
    ("donchian", CALL): "precio en el PISO del canal (soporte, posible rebote)",
    ("donchian", PUT): "precio en el TECHO del canal (resistencia, posible rechazo)",
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

    def _opinar_df(self, df, tf=None, regimen=None):
        """
        Un 'analista' opina sobre un DataFrame de velas. SIEMPRE calcula la
        inclinación (lean) aunque sea débil; marca aparte si está CONFIRMADA
        (confianza >= umbral). Así nunca perdemos la dirección.

        tf / regimen: si se dan, los pesos de los indicadores se AJUSTAN a esa
        temporalidad y régimen (config no fija). Si no, usa los pesos base.
        """
        velas = 0 if df is None else len(df)
        if df is None or velas < self.min_candles:
            return {"dir": "NEUTRAL", "conf": 0.0, "velas": velas,
                    "votes": {}, "confirmado": False, "datos": False}
        pesos = weights_for(tf, regimen) if (tf or regimen) else None
        _, _, d = ScoringStrategy(self.cfg).analyze(df, weights=pesos)
        call_s, put_s = d.get("call_score", 0.0), d.get("put_score", 0.0)
        conf = d.get("confidence", 0.0)
        if call_s > put_s:
            direction = CALL
        elif put_s > call_s:
            direction = PUT
        else:
            direction = "NEUTRAL"
        return {"dir": direction, "conf": round(conf, 3), "velas": velas,
                "votes": d.get("votes", {}),
                "confirmado": conf >= self.min_conf, "datos": True}

    def _opinar_temporalidad(self, tf_seconds, ticks_suaves, regimen=None):
        """Construye las velas de SU tiempo desde ticks y opina (pesos por tiempo)."""
        cb = CandleBuilder(tf_seconds)
        for ts, p in ticks_suaves:
            cb.add_tick(p, ts * 1000.0)
        return self._opinar_df(cb.to_dataframe(include_forming=True),
                               tf=tf_seconds, regimen=regimen)

    def _combinar(self, por_tiempo):
        """
        La ECUACIÓN. Métrica CLARA (0-100%): ALINEACIÓN = % de tiempos que
        coinciden. Bandas: >=75% OPERAR, >=60% OPCIONAL, si no NO OPERAR.
        SIEMPRE devuelve una lectura (nunca "0/0 sin datos" si hay movimiento):
        confirmada (fuerte), inclinación débil, o mercado plano.
        """
        base = {"por_tiempo": por_tiempo}
        con_datos = {tf: v for tf, v in por_tiempo.items() if v.get("datos")}

        if not con_datos:
            base.update(veredicto="🚫 NO OPERAR", direccion="⏸️ sin velas",
                        fuerza=0.0, coinciden="0/0",
                        explicacion="Aún no hay suficientes velas. Deja el bot "
                                    "leyendo este activo un rato y reintenta.")
            return base

        # Inclinación cruda (aunque débil) y confirmada (supera umbral).
        ups_l = [tf for tf, v in con_datos.items() if v["dir"] == CALL]
        downs_l = [tf for tf, v in con_datos.items() if v["dir"] == PUT]
        ups_c = [tf for tf in ups_l if con_datos[tf]["confirmado"]]
        downs_c = [tf for tf in downs_l if con_datos[tf]["confirmado"]]

        if not ups_l and not downs_l:
            base.update(veredicto="🚫 NO OPERAR", direccion="😴 mercado plano",
                        fuerza=0.0, coinciden="0/0",
                        explicacion="Este activo está muy plano ahora (sin "
                                    "movimiento claro). Prueba otro más activo.")
            return base

        opinan_c = len(ups_c) + len(downs_c)

        # CASO 1: hay suficientes tiempos CONFIRMADOS -> señal de verdad.
        if opinan_c >= 2:
            if len(ups_c) >= len(downs_c):
                side, tfs, win = CALL, ups_c, len(ups_c)
            else:
                side, tfs, win = PUT, downs_c, len(downs_c)
            lose = opinan_c - win
            alignment = win / opinan_c
            if lose == 0 and win >= 3 and alignment >= 0.75:
                veredicto = "✅ OPERAR"
            elif lose <= 1 and alignment >= 0.60:
                veredicto = "🟡 OPCIONAL"
            else:
                veredicto = "🚫 NO OPERAR"
            flecha = "⬆️ UP (CALL)" if side == CALL else "⬇️ DOWN (PUT)"
            base.update(veredicto=veredicto, direccion=flecha,
                        fuerza=round(alignment, 3),
                        coinciden=f"{win}/{opinan_c} tiempos",
                        explicacion=_explicar(por_tiempo, side))
            return base

        # CASO 2: hay inclinación pero DÉBIL (no confirmada) -> mostrarla, no operar.
        u, dn = len(ups_l), len(downs_l)
        side = CALL if u >= dn else PUT
        win = max(u, dn)
        alignment = win / (u + dn)
        flecha = "⬆️ UP" if side == CALL else "⬇️ DOWN"
        hacia = "al alza" if side == CALL else "a la baja"
        base.update(veredicto="🚫 NO OPERAR", direccion=f"{flecha} (débil)",
                    fuerza=round(alignment, 3),
                    coinciden=f"{win}/{u + dn} débiles",
                    explicacion=f"Ligera inclinación {hacia}, pero DÉBIL "
                                f"(sin confirmación). Mejor esperar a que se "
                                f"fortalezca.")
        return base

    def analyze(self, ticks, regimen=None):
        """
        ticks: [(timestamp_segundos, precio), ...] en orden cronológico.
        regimen: 'slide'/'oscillate'/'mixto' (opcional) para ajustar los pesos.
        """
        if not ticks:
            return {"veredicto": "SIN DATOS", "direccion": "NEUTRAL",
                    "fuerza": 0.0, "por_tiempo": {}}
        suaves = self._filtrar_ruido(ticks)
        por_tiempo = {tf: self._opinar_temporalidad(tf, suaves, regimen)
                      for tf in self.timeframes}
        return self._combinar(por_tiempo)

    def analyze_frames(self, frames, regimen=None):
        """
        frames: dict {tf_segundos: DataFrame de velas}. Permite mezclar tiempos
        cortos (desde ticks) y largos (desde historial acumulado). Es el modo
        de "lectura continua": los tiempos largos usan las velas que el bot ha
        ido acumulando.
        regimen: ajusta los pesos de indicadores según tendencia/rango.
        """
        if not frames:
            return {"veredicto": "SIN DATOS", "direccion": "NEUTRAL",
                    "fuerza": 0.0, "por_tiempo": {}}
        por_tiempo = {tf: self._opinar_df(df, tf=tf, regimen=regimen)
                      for tf, df in frames.items()}
        return self._combinar(por_tiempo)
