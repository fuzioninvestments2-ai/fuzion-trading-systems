"""
indicators/ema.py (fuzion_fx) — Media Movil Exponencial.

EMA pondera mas las velas recientes. El par rapida/lenta (9/21) lee tendencia:
rapida por encima de lenta = sesgo alcista (CALL); por debajo = bajista (PUT).
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np


def ema_series(values: Sequence[float], period: int) -> np.ndarray:
    """Serie EMA completa. alpha = 2/(period+1); siembra con el primer dato."""
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return v
    period = max(1, int(period))
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(v)
    out[0] = v[0]
    for i in range(1, v.size):
        out[i] = alpha * v[i] + (1.0 - alpha) * out[i - 1]
    return out


def ema(values: Sequence[float], period: int) -> float:
    """Ultimo valor de la EMA (0.0 si no hay datos)."""
    s = ema_series(values, period)
    return float(s[-1]) if s.size else 0.0


def calculate_ema_pair(closes: Sequence[float], fast: int,
                       slow: int) -> Tuple[float, float]:
    """(ema_fast, ema_slow) del ultimo punto: comodidad para el motor de senal."""
    return ema(closes, fast), ema(closes, slow)
