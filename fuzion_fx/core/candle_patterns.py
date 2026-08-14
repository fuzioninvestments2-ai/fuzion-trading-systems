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


# patron -> (direccion, magnitud del ajuste) segun el doc fuente de Alex. El
# envolvente pesa mas (+15%) que el marubozu (+12%) que el martillo/estrella
# (+10%). El doji se maneja aparte (-20% e indecision).
_AJUSTE = {
    "martillo":           (CALL, 0.10),
    "estrella":           (PUT, 0.10),
    "marubozu_alcista":   (CALL, 0.12),
    "marubozu_bajista":   (PUT, 0.12),
    "envolvente_alcista": (CALL, 0.15),
    "envolvente_bajista": (PUT, 0.15),
}
CONTRADICTORIO = -0.15          # patron que va CONTRA la direccion de la senal
DOJI_PENAL = -0.20             # indecision: debilita cualquier direccion


def ajuste_confianza(candles: Dict[str, Sequence[float]], direccion: int) -> Dict[str, Any]:
    """
    Cuanto ajusta el FACTOR DE CONFIANZA del motor la vela actual, dada la
    `direccion` propuesta (CALL/PUT). Reglas del doc fuente:
      - Doji                       -> -0.20 e indecision (si la prob es floja, NO OPERAR).
      - Patron a FAVOR de la senal -> +0.10/+0.12/+0.15 (segun patron).
      - Patron en CONTRA           -> -0.15 (contradictorio).
      - Sin patron                 -> 0.0.
    Devuelve {factor, patron, indecision}.
    """
    det = detectar(candles)
    if det["indecision"]:
        return {"factor": DOJI_PENAL, "patron": "doji", "indecision": True}
    # Elige el patron de mayor magnitud presente (envolvente > marubozu > martillo).
    mejor = None; mejor_mag = -1.0
    for p in det["patrones"]:
        if p in _AJUSTE and _AJUSTE[p][1] > mejor_mag:
            mejor = p; mejor_mag = _AJUSTE[p][1]
    if mejor is None:
        return {"factor": 0.0, "patron": None, "indecision": False}
    pat_dir, mag = _AJUSTE[mejor]
    factor = mag if pat_dir == direccion else CONTRADICTORIO
    return {"factor": factor, "patron": mejor, "indecision": False}
