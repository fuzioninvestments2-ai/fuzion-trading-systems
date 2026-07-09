"""
bot/skills/multi_timeframe.py
=============================
VIGILANCIA MULTI-TIMEFRAME para la alerta de Telegram. El sistema observa los 13
tiempos (5s→4h) y decide en los tiempos OPERABLES (1m,2m,3m,5m,10m, que es donde el
trader entra). El resto (ultra-cortos y largos) dan CONTEXTO y alineación.

Salida lista para la tarjeta de Telegram:
  - dirección y confianza del consenso (skills) en los tiempos operables,
  - panel de los 13 tiempos (flecha por tiempo),
  - alineación (cuántos de los 13 coinciden con la dirección).

Solo señal; el humano opera. No garantiza aciertos.
"""
import os

from bot.cuantico import calculate_timeframe_signal
from bot.skills.base_skill import CALL, PUT, NEUTRAL
from bot.skills.bot_real import crear_manager

# Los 13 tiempos que el sistema vigila (segundos).
TF_ALERTA = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600, 14400]
# Tiempos donde el trader OPERA (entra). El consenso de skills se calcula aquí.
TF_OPERABLES = [60, 120, 180, 300, 600]
ALINEACION_MIN = 0.60           # % de los 13 tiempos que deben coincidir para alertar


def _etq(seg):
    if seg < 60:
        return f"{seg}s"
    if seg < 3600:
        return f"{seg // 60}m"
    return f"{seg // 3600}h"


def analizar(frames, pair="EURUSD", manager=None):
    """
    `frames`: dict {tf_segundos: DataFrame OHLC}. `manager`: SkillManager entrenado
    (opcional; si no, uno fresco). Devuelve el resultado estructurado.
    """
    m = manager or crear_manager(weights_path=os.devnull)

    # 1) Dirección por tiempo en los 13 (para la alineación/panel).
    dir_por_tf = {}
    for tf in TF_ALERTA:
        df = frames.get(tf)
        if df is not None and len(df) >= 20:
            d, _f, _p = calculate_timeframe_signal(df)
            dir_por_tf[tf] = d                       # +1 / -1 / 0

    # 2) Consenso de skills en los tiempos OPERABLES.
    consensos = {}
    for tf in TF_OPERABLES:
        df = frames.get(tf)
        if df is not None and len(df) >= 30:
            consensos[tf] = m.get_consensus({"df": df, "pair": pair, "timeframe": tf})

    # 3) Dirección global = mayoría ponderada por confianza de los operables.
    peso_call = sum(c["confidence"] for c in consensos.values() if c["direction"] == CALL)
    peso_put = sum(c["confidence"] for c in consensos.values() if c["direction"] == PUT)
    if peso_call == peso_put == 0:
        direccion = NEUTRAL
    else:
        direccion = CALL if peso_call >= peso_put else PUT
    total = peso_call + peso_put
    confianza = (max(peso_call, peso_put) / total) if total else 0.0

    # 4) Alineación de los 13 tiempos con la dirección global.
    signo = 1 if direccion == CALL else (-1 if direccion == PUT else 0)
    presentes = len(dir_por_tf)
    alineados = sum(1 for d in dir_por_tf.values() if d == signo) if signo else 0
    alineacion_pct = (alineados / presentes * 100) if presentes else 0.0

    operar = (direccion != NEUTRAL and confianza >= 0.55 and
              presentes >= 9 and alineacion_pct >= ALINEACION_MIN * 100)

    return {
        "pair": pair, "direccion": direccion, "confianza": round(confianza, 3),
        "operar": operar, "alineados": alineados, "presentes": presentes,
        "alineacion_pct": round(alineacion_pct, 1),
        "dir_por_tf": dir_por_tf, "consensos": consensos,
        "operables": {tf: consensos[tf] for tf in TF_OPERABLES if tf in consensos},
    }


def formato_telegram(res):
    """Tarjeta de texto para Telegram."""
    flecha = {1: "▲", -1: "▼", 0: "·"}
    cab = f"📊 {res['pair']}  ·  Vigilancia 13 tiempos"
    if res["direccion"] == NEUTRAL or not res["operar"]:
        motivo = ("sin alineación suficiente" if res["direccion"] != NEUTRAL
                  else "sin consenso")
        cuerpo = [cab, "", "⏸️  SIN SEÑAL  (" + motivo + ")",
                  f"Alineación: {res['alineados']}/{res['presentes']} tiempos "
                  f"({res['alineacion_pct']:.0f}%)"]
    else:
        emoji = "🟢 CALL ▲" if res["direccion"] == CALL else "🔴 PUT ▼"
        cuerpo = [cab, "",
                  f"{emoji}   confianza {res['confianza']*100:.0f}%",
                  f"Alineación: {res['alineados']}/{res['presentes']} tiempos "
                  f"({res['alineacion_pct']:.0f}%)"]
    # Panel de tiempos.
    fila = []
    for tf in TF_ALERTA:
        if tf in res["dir_por_tf"]:
            fila.append(f"{_etq(tf)}{flecha[res['dir_por_tf'][tf]]}")
    cuerpo += ["", "Tiempos: " + "  ".join(fila)]
    # Tiempos operables (donde entras).
    ops = []
    for tf, c in res["operables"].items():
        d = c["direction"]
        ops.append(f"{_etq(tf)}:{d}({c['confidence']*100:.0f}%)")
    if ops:
        cuerpo += ["Operables (1m-10m): " + "  ".join(ops)]
    cuerpo += ["", "Señal educativa. Tú decides y operas. No garantiza aciertos."]
    return "\n".join(cuerpo)
