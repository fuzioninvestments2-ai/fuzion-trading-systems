"""
indicators/rsi.py (fuzion_fx) — Indice de Fuerza Relativa (Wilder).

RSI en [0,100]. <30 sobreventa (sesgo CALL), >70 sobrecompra (sesgo PUT). Usa el
suavizado de Wilder para no saltar cuando un valor entra/sale de la ventana.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def rsi(closes: Sequence[float], period: int = 14) -> float:
    """Ultimo RSI. 50.0 (neutral) si no hay muestra suficiente."""
    c = np.asarray(closes, dtype=np.float64)
    period = max(1, int(period))
    if c.size < period + 1:
        return 50.0

    delta = np.diff(c)
    ganancias = np.where(delta > 0, delta, 0.0)
    perdidas = np.where(delta < 0, -delta, 0.0)

    avg_g = float(np.mean(ganancias[:period]))
    avg_p = float(np.mean(perdidas[:period]))
    for i in range(period, delta.size):
        avg_g = (avg_g * (period - 1) + ganancias[i]) / period
        avg_p = (avg_p * (period - 1) + perdidas[i]) / period

    if avg_p == 0:
        return 100.0
    rs = avg_g / avg_p
    return float(100.0 - (100.0 / (1.0 + rs)))
