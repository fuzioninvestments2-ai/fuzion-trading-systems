"""
bot/real_system.py
==================
SISTEMA MERCADO REAL del usuario. La MISMA base que el OTC (mismos 10 indicadores,
mismas 12 temporalidades, mismos pesos de alineación) pero con las diferencias que
el trader marcó para el forex real. Documentar = ejecutar.

Diferencias clave vs OTC (palabras del usuario):
  - NOTICIAS = factor #1: no operar 15 min antes, DURANTE, ni 30 min después.
  - Alineación MÁS ESTRICTA: mínimo 8 de 12 (OTC pedía 7).
  - SPREAD: no operar si supera ~2 pips (en real varía por sesión/noticia).
  - Sesiones: London Open y NY Open concentran ~80% del movimiento real.
  - Los niveles S/R y las divergencias son "más respetados" (mercado con bancos).

Reutiliza (NO duplica) las constantes idénticas del OTC; solo redefine lo que
cambia. Así los dos "motores" comparten la config común y difieren donde el
mercado lo exige.

⚠️ HONESTIDAD: los % de fiabilidad (85-95%) son la experiencia del trader, no una
garantía del bot. El bot mide su acierto real con signal_log. Además, el spread
en vivo puede no estar disponible desde las velas de PO: el umbral queda
documentado como regla y se aplica solo si la fuente entrega el spread.

SRP: solo define la config del sistema real. Sin red. Testeable con asserts.
"""

# Config IDÉNTICA al OTC -> se reutiliza (Regla 1: no duplicar datos iguales).
from bot.otc_system import (
    INDICADORES_OTC as INDICADORES_REAL,
    TIMEFRAMES_OTC as TIMEFRAMES_REAL,
    PESOS_ALINEACION,
    CICLO_MERCADO,
    PAYOUT_MINIMO, PAYOUT_BUENO,
    REGLA_DIRECCION_ABSOLUTA,
    clasificar_payout, indicador, peso_alineacion,
)

# Nombres CANÓNICOS (igual que en otc_system) para que los módulos funcionen
# con cualquiera de los dos sistemas sin fallar.
TIMEFRAMES = TIMEFRAMES_REAL
INDICADORES = INDICADORES_REAL

# --- DIFERENCIA 1: alineación más estricta (8 de 12, vs 7 en OTC) ---
ALINEACION_MINIMA = 8

# --- DIFERENCIA 2: noticias son el factor #1 (también DURANTE el evento) ---
NOTICIAS_ANTES_MIN = 15
NOTICIAS_DESPUES_MIN = 30
NOTICIAS_DURANTE = True            # en real NO se opera durante la noticia
CALENDARIOS = ("ForexFactory", "Investing.com")

# --- DIFERENCIA 3: filtro de SPREAD (pips) ---
# En real el spread varía por sesión y se dispara en noticias (5-10 pips).
SPREAD_MAX_PIPS = 2.0

# --- Sesiones (horas EST). ~80% del movimiento real en London/NY open ---
SESIONES_BUENAS = [("London Open", 2.0, 5.0), ("NY Open", 9.5, 11.0)]
SESIONES_EVITAR = [("Asia", 20.0, 24.0), ("NY PM", 13.0, 16.0)]

# Nota de fiabilidad (lectura del trader, NO garantía): en real las señales se
# consideran más fiables que en OTC porque el mercado tiene bancos detrás.
NOTA_FIABILIDAD = ("Lectura del trader: en real las divergencias RSI y los "
                   "niveles S/R se respetan más que en OTC. No es garantía; "
                   "el acierto real lo mide el registro de señales.")


def spread_ok(pips):
    """
    True si el spread es operable (<= 2 pips). Si no hay dato de spread (None),
    devuelve True (no bloquea por falta de dato; el bot suele leer velas OHLC sin
    spread). Se aplica de verdad cuando la fuente sí entrega el spread.
    """
    if pips is None:
        return True
    return float(pips) <= SPREAD_MAX_PIPS
