"""
bot/candle_patterns.py
======================
Detecta PATRONES DE VELA (velas japonesas) sobre las últimas velas OHLC.

El usuario pidió más lecturas y, sobre todo, detectar la INDECISIÓN. Los patrones
de vela son justo eso: la FORMA de la vela cuenta una historia que los
indicadores (que promedian precios) no ven.

Patrones incluidos y su porqué:
  - DOJI              -> cuerpo minúsculo: compradores y vendedores empatados =
                         INDECISIÓN (mejor no entrar).
  - MARTILLO (hammer) -> mecha inferior larga: rechazo de precios bajos = presión
                         alcista (posible CALL).
  - ESTRELLA FUGAZ    -> mecha superior larga: rechazo de precios altos = presión
                         bajista (posible PUT).
  - ENVOLVENTE alcista/bajista (engulfing) -> la vela envuelve a la anterior:
                         cambio de fuerza (reversión).
  - MARUBOZU          -> casi sin mechas: momento fuerte en una dirección.

SRP: solo lee la forma de las velas. Sin red. Determinista y testeable.
Trabaja sobre un DataFrame con columnas open/high/low/close.
"""

CALL = "CALL"
PUT = "PUT"


def _partes(o, h, l, c):
    """Descompone una vela en cuerpo, mechas y rango total (todos >= 0)."""
    rango = max(h - l, 1e-12)              # evita división por cero en velas planas
    cuerpo = abs(c - o)
    mecha_sup = h - max(o, c)
    mecha_inf = min(o, c) - l
    return rango, cuerpo, mecha_sup, mecha_inf


def detect_patterns(df, doji_ratio=0.1, mecha_ratio=2.0, marubozu_ratio=0.9):
    """
    Analiza la ÚLTIMA vela (y la previa para envolventes) del DataFrame.

    doji_ratio    : cuerpo/rango por debajo de esto = doji (indecisión).
    mecha_ratio   : cuánto mayor debe ser una mecha frente al cuerpo para
                    contar como martillo/estrella (rechazo).
    marubozu_ratio: cuerpo/rango por encima de esto = marubozu (momento fuerte).

    Devuelve dict: {patrones: [str], bias: CALL|PUT|None, indecision: bool}.
    - `bias` resume la dirección sugerida por los patrones (None si neutral).
    - `indecision` es True si domina un doji (señal de NO entrar).
    """
    res = {"patrones": [], "bias": None, "indecision": False}
    if df is None or len(df) < 1:
        return res

    o = float(df["open"].iloc[-1])
    h = float(df["high"].iloc[-1])
    l = float(df["low"].iloc[-1])
    c = float(df["close"].iloc[-1])
    rango, cuerpo, m_sup, m_inf = _partes(o, h, l, c)

    votos_call = votos_put = 0

    # Orden importa: un martillo también tiene cuerpo pequeño, así que primero
    # miramos la ASIMETRÍA de mechas (¿domina una?); el doji queda como el caso
    # de cuerpo pequeño SIN mecha dominante (fuerzas equilibradas = indecisión).
    # Usamos max(cuerpo, eps) para que la regla no se rompa si el cuerpo es ~0,
    # y exigimos que la mecha dominante sea >2x la otra (asimetría clara).
    eps = 1e-9
    hammer = (m_inf >= mecha_ratio * max(cuerpo, eps) and m_inf > 2.0 * m_sup)
    star = (m_sup >= mecha_ratio * max(cuerpo, eps) and m_sup > 2.0 * m_inf)

    if hammer:
        # MARTILLO: mecha inferior larga -> rechazo de mínimos (alza).
        res["patrones"].append("Martillo (rechazo de mínimos → alza)")
        votos_call += 1
    elif star:
        # ESTRELLA FUGAZ: mecha superior larga -> rechazo de máximos (baja).
        res["patrones"].append("Estrella fugaz (rechazo de máximos → baja)")
        votos_put += 1
    elif cuerpo <= doji_ratio * rango:
        # DOJI: cuerpo diminuto y mechas equilibradas -> indecisión.
        res["patrones"].append("Doji (indecisión)")
        res["indecision"] = True

    # MARUBOZU: cuerpo que casi ocupa todo el rango -> momento fuerte.
    if cuerpo >= marubozu_ratio * rango:
        if c > o:
            res["patrones"].append("Marubozu alcista (momento fuerte)")
            votos_call += 1
        else:
            res["patrones"].append("Marubozu bajista (momento fuerte)")
            votos_put += 1

    # ENVOLVENTE (engulfing): la vela actual envuelve el cuerpo de la anterior.
    if len(df) >= 2:
        o0 = float(df["open"].iloc[-2])
        c0 = float(df["close"].iloc[-2])
        cuerpo0 = abs(c0 - o0)
        # Alcista: vela previa bajista y la actual alcista que la envuelve.
        if (c0 < o0 and c > o and c >= o0 and o <= c0 and cuerpo > cuerpo0):
            res["patrones"].append("Envolvente alcista (reversión ↑)")
            votos_call += 1
        elif (c0 > o0 and c < o and c <= o0 and o >= c0 and cuerpo > cuerpo0):
            res["patrones"].append("Envolvente bajista (reversión ↓)")
            votos_put += 1

    # Sesgo resumido: la indecisión (doji) manda; si no, mayoría de votos.
    if res["indecision"]:
        res["bias"] = None
    elif votos_call > votos_put:
        res["bias"] = CALL
    elif votos_put > votos_call:
        res["bias"] = PUT
    return res
