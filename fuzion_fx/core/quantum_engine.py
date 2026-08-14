"""
core/quantum_engine.py (fuzion_fx)
==================================
MOTOR CUANTICO: Probabilidad + Convergencia (estrategia de Alex, doc fuente).

Dos niveles:
  1) analizar_tf(velas): para UN timeframe combina los 8 indicadores (ponderados
     por el modo del ADX), el momentum (multiplicador) y el patron de vela en una
     PROBABILIDAD y una direccion de ESE tiempo.
  2) analizar(velas_por_tf): junta los 7 timeframes con su peso de influencia,
     mide la ALINEACION y la PROBABILIDAD total, y emite el VEREDICTO:
        prob >= 90% y alineacion >= 0.75 y >=3 tiempos (con uno de peso alto) -> OPERAR
        prob 75-89% -> OPCIONAL   ·   60-74% -> MONITOREAR   ·   <60% -> NO OPERAR
     Un timeframe MAYOR (15m/30m) que contradice fuerte, o un doji con prob floja,
     fuerzan NO OPERAR.

PORQUE se pondera y no se cuenta a secas: un voto al borde no vale como uno
rotundo, y el 30m no vale como el 1m. La convergencia (que coincidan indicadores,
tiempos y fuerza) es lo que separa una señal clara de ruido. HONESTIDAD: esto es
DISCIPLINA, no una bola de cristal; el acierto real lo mide el registro. Sin red.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from core import indicator_set, adx_arbiter, candle_patterns
from core.indicator_set import CALL, PUT, NEUTRAL

# Peso de INFLUENCIA por timeframe (segundos). Suma 1.0. Del doc fuente: el medio
# (3m-10m) manda, el largo (15m-30m) confirma, el corto (1m-2m) casi no pesa.
PESO_TF = {60: 0.02, 120: 0.03, 180: 0.10, 300: 0.20,
           600: 0.20, 900: 0.25, 1800: 0.20}
# Timeframes de peso alto: al menos uno debe estar de acuerdo para OPERAR.
TF_ALTO = {300, 600, 900, 1800}
# Timeframes mayores: si uno contradice FUERTE, no se opera.
TF_MAYOR = {900, 1800}

# Umbrales de decision (doc fuente).
UMBRAL_OPERAR = 0.90
UMBRAL_OPCIONAL = 0.75
UMBRAL_MONITOREAR = 0.60
ALINEACION_OPERAR = 0.75
ALINEACION_OPCIONAL = 0.60


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


# ------------------------------------------------------------- nivel 1: por tf
def analizar_tf(candles: Dict[str, Sequence[float]]) -> Optional[Dict[str, Any]]:
    """
    Probabilidad y direccion de UN timeframe. Devuelve None si no hay datos o
    ningun indicador vota con fuerza.
    """
    votos = indicator_set.votar(candles)
    if not votos:
        return None
    pesos = adx_arbiter.arbitrar(candles)
    modo = pesos["modo"]; peso_ind = pesos["pesos"]; adx_val = pesos["adx"]

    # Momentum es MULTIPLICADOR (no vota): se separa de los votantes.
    mom = votos.get("momentum", {"dir": NEUTRAL, "fuerza": 0.0})

    favor_call = favor_put = peso_total = 0.0
    suma_fuerza = 0.0; n_vot = 0
    for nombre, voto in votos.items():
        if nombre == "momentum":
            continue
        contrib = voto["fuerza"] * peso_ind.get(nombre, 1.0)   # fuerza * peso del modo
        peso_total += contrib
        if voto["dir"] == CALL:
            favor_call += contrib
        elif voto["dir"] == PUT:
            favor_put += contrib
        if voto["fuerza"] > 0:
            suma_fuerza += voto["fuerza"]; n_vot += 1
    if peso_total <= 0:
        return None

    direccion = CALL if favor_call >= favor_put else PUT
    favor = favor_call if direccion == CALL else favor_put
    prob_base = favor / peso_total                              # fraccion ponderada a favor

    # Momentum: si acompana la direccion, sube la fuerza; si va en contra, la baja.
    if mom["dir"] == direccion:
        mmult = 1.0 + 0.15 * mom["fuerza"]
    elif mom["dir"] == NEUTRAL:
        mmult = 1.0
    else:
        mmult = 1.0 - 0.15 * mom["fuerza"]

    # Patron de vela: ajusta el factor de confianza (+/- segun el doc).
    pat = candle_patterns.ajuste_confianza(candles, direccion)
    factor = mmult * (1.0 + pat["factor"])
    prob_tf = _clip01(prob_base * factor)
    fuerza_tf = (suma_fuerza / n_vot) if n_vot else 0.0

    return {"dir": direccion, "prob": prob_tf, "prob_base": prob_base,
            "fuerza": fuerza_tf, "adx": adx_val, "modo": modo,
            "patron": pat["patron"], "indecision": pat["indecision"]}


# ------------------------------------------------- nivel 2: multi-temporalidad
def analizar(velas_por_tf: Dict[int, Dict[str, Sequence[float]]]) -> Dict[str, Any]:
    """
    Junta los timeframes disponibles y emite el veredicto. `velas_por_tf` mapea
    segundos->velas (ej. {60: ..., 300: ..., 900: ...}). Solo pesan los que tengan
    datos. Devuelve un dict con veredicto, direccion, probabilidad, alineacion,
    cuantos tiempos se alinean y el detalle por tiempo.
    """
    por_tf: Dict[int, Dict[str, Any]] = {}
    for tf, candles in velas_por_tf.items():
        r = analizar_tf(candles)
        if r is not None:
            por_tf[int(tf)] = r

    if not por_tf:
        return {"veredicto": "NO_OPERAR", "motivo": "sin datos",
                "direccion": NEUTRAL, "probabilidad": 0.0, "alineacion": 0.0,
                "n_alineados": 0, "por_tf": {}}

    # Net firmado (hacia CALL +, hacia PUT -), ponderado por influencia y prob.
    num = den = alin_num = 0.0
    for tf, r in por_tf.items():
        w = PESO_TF.get(tf, 0.05)
        num += w * r["dir"] * r["prob"]
        alin_num += w * r["dir"] * r["fuerza"]
        den += w
    net = num / den if den else 0.0
    alineacion_firmada = alin_num / den if den else 0.0

    direccion = CALL if net >= 0 else PUT
    probabilidad = 0.5 + 0.5 * abs(net)                # 50%..100% hacia la direccion
    alineacion = abs(alineacion_firmada)

    alineados = [tf for tf, r in por_tf.items() if r["dir"] == direccion]
    n_alineados = len(alineados)
    hay_alto = any(tf in TF_ALTO for tf in alineados)

    # Contradiccion de un timeframe MAYOR (15m/30m) en contra y con conviccion.
    contra_mayor = any(tf in TF_MAYOR and r["dir"] != direccion and r["prob"] >= 0.70
                       for tf, r in por_tf.items())
    # Doji con probabilidad floja -> el doc manda NO OPERAR.
    doji_debil = (any(r["indecision"] for r in por_tf.values())
                  and probabilidad < UMBRAL_OPCIONAL)

    if contra_mayor:
        veredicto, motivo = "NO_OPERAR", "un timeframe mayor contradice fuerte"
    elif doji_debil:
        veredicto, motivo = "NO_OPERAR", "doji (indecision) con probabilidad floja"
    elif (probabilidad >= UMBRAL_OPERAR and alineacion >= ALINEACION_OPERAR
          and n_alineados >= 3 and hay_alto):
        veredicto, motivo = "OPERAR", "alta convergencia"
    elif probabilidad >= UMBRAL_OPCIONAL and alineacion >= ALINEACION_OPCIONAL:
        veredicto, motivo = "OPCIONAL", "convergencia moderada"
    elif probabilidad >= UMBRAL_MONITOREAR:
        veredicto, motivo = "MONITOREAR", "sesgo pero sin fuerza"
    else:
        veredicto, motivo = "NO_OPERAR", "sin claridad"

    return {"veredicto": veredicto, "motivo": motivo, "direccion": direccion,
            "probabilidad": round(probabilidad, 4), "alineacion": round(alineacion, 4),
            "n_alineados": n_alineados, "por_tf": por_tf}
