"""
bot/lectura_tiempo.py
=====================
LECTURA POR TEMPORALIDAD (el "baile" indicadores × tiempos, como lo pidió el
trader). Cada tiempo NO se lee igual: tiene SU indicador principal (la tabla del
trader / sinfonía) que marca la DIRECCIÓN, y los 10 indicadores actúan como
CONFIRMACIÓN (cuántos acompañan = fuerza de esa temporalidad).

Regla por tiempo (dirección principal, de la sinfonía del trader):
  1H  -> EMA200 (ley absoluta)          30s -> MACD (cruce/histograma)
  30m -> EMA50 y EMA200 + precio        15s -> Stochastic (zona favorable)
  15m -> EMA50 (pendiente)              10s -> RSI 5 (viene de un extremo)
  5m  -> EMA50 y EMA200 + precio        5s  -> pila EMA8/20 + precio
  2m  -> EMA20>50>200                   3m, 10m -> pila de EMAs
  1m  -> precio vs EMA20

La FUERZA (0-1) = fracción de los 10 indicadores del trader (EMA 8/20/50/200,
Stoch, Bollinger, Donchian, RSI, MACD, S/R) que votan la MISMA dirección que la
regla del tiempo. Así "los indicadores se alinean con los tiempos": el tiempo
manda la dirección, los indicadores dicen qué tan fuerte está.

SRP: solo lee una temporalidad. Sin red. Testeable con asserts.
"""

from bot.alignment import direccion_timeframe
from bot.system_wiring import votar_sistema
from bot.scoring_strategy import CALL, PUT, HOLD

# Nombre bonito de cada indicador para el detalle de la tarjeta.
_NOMBRE = {"ema8": "EMA8", "ema20": "EMA20", "ema50": "EMA50", "ema200": "EMA200",
           "stochastic": "Stoch", "bollinger": "Bollinger", "donchian": "Donchian",
           "rsi": "RSI", "macd": "MACD", "soporte_resistencia": "S/R"}


def leer_tiempo(df, tf, sistema):
    """
    Lee UNA temporalidad con su regla. Devuelve:
      {"dir": "CALL"|"PUT"|"HOLD", "fuerza": 0-1,
       "confirman": [claves de indicadores a favor],
       "en_contra": [claves en contra]}
    - dir: la DIRECCIÓN según la regla de ese tiempo (tabla del trader).
    - fuerza: fracción de los 10 indicadores que acompañan esa dirección.
    """
    d = direccion_timeframe(df, tf)
    votos = votar_sistema(df, sistema)
    total = len(votos) or 1
    if d in (CALL, PUT):
        confirman = [k for k, v in votos.items() if v == d]
        contra = [k for k, v in votos.items() if v in (CALL, PUT) and v != d]
        fuerza = len(confirman) / total
    else:
        # Sin dirección de tiempo: si los indicadores tienen mayoría CLARA, esa es
        # la dirección tentativa (débil); si no, HOLD.
        n_call = sum(1 for v in votos.values() if v == CALL)
        n_put = sum(1 for v in votos.values() if v == PUT)
        if n_call > n_put and n_call >= 6:
            d, confirman = CALL, [k for k, v in votos.items() if v == CALL]
        elif n_put > n_call and n_put >= 6:
            d, confirman = PUT, [k for k, v in votos.items() if v == PUT]
        else:
            return {"dir": HOLD, "fuerza": 0.0, "confirman": [], "en_contra": []}
        contra = [k for k, v in votos.items() if v in (CALL, PUT) and v != d]
        fuerza = len(confirman) / total
    return {"dir": d, "fuerza": fuerza, "confirman": confirman, "en_contra": contra}


def detalle_texto(lectura, maximo=4):
    """Texto corto de qué indicadores acompañan (para la tarjeta)."""
    nombres = [_NOMBRE.get(k, k) for k in lectura.get("confirman", [])[:maximo]]
    return ", ".join(nombres)
