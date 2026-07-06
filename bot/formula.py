"""
bot/formula.py
==============
LA FÓRMULA DE LA DANZA (motor de decisión del trader).

No cuenta "flechas iguales" (7/12). Calcula un SCORE continuo combinando TODOS los
tiempos, cada uno con su dirección (regla del tiempo) y su FUERZA (indicadores que
confirman), pesados. Así una tendencia CORTA pero FUERTE también manda y sigue —
"todo es una danza". Sobre ese score se añade la ZONA (soporte/resistencia del
tiempo operado) y se exige un GATILLO en los tiempos cortos (5s-1m: donde el
trader entra). El resultado: dirección + fuerza + veredicto, calculados por fórmula.

    score = Σ_t  dir_t · fuerza_t · peso(t)  /  Σ_t peso(t)      (rango -1..+1)
    score += zona(T)                                            (nudge S/R, acotado)
    OPERAR  si  |score| ≥ UMBRAL  y  un tiempo corto confirma la dirección.

dir_t ∈ {+1 CALL, −1 PUT, 0}. fuerza_t ∈ [0,1]. peso(t) = ponderación del trader
con un PISO para que los cortos (donde entra) cuenten.

SRP: solo calcula la entrada. Sin red. Testeable con asserts.
"""

import math

from bot.lectura_tiempo import leer_tiempo
from bot.scoring_strategy import CALL, PUT, HOLD

# Tiempos CORTOS donde el trader hace la ENTRADA (5s..1m). Uno de ellos debe
# confirmar la dirección para dar el gatillo (entrar en el punto correcto).
TIEMPOS_ENTRADA = (5, 10, 15, 30, 60)

# PISO de peso: todo tiempo presente aporta algo (el trader ENTRA en los cortos,
# así que no pueden pesar 0). Los altos siguen dominando el sesgo, pero un tiempo
# corto FUERTE suma de verdad.
PISO_PESO = 4

UMBRAL_DANZA = 0.35          # |score| mínimo para considerar dirección operable
UMBRAL_GATILLO = 0.25        # confirmación mínima de los tiempos cortos
UMBRAL_PARTICIPACION = 0.12  # fracción mínima del peso que debe estar EN MOVIMIENTO
ZONA_MAX = 0.10              # nudge máximo por soporte/resistencia

# Mezcla dirección(regla, EMAs) vs MOMENTUM (movimiento real reciente). El momentum
# lidera para captar el movimiento de AHORA (las EMAs van con retraso y en un giro
# brusco marcan la dirección vieja). Suman ~1.
PESO_DIRECCION = 0.5
PESO_MOMENTUM = 0.5
MOM_VELAS = 5                # velas recientes para medir el momentum


def _momentum(df, k=MOM_VELAS):
    """
    Movimiento REAL reciente, normalizado por la volatilidad típica: cuántos
    'movimientos normales' recorrió el precio en las últimas k velas, con signo.
    +1 = subida fuerte y limpia; −1 = bajada fuerte; ~0 = lateral/choppy. Capta el
    giro de AHORA que las EMAs (con retraso) no ven.
    """
    if df is None or len(df) < k + 2:
        return 0.0
    close = df["close"]
    tipico = float(close.diff().abs().tail(20).mean())
    if tipico <= 0:
        return 0.0
    mov = float(close.iloc[-1]) - float(close.iloc[-1 - k])
    m = mov / (k * tipico)
    return max(-1.0, min(1.0, m))


# Cuánto se estrecha el foco alrededor del tiempo operado (en escala log-tiempo).
# Menor = más foco en el tiempo que se opera y sus vecinos.
SIGMA_PROX = 1.6
PROX_PISO = 0.30             # los tiempos lejanos (contexto) conservan este mínimo


def _peso_eff(sistema, tf, tf_operar):
    """
    Peso de un tiempo en la fórmula = su peso base (ponderación del trader + piso)
    modulado por la PROXIMIDAD al tiempo que se OPERA. La entrada se decide en el
    tiempo operado y sus vecinos (ahí está el punto); los tiempos muy lejanos son
    contexto (conservan PROX_PISO). Así una subida clara en M1 no la diluye un 15m
    en rango. Proximidad = gaussiana en log-tiempo.
    """
    base = sistema.peso_alineacion(tf) + PISO_PESO
    r = math.log(max(tf, 1)) - math.log(max(tf_operar, 1))
    prox = PROX_PISO + (1 - PROX_PISO) * math.exp(-(r * r) / (2 * SIGMA_PROX ** 2))
    return base * prox


def _signo(d):
    return 1 if d == CALL else (-1 if d == PUT else 0)


def _zona(df, periodo=20):
    """
    Posición del precio en el canal (0 = piso/soporte, 1 = techo/resistencia).
    Devuelve un nudge: cerca del soporte favorece CALL (+), cerca de la resistencia
    favorece PUT (−). Acotado (la tendencia manda; esto solo afina el punto).
    """
    if df is None or len(df) < periodo:
        return 0.0
    hh = float(df["high"].rolling(periodo).max().iloc[-1])
    ll = float(df["low"].rolling(periodo).min().iloc[-1])
    p = float(df["close"].iloc[-1])
    if hh <= ll:
        return 0.0
    pos = (p - ll) / (hh - ll)                 # 0..1
    # Rebote: cerca del piso (+CALL), cerca del techo (−PUT). Lineal y acotado.
    return max(-ZONA_MAX, min(ZONA_MAX, (0.5 - pos) * 2 * ZONA_MAX))


def calcular_danza(frames, sistema, tf_operar):
    """
    Calcula la entrada para `tf_operar` con la fórmula de la danza. Devuelve un dict
    compatible con la tarjeta:
      direccion_1h, veredicto('OPERAR'/'NO OPERAR'), peso_favor(0-100),
      alineados, total_tf, dir_por_tf, fuerza_por_tf, motivo, score, gatillo.
    """
    dir_por_tf, fuerza_por_tf = {}, {}
    num = den_part = den_all = 0.0
    mom_num = 0.0
    for tf, df in frames.items():
        lec = leer_tiempo(df, tf, sistema)
        dir_por_tf[tf] = lec["dir"]
        fuerza_por_tf[tf] = lec["fuerza"]
        w = _peso_eff(sistema, tf, tf_operar)
        num += _signo(lec["dir"]) * lec["fuerza"] * w
        den_part += lec["fuerza"] * w          # peso EN MOVIMIENTO (participación)
        den_all += w
        mom_num += _momentum(df) * w           # movimiento real reciente, pesado
    total_tf = len(frames)
    # PARTICIPACIÓN: cuánto del peso posible está de verdad moviéndose. Si casi nada
    # se mueve (mercado plano/indeciso) no hay danza -> no se opera.
    participacion = (den_part / den_all) if den_all else 0.0
    if den_part == 0 or participacion < UMBRAL_PARTICIPACION or total_tf == 0:
        return {"direccion_1h": HOLD, "veredicto": "NO OPERAR", "peso_favor": 0.0,
                "alineados": 0, "total_tf": total_tf, "dir_por_tf": dir_por_tf,
                "fuerza_por_tf": fuerza_por_tf, "score": 0.0, "gatillo": False,
                "motivo": "El mercado no se mueve lo suficiente ahora: espera."}

    # Score = MEZCLA de dos criterios:
    #  (a) DIRECCIÓN (regla de cada tiempo, EMAs): el sesgo estructural.
    #  (b) MOMENTUM (movimiento real reciente): capta el giro de AHORA que las EMAs,
    #      con retraso, no ven (por eso el bot marcaba UP en una caída clara).
    # La dirección se normaliza por participación (los que se mueven) -> una tendencia
    # corta pero fuerte manda. El momentum por todo el peso (0 en los laterales).
    score_dir = num / den_part
    score_mom = mom_num / den_all if den_all else 0.0
    score = PESO_DIRECCION * score_dir + PESO_MOMENTUM * score_mom
    # ZONA S/R del tiempo operado, PERO solo pesa en RANGO: en tendencia fuerte
    # (momentum alto) estar pegado al borde es CONTINUACIÓN, no rechazo — así que la
    # zona se apaga cuando el movimiento manda. Evita penalizar comprar/vender a
    # favor de una tendencia clara.
    score += _zona(frames.get(tf_operar)) * (1 - min(1.0, abs(score_mom)))
    score = max(-1.0, min(1.0, score))

    direccion = CALL if score > 0 else (PUT if score < 0 else HOLD)
    fuerza = abs(score)

    # GATILLO: al menos un tiempo CORTO (5s-1m) confirma la dirección con fuerza.
    trig_num = trig_den = 0.0
    for tf in TIEMPOS_ENTRADA:
        if tf in frames:
            w = _peso_eff(sistema, tf, tf_operar)
            trig_den += w
            if dir_por_tf.get(tf) == direccion and direccion in (CALL, PUT):
                trig_num += fuerza_por_tf.get(tf, 0.0) * w
    gatillo = trig_den > 0 and (trig_num / trig_den) >= UMBRAL_GATILLO

    alineados = sum(1 for d in dir_por_tf.values() if d == direccion
                    and direccion in (CALL, PUT))
    peso_favor = round(fuerza * 100)

    etq = ("1H" if tf_operar >= 3600 else
           f"{tf_operar}s" if tf_operar < 60 else f"{tf_operar // 60}m")
    lado = "CALL" if direccion == CALL else "PUT"
    if direccion == HOLD or fuerza < UMBRAL_DANZA:
        veredicto, motivo = "NO OPERAR", (
            f"Fuerza insuficiente ({peso_favor}%): los tiempos y el movimiento no "
            f"marcan una dirección clara todavía.")
    elif not gatillo:
        veredicto, motivo = "NO OPERAR", (
            f"Dirección {lado} con fuerza {peso_favor}%, pero falta confirmación en "
            f"el tiempo corto (5s-1m): espera el punto de entrada.")
    else:
        veredicto, motivo = "OPERAR", (
            f"{lado} con {peso_favor}% de fuerza (tiempos + movimiento) y "
            f"confirmación en corto. Entrada en {etq}.")

    return {"direccion_1h": direccion, "veredicto": veredicto,
            "peso_favor": peso_favor, "alineados": alineados, "total_tf": total_tf,
            "dir_por_tf": dir_por_tf, "fuerza_por_tf": fuerza_por_tf,
            "score": round(score, 3), "gatillo": gatillo, "motivo": motivo}
