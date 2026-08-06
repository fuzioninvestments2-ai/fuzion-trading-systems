"""
src/indicators/pips.py
======================
FASE 2: conversion precio->pips por par, para activar los filtros de riesgo que
razonan en pips (ATR y distancia a S/R).

Un "pip" es la unidad minima estandar de un par FX:
  - Pares con JPY: 0.01  (el yen cotiza con 2-3 decimales).
  - Resto de FX  : 0.0001.
No-FX (cripto, acciones, metales, indices) NO tienen pip estandar; ahi se
devuelve None -> el caller pasa el campo como None y el filtro se saltea (mejor
no filtrar que inventar una escala). Honestidad: no se fuerza un pip donde no
existe.

Funciones puras (sin red): se prueban sin internet.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from src.risk.manager import average_true_range

# Codigos ISO de divisa que maneja el bot (para reconocer un par FX real).
_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"}


def currencies_of(pair: str) -> Optional[Tuple[str, str]]:
    """
    (base, cotizada) de un par FX, p. ej. 'EURUSD_otc' -> ('EUR', 'USD').
    None si no es un par FX (cripto/accion/metal/indice).
    """
    p = _normalizar(pair)
    if not _es_fx(p):
        return None
    return p[:3], p[3:]


def _normalizar(pair: str) -> str:
    """Quita sufijo _otc y adornos (#) y pasa a mayusculas."""
    p = str(pair).upper().strip().lstrip("#")
    if p.endswith("_OTC"):
        p = p[:-4]
    return p


def _es_fx(pair_norm: str) -> bool:
    """True si es un par FX de 6 letras con ambas mitades divisa conocida."""
    return (len(pair_norm) == 6
            and pair_norm[:3] in _CURRENCIES
            and pair_norm[3:] in _CURRENCIES)


def pip_size(pair: str) -> Optional[float]:
    """
    Tamano de pip del par. 0.01 si incluye JPY, 0.0001 el resto de FX, None si
    no es FX (cripto/accion/metal/indice: sin pip estandar).
    """
    p = _normalizar(pair)
    if not _es_fx(p):
        return None
    return 0.01 if "JPY" in p else 0.0001


def to_pips(distancia_precio: float, pair: str) -> Optional[float]:
    """Convierte una distancia de PRECIO a pips. None si el par no es FX."""
    ps = pip_size(pair)
    if ps is None:
        return None
    return round(abs(float(distancia_precio)) / ps, 2)


def atr_pips(high: Sequence[float], low: Sequence[float], close: Sequence[float],
             pair: str, period: int = 14) -> Optional[float]:
    """
    ATR del par expresado en pips (reusa average_true_range). None si el par no
    es FX o no hay ATR (datos insuficientes).
    """
    ps = pip_size(pair)
    if ps is None:
        return None
    atr = average_true_range(high, low, close, period)
    if atr <= 0:
        return None
    return round(atr / ps, 2)


def nearest_sr_distance_pips(price: float, levels: Dict[str, List[float]],
                             pair: str) -> Optional[float]:
    """
    Distancia en pips del precio al nivel de Soporte/Resistencia mas cercano.
    `levels`: dict {soportes:[...], resistencias:[...]} (de bot.levels.detect_levels).
    None si el par no es FX o no hay niveles.
    """
    ps = pip_size(pair)
    if ps is None:
        return None
    todos: List[float] = []
    todos.extend(levels.get("soportes", []) or [])
    todos.extend(levels.get("resistencias", []) or [])
    if not todos:
        return None
    dist_precio = min(abs(float(price) - float(l)) for l in todos)
    return round(dist_precio / ps, 2)
