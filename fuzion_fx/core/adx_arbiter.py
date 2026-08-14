"""
core/adx_arbiter.py (fuzion_fx)
===============================
EL ARBITRO: el ADX decide el "modo" del mercado y con eso cuanto pesa cada
indicador (estrategia de Alex, doc fuente).

PORQUE: un mismo indicador NO vale lo mismo siempre. En tendencia fuerte, la
reversion (RSI/Bollinger) miente y hay que seguir la corriente (EMA/MACD/Donchian).
En rango, al reves. El ADX mide si hay tendencia o no, y aca traducimos eso a
MULTIPLICADORES de peso por indicador.

  ADX < 20   -> Oscillate (rango)          -> reversion pesa mas
  ADX 20-25  -> Transicion (precaucion)    -> pesos neutros (esperar confirmacion)
  ADX > 25   -> Slide (tendencia)          -> tendencia pesa mas
  ADX > 40   -> Slide agresivo (extrema)   -> tendencia pesa aun mas, reversion casi 0

Determinista, SIN red, solo numpy.
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np

# Multiplicadores por indicador segun modo (tabla del doc fuente). VWAP siempre
# 1.0 (nivel neutral); momentum es multiplicador aparte -> 1.0 aca.
PESOS = {
    "oscillate":      {"ema": 0.8, "macd": 0.8, "donchian": 0.7,
                       "rsi": 1.3, "bollinger": 1.3, "estocastico": 1.2,
                       "vwap": 1.0, "momentum": 1.0},
    "transicion":     {"ema": 1.0, "macd": 1.0, "donchian": 1.0,
                       "rsi": 1.0, "bollinger": 1.0, "estocastico": 1.0,
                       "vwap": 1.0, "momentum": 1.0},
    "slide":          {"ema": 1.3, "macd": 1.3, "donchian": 1.2,
                       "rsi": 0.7, "bollinger": 0.7, "estocastico": 0.8,
                       "vwap": 1.0, "momentum": 1.0},
    "slide_agresivo": {"ema": 1.4, "macd": 1.4, "donchian": 1.3,
                       "rsi": 0.5, "bollinger": 0.5, "estocastico": 0.6,
                       "vwap": 1.0, "momentum": 1.0},
}


def _wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Suavizado de Wilder (el que usa el ADX): como una EMA con alfa=1/n."""
    out = np.empty_like(x)
    out[0] = x[0]
    a = 1.0 / n
    for i in range(1, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def adx(candles: Dict[str, Sequence[float]], n: int = 14) -> float:
    """
    ADX de Wilder sobre las velas. Devuelve el ultimo valor (0..100). Sin datos
    suficientes devuelve 0.0 (el arbitro cae a modo transicion, neutro).
    """
    h = np.asarray(candles.get("high", []), float)
    l = np.asarray(candles.get("low", []), float)
    c = np.asarray(candles.get("close", []), float)
    if len(c) < 2 * n + 2:
        return 0.0
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev_c = c[:-1]
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - prev_c), np.abs(l[1:] - prev_c)))
    atr = _wilder(tr, n)
    atr = np.where(atr == 0, 1e-12, atr)
    plus_di = 100.0 * _wilder(plus_dm, n) / atr
    minus_di = 100.0 * _wilder(minus_dm, n) / atr
    suma = plus_di + minus_di
    dx = 100.0 * np.abs(plus_di - minus_di) / np.where(suma == 0, 1e-12, suma)
    return float(_wilder(dx, n)[-1])


def modo(adx_val: float) -> str:
    """Traduce el ADX a modo de mercado (los cortes del doc fuente)."""
    if adx_val <= 0:
        return "transicion"                          # sin dato -> neutro (no oscillate)
    if adx_val > 40:
        return "slide_agresivo"
    if adx_val > 25:
        return "slide"
    if adx_val < 20:
        return "oscillate"
    return "transicion"                              # 20-25: zona de precaucion


def pesos(modo_actual: str) -> Dict[str, float]:
    """Multiplicadores de peso por indicador para ese modo."""
    return dict(PESOS.get(modo_actual, PESOS["transicion"]))


def arbitrar(candles: Dict[str, Sequence[float]]) -> Dict[str, object]:
    """
    Foto del arbitro para un timeframe: {adx, modo, pesos}. Es lo que el motor
    cuantico usa para ponderar los votos de los indicadores en ese tiempo.
    """
    a = adx(candles)
    m = modo(a)
    return {"adx": a, "modo": m, "pesos": pesos(m)}
