"""
bot/skills/skill_regime.py
==========================
Skill de RÉGIMEN de mercado. Detecta si el mercado está en TENDENCIA o en RANGO y
elige la estrategia adecuada:
  - Tendencia (ADX alto y autocorrelación no negativa) → MOMENTUM (seguir).
  - Rango / reversión (ADX bajo o autocorrelación negativa) → REVERSIÓN (contra).
Así no aplica una sola lógica a ciegas: usa la que encaja con el estado actual.

Reutiliza los skills existentes (no duplica): delega en SkillMomentum o
SkillReversion según el régimen, y añade el régimen detectado al motivo.
"""
import numpy as np

from bot.skills.base_skill import BaseSkill, voto, NEUTRAL
from bot.skills.skill_reversion import SkillReversion, autocorrelacion
from bot.skills.skill_momentum import SkillMomentum

MIN_VELAS = 30
ADX_TENDENCIA = 25.0
AUTOCORR_REVERSION = -0.03


def calcular_adx(df, periodo=14):
    """ADX clásico (Wilder). Mide FUERZA de tendencia (0-100), no dirección."""
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    if len(c) < periodo * 2 + 1:
        return 0.0
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])

    def _suavizar(x):
        # Media móvil de Wilder (aprox: media simple de la ventana).
        return np.convolve(x, np.ones(periodo) / periodo, mode="valid")

    atr = _suavizar(tr)
    atr[atr == 0] = 1e-9
    pdi = 100 * _suavizar(plus_dm) / atr
    mdi = 100 * _suavizar(minus_dm) / atr
    suma = pdi + mdi
    suma[suma == 0] = 1e-9
    dx = 100 * np.abs(pdi - mdi) / suma
    if len(dx) < periodo:
        return float(dx[-1]) if len(dx) else 0.0
    adx = np.convolve(dx, np.ones(periodo) / periodo, mode="valid")
    return float(adx[-1]) if len(adx) else 0.0


class SkillMarketRegime(BaseSkill):
    def __init__(self):
        super().__init__("MarketRegime", "1.0")
        self._rev = SkillReversion()
        self._mom = SkillMomentum()

    def analyze(self, market_data):
        df = market_data.get("df")
        if df is None or len(df) < MIN_VELAS:
            return voto(NEUTRAL, 0, 0, "datos insuficientes")
        adx = calcular_adx(df)
        ac = autocorrelacion(df["close"].astype(float).tail(60).tolist())

        if adx >= ADX_TENDENCIA and ac >= AUTOCORR_REVERSION:
            base = self._mom.analyze(market_data)
            regimen = f"TENDENCIA (ADX {adx:.0f}, autocorr {ac:.3f}) → momentum"
        else:
            base = self._rev.analyze(market_data)
            regimen = f"RANGO (ADX {adx:.0f}, autocorr {ac:.3f}) → reversión"
        extra = dict(base.get("indicators_used") or {})
        extra.update({"adx": round(adx, 1), "autocorr": round(ac, 3)})
        return voto(base["direction"], base["confidence"], base["signal_strength"],
                    f"{regimen} · {base['reason']}", extra)
