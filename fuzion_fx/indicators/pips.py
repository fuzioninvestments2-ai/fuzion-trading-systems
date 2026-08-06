"""
indicators/pips.py (fuzion_fx) — Tamano de pip y conversion por par FX.

Pip = 0.01 si el par incluye JPY, 0.0001 el resto. Los pares llegan con barra
("EUR/USD"); se normaliza a "EURUSD".
"""

from __future__ import annotations

from typing import Optional, Tuple

_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"}


def _norm(pair: str) -> str:
    p = str(pair).upper().replace("/", "").replace("-", "").strip().lstrip("#")
    if p.endswith("_OTC"):
        p = p[:-4]
    return p


def currencies_of(pair: str) -> Optional[Tuple[str, str]]:
    """(base, cotizada) de un par FX; None si no es FX conocido."""
    p = _norm(pair)
    if len(p) == 6 and p[:3] in _CURRENCIES and p[3:] in _CURRENCIES:
        return p[:3], p[3:]
    return None


def pip_size(pair: str) -> float:
    """0.01 si incluye JPY, 0.0001 el resto."""
    return 0.01 if "JPY" in _norm(pair) else 0.0001


def to_pips(distancia_precio: float, pair: str) -> float:
    """Distancia de precio -> pips."""
    return round(abs(float(distancia_precio)) / pip_size(pair), 2)
