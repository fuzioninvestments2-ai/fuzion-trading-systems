"""
indicators/bollinger.py (fuzion_fx) — Bandas de Bollinger.

SMA +/- k*desviacion. Precio en la banda inferior = sobreventa (CALL); en la
superior = sobrecompra (PUT). El ancho mide volatilidad.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np


def bollinger(closes: Sequence[float], period: int = 20,
              std: float = 2.0) -> Tuple[float, float, float]:
    """(banda_superior, media, banda_inferior). Colapsan al ultimo precio si faltan datos."""
    c = np.asarray(closes, dtype=np.float64)
    period = max(1, int(period))
    if c.size < period:
        ult = float(c[-1]) if c.size else 0.0
        return ult, ult, ult
    ventana = c[-period:]
    media = float(np.mean(ventana))
    desv = float(np.std(ventana))          # ddof=0: convencion de Bollinger
    return media + std * desv, media, media - std * desv
