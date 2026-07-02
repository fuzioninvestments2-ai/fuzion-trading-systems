"""
bot/vwap.py
===========
VWAP = Precio Medio Ponderado por Volumen (Volume-Weighted Average Price).

Es un NIVEL DE REFERENCIA que usan los profesionales: el precio "justo" del
periodo, ponderando cada vela por su volumen. La lectura clásica:
  - precio POR ENCIMA del VWAP -> los compradores mandan (sesgo alcista).
  - precio POR DEBAJO del VWAP -> los vendedores mandan (sesgo bajista).
  - precio MUY lejos del VWAP  -> extendido (en rango, suele volver al VWAP).

⚠️ HONESTIDAD sobre el volumen: en OTC de Pocket Option no hay volumen real; aquí
`volume` es el NÚMERO DE TICKS de cada vela (un sustituto). Por eso este VWAP es
"ponderado por actividad" (ticks), no por dinero real. Sigue siendo un anclaje
útil, pero se documenta para no engañar.

SRP: solo calcula el nivel y el sesgo. Sin red. Determinista y testeable.
Trabaja sobre un DataFrame con open/high/low/close y (opcional) volume.
"""

CALL = "CALL"
PUT = "PUT"
HOLD = "HOLD"


def vwap(df):
    """
    Devuelve el VWAP acumulado sobre TODA la ventana del DataFrame, o None si no
    hay datos. Usa el precio típico (high+low+close)/3 ponderado por volumen.
    Si no hay columna volume (o suma 0), cae a un promedio simple del típico
    (equivale a volumen uniforme) — así nunca divide por cero.
    """
    if df is None or len(df) == 0:
        return None
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    tipico = (high + low + close) / 3.0
    if "volume" in df.columns:
        vol = df["volume"].astype(float)
        total = float(vol.sum())
        if total > 0:
            return float((tipico * vol).sum() / total)
    # Sin volumen útil -> promedio simple (volumen uniforme).
    return float(tipico.mean())


def vwap_signal(df, banda=0.0015):
    """
    Sesgo respecto al VWAP.

    banda: fracción del propio VWAP que se considera "pegado" al nivel (zona
           neutral). Por defecto 0.15% — dentro de eso, HOLD (no hay sesgo claro).

    Devuelve dict: {vwap: float|None, side: CALL|PUT|HOLD, dist_pct: float}.
    - side CALL si el precio está claramente por encima del VWAP; PUT si debajo.
    - dist_pct: distancia del precio al VWAP en % (signo: + arriba, - abajo).
    """
    v = vwap(df)
    if v is None or v == 0:
        return {"vwap": None, "side": HOLD, "dist_pct": 0.0}
    price = float(df["close"].iloc[-1])
    dist = (price - v) / v                     # fracción (+ arriba / - abajo)
    if dist > banda:
        side = CALL
    elif dist < -banda:
        side = PUT
    else:
        side = HOLD
    return {"vwap": round(v, 6), "side": side, "dist_pct": round(dist * 100.0, 3)}
