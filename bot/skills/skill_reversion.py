"""
bot/skills/skill_reversion.py
=============================
Estrategia de REVERSIÓN a la media. Nace del hallazgo del estudio FX: la
autocorrelación de retornos es NEGATIVA (−0.05 a −0.11) en 1m-30m → el precio
tiende a devolverse tras un empujón. Este skill apuesta a ese retorno.

Lógica:
  1. Posición del precio en las Bandas de Bollinger (20, 2σ).
  2. Si el precio pincha la banda superior → PUT (esperar bajada); inferior → CALL.
  3. FILTRO honesto: solo vota fuerte si la autocorrelación reciente es negativa
     (hay memoria de reversión). Si es ~0, el mercado está en régimen de azar y se
     baja la confianza — no se fuerza la señal.
"""
import numpy as np

from bot.scoring_strategy import Indicators, _last
from bot.skills.base_skill import BaseSkill, voto, CALL, PUT, NEUTRAL

MIN_VELAS = 20
AUTOCORR_MEMORIA = -0.03      # umbral: por debajo hay reversión aprovechable


def autocorrelacion(cierres, lag=1):
    """Autocorrelación de log-retornos (lag 1). 0 = sin memoria."""
    if len(cierres) < lag + 3:
        return 0.0
    ret = np.diff(np.log(np.asarray(cierres, dtype=float)))
    if len(ret) <= lag:
        return 0.0
    a, b = ret[:-lag], ret[lag:]
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


class SkillReversion(BaseSkill):
    def __init__(self):
        super().__init__("Reversion", "1.0")

    def analyze(self, market_data):
        df = market_data.get("df")
        if df is None or len(df) < MIN_VELAS:
            return voto(NEUTRAL, 0, 0, "datos insuficientes")
        close = df["close"]
        c = float(close.iloc[-1])
        up, mid, lo, _pb = Indicators.bollinger_bands(close, 20, 2.0)
        u, m, d = _last(up), _last(mid), _last(lo)
        if None in (u, m, d) or u <= d:
            return voto(NEUTRAL, 0, 0, "bandas no disponibles")

        # Posición normalizada dentro de las bandas: +1 en la superior, −1 en la inferior.
        pos = (c - m) / ((u - d) / 2) if (u - d) else 0.0
        ac = autocorrelacion(close.tail(60).tolist())

        if pos >= 1.0:
            direccion, motivo = PUT, f"precio en/encima banda superior (pos {pos:.2f})"
        elif pos <= -1.0:
            direccion, motivo = CALL, f"precio en/debajo banda inferior (pos {pos:.2f})"
        else:
            return voto(NEUTRAL, 0, abs(pos), f"dentro de bandas (pos {pos:.2f})",
                        {"autocorr": ac, "pos": pos})

        fuerza = min(1.0, abs(pos))
        conf = fuerza * 0.7                                  # techo 70% para un solo skill
        # Filtro de memoria: sin autocorrelación negativa, el régimen es azar → baja conf.
        if ac > AUTOCORR_MEMORIA:
            conf *= 0.5
            motivo += f" · autocorr {ac:.3f} débil (régimen azar)"
        else:
            motivo += f" · autocorr {ac:.3f} confirma reversión"
        return voto(direccion, conf, fuerza, motivo,
                    {"autocorr": ac, "pos": pos, "upper": u, "lower": d})
