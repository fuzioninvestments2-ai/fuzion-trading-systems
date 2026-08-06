"""
indicators/macd.py (fuzion_fx) — MACD.

MACD = EMA(fast) - EMA(slow); senal = EMA(MACD, signal). Histograma = MACD-senal:
>0 impulso alcista (CALL), <0 bajista (PUT).
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

from indicators.ema import ema_series


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> Tuple[float, float, float]:
    """(macd_line, signal_line, histograma) del ultimo punto. Ceros si faltan datos."""
    c = np.asarray(closes, dtype=np.float64)
    if c.size < slow + signal:
        return 0.0, 0.0, 0.0
    macd_line = ema_series(c, fast) - ema_series(c, slow)
    signal_line = ema_series(macd_line, signal)
    hist = macd_line - signal_line
    return float(macd_line[-1]), float(signal_line[-1]), float(hist[-1])
