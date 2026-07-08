"""
bot/skills/skill_momentum.py
============================
Estrategia de MOMENTUM (continuación). Contrapeso natural de la reversión: cuando
el mercado está en tendencia (autocorrelación NO negativa y ADX alto), el precio
tiende a seguir. Vota en la dirección del empuje reciente.

Lógica:
  1. Pendiente de las últimas N velas (retorno acumulado) da la dirección.
  2. Fuerza = tamaño del empuje normalizado por la volatilidad.
  3. Solo vota fuerte si NO hay reversión dominante (autocorrelación >= umbral).
"""
import numpy as np

from bot.skills.base_skill import BaseSkill, voto, CALL, PUT, NEUTRAL
from bot.skills.skill_reversion import autocorrelacion

MIN_VELAS = 20
N_EMPUJE = 5
AUTOCORR_TENDENCIA = -0.03    # por encima: no domina la reversión → momentum válido


class SkillMomentum(BaseSkill):
    def __init__(self):
        super().__init__("Momentum", "1.0")

    def analyze(self, market_data):
        df = market_data.get("df")
        if df is None or len(df) < MIN_VELAS:
            return voto(NEUTRAL, 0, 0, "datos insuficientes")
        close = np.asarray(df["close"], dtype=float)
        ret = np.diff(np.log(close[-(N_EMPUJE + 1):]))          # retornos últimas N velas
        empuje = float(ret.sum())
        vol = float(np.std(np.diff(np.log(close[-20:])))) or 1e-9
        fuerza = min(1.0, abs(empuje) / (vol * N_EMPUJE))       # empuje normalizado por vol
        ac = autocorrelacion(close[-60:].tolist())

        if abs(empuje) < vol:                                    # empuje menor que el ruido
            return voto(NEUTRAL, 0, fuerza, f"empuje {empuje:.5f} < ruido", {"autocorr": ac})
        direccion = CALL if empuje > 0 else PUT
        conf = fuerza * 0.7
        motivo = f"empuje {empuje:+.5f} ({N_EMPUJE} velas)"
        # Si domina la reversión (autocorr muy negativa), el momentum es trampa → baja conf.
        if ac < AUTOCORR_TENDENCIA:
            conf *= 0.5
            motivo += f" · autocorr {ac:.3f} (reversión domina, cautela)"
        else:
            motivo += f" · autocorr {ac:.3f} (tendencia ok)"
        return voto(direccion, conf, fuerza, motivo, {"autocorr": ac, "empuje": empuje})
