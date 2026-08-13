"""
core/candle_patterns.py (fuzion_fx)
===================================
Patrones de velas japonesas sobre velas OHLC en formato del sistema
({"open":[...],"high":[...],"low":[...],"close":[...]}). La FORMA de la vela
cuenta algo que los indicadores (que promedian) no ven: rechazo, indecision,
reversion. Es una pieza mas de la "formula de tiempo" (junto a los indicadores y
la convergencia multi-temporalidad).

Devuelve un voto direccional:  +1 (alcista) / -1 (bajista) / 0 (neutral).
La INDECISION (doji) devuelve 0 aparte (marca "no entrar" en esa vela).

Reusa la logica probada de bot/candle_patterns.py, adaptada al dict de listas
(sin pandas). Determinista, sin red.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

CALL = 1
PUT = -1


def _partes(o: float, h: float, l: float, c: float):
    """Cuerpo, mechas y rango de una vela (todos >= 0)."""
    rango = max(h - l, 1e-12)
    cuerpo = abs(c - o)
    mecha_sup = h - max(o, c)
    mecha_inf = min(o, c) - l
    return rango, cuerpo, mecha_sup, mecha_inf


def detectar(candles: Dict[str, Sequence[float]], doji_ratio: float = 0.1,
             mecha_ratio: float = 2.0, marubozu_ratio: float = 0.9) -> Dict[str, Any]:
    """
    Lee la ULTIMA vela (y la previa para envolventes). Devuelve:
      {lean: +1/-1/0, indecision: bool, patrones: [str]}.
    lean resume el sesgo de los patrones; indecision True = doji (no entrar).
    """
    res: Dict[str, Any] = {"lean": 0, "indecision": False, "patrones": []}
    close = list(candles.get("close", []))
    n = len(close)
    if n < 1:
        return res
    o = float(candles["open"][-1]); h = float(candles["high"][-1])
    l = float(candles["low"][-1]); c = float(close[-1])
    rango, cuerpo, m_sup, m_inf = _partes(o, h, l, c)

    call = put = 0
    eps = 1e-9
    hammer = (m_inf >= mecha_ratio * max(cuerpo, eps) and m_inf > 2.0 * m_sup)
    star = (m_sup >= mecha_ratio * max(cuerpo, eps) and m_sup > 2.0 * m_inf)

    if hammer:
        res["patrones"].append("martillo"); call += 1
    elif star:
        res["patrones"].append("estrella"); put += 1
    elif cuerpo <= doji_ratio * rango:
        res["patrones"].append("doji"); res["indecision"] = True

    if cuerpo >= marubozu_ratio * rango:
        if c > o:
            res["patrones"].append("marubozu_alcista"); call += 1
        else:
            res["patrones"].append("marubozu_bajista"); put += 1

    if n >= 2:
        o0 = float(candles["open"][-2]); c0 = float(candles["close"][-2])
        cuerpo0 = abs(c0 - o0)
        if c0 < o0 and c > o and c >= o0 and o <= c0 and cuerpo > cuerpo0:
            res["patrones"].append("envolvente_alcista"); call += 1
        elif c0 > o0 and c < o and c <= o0 and o >= c0 and cuerpo > cuerpo0:
            res["patrones"].append("envolvente_bajista"); put += 1

    if res["indecision"]:
        res["lean"] = 0
    elif call > put:
        res["lean"] = CALL
    elif put > call:
        res["lean"] = PUT
    return res
