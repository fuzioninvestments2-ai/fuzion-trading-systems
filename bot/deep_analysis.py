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


class DeepAnalyzer:
    def __init__(self, timeframes=DEFAULT_TIMEFRAMES, noise_alpha=0.35,
                 min_candles=8):
        """
        timeframes : tuple de segundos (de menor a mayor).
        noise_alpha: suavizado del filtro de ruido (0-1). Más bajo = más suave.
        min_candles: velas mínimas para que una temporalidad "opine".
        """
        self.timeframes = tuple(timeframes)
        self.noise_alpha = float(noise_alpha)
        self.min_candles = int(min_candles)
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

    def _opinar_temporalidad(self, tf_seconds, ticks_suaves):
        """Un 'analista': construye las velas de SU tiempo y opina."""
        cb = CandleBuilder(tf_seconds)
        for ts, p in ticks_suaves:
            cb.add_tick(p, ts * 1000.0)
        df = cb.to_dataframe(include_forming=True)
        if len(df) < self.min_candles:
            return {"dir": "NEUTRAL", "conf": 0.0, "velas": len(df)}
        _, _, d = ScoringStrategy(self.cfg).analyze(df)
        call_s, put_s = d.get("call_score", 0.0), d.get("put_score", 0.0)
        conf = d.get("confidence", 0.0)
        direction = CALL if call_s > put_s else PUT if put_s > call_s else "NEUTRAL"
        return {"dir": direction, "conf": round(conf, 3), "velas": len(df)}

    def analyze(self, ticks):
        """
        ticks: lista de (timestamp_segundos, precio) en orden cronológico.
        Devuelve el veredicto combinado + el desglose por temporalidad.
        """
        if not ticks:
            return {"veredicto": "SIN DATOS", "direccion": "NEUTRAL",
                    "fuerza": 0.0, "por_tiempo": {}}

        suaves = self._filtrar_ruido(ticks)
        por_tiempo = {tf: self._opinar_temporalidad(tf, suaves)
                      for tf in self.timeframes}

        # Contamos hacia dónde apunta cada temporalidad que sí opinó.
        ups = [tf for tf, v in por_tiempo.items() if v["dir"] == CALL]
        downs = [tf for tf, v in por_tiempo.items() if v["dir"] == PUT]
        opinan = ups + downs
        total = len(self.timeframes)

        # Confianza media de las que apoyan la dirección mayoritaria.
        def _avg(tfs):
            vals = [por_tiempo[t]["conf"] for t in tfs]
            return round(sum(vals) / len(vals), 3) if vals else 0.0

        # LA ECUACIÓN: coincidencia entre temporalidades.
        if ups and downs:
            # Corto y largo se contradicen -> mercado no claro.
            return {"veredicto": "🚫 NO OPERAR", "direccion": "⚠️ conflicto",
                    "fuerza": 0.0, "motivo": "las temporalidades no coinciden",
                    "por_tiempo": por_tiempo}
        if len(ups) >= 2:
            fuerza = _avg(ups)
            v = "✅ OPERAR" if len(ups) == total else "🟡 OPCIONAL"
            return {"veredicto": v, "direccion": "⬆️ UP (CALL)", "fuerza": fuerza,
                    "coinciden": f"{len(ups)}/{total} tiempos",
                    "por_tiempo": por_tiempo}
        if len(downs) >= 2:
            fuerza = _avg(downs)
            v = "✅ OPERAR" if len(downs) == total else "🟡 OPCIONAL"
            return {"veredicto": v, "direccion": "⬇️ DOWN (PUT)", "fuerza": fuerza,
                    "coinciden": f"{len(downs)}/{total} tiempos",
                    "por_tiempo": por_tiempo}
        # Ninguna confluencia suficiente.
        return {"veredicto": "🚫 NO OPERAR",
                "direccion": "⏸️ sin confluencia",
                "fuerza": _avg(opinan),
                "motivo": "pocas temporalidades de acuerdo o pocos datos",
                "por_tiempo": por_tiempo}
