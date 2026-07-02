"""
bot/calibration.py
==================
CALIBRACIÓN que "aprende": busca en el historial de un activo qué umbral de
confianza habría funcionado mejor, y lo propone para las próximas señales.

Es el "entrenamiento continuo": cuanto más historial hay, más fiable la
calibración.

⚠️ HONESTIDAD: calibrar sobre el pasado NO garantiza el futuro (y en OTC, que es
sintético, aún menos). Ajusta la DISCIPLINA (cuán exigente es el bot), no la
suerte. Es una guía, no una promesa.

SRP: solo calcula el mejor umbral. No opera ni conecta a red.
"""

import copy

from bot.backtester import backtest
from bot.config import get_preset


def calibrate(candles_df, valores=(0.15, 0.20, 0.25, 0.30, 0.40, 0.50),
              min_signals=8, expiry_horizon=1):
    """
    Prueba varios umbrales sobre el historial (backtest) y devuelve el que dio
    mejor win-rate con suficientes señales. Devuelve un dict o None si no hay
    datos suficientes.
    """
    if candles_df is None or len(candles_df) < 60:
        return None

    base = get_preset("agresivo")
    mejor = None
    for v in valores:
        cfg = copy.copy(base)
        cfg.min_confidence = v
        r = backtest(cfg, candles_df, expiry_horizon=expiry_horizon)
        if r["signals"] < min_signals:      # muy pocas señales -> poco fiable
            continue
        score = r["win_rate"]
        if mejor is None or score > mejor["score"]:
            mejor = {"min_confidence": v, "score": round(score, 3),
                     "señales": r["signals"], "win_rate": r["win_rate"]}
    return mejor
