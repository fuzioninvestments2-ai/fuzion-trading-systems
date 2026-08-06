"""
indicators/atr.py (fuzion_fx) — Average True Range (Wilder).

Volatilidad real reciente (rango tipico de las velas). Para dimensionar
stops/objetivos con la realidad del mercado. Incluye gaps (usa el cierre previo).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        period: int = 14) -> float:
    """Ultimo ATR por suavizado de Wilder. 0.0 si faltan datos."""
    h = np.asarray(highs, dtype=np.float64)
    l = np.asarray(lows, dtype=np.float64)
    c = np.asarray(closes, dtype=np.float64)
    n = c.size
    if n < 2 or h.size != n or l.size != n:
        return 0.0
    prev_close = c[:-1]
    tr = np.maximum.reduce([
        h[1:] - l[1:],
        np.abs(h[1:] - prev_close),
        np.abs(l[1:] - prev_close),
    ])
    if tr.size == 0:
        return 0.0
    period = max(1, min(int(period), tr.size))
    val = float(np.mean(tr[:period]))
    for x in tr[period:]:
        val = (val * (period - 1) + float(x)) / period
    return val
