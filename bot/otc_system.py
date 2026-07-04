"""
bot/otc_system.py
=================
SISTEMA OTC del usuario (trader con 5+ años), tal cual lo especificó. Este módulo
NO calcula nada: es la CONFIGURACIÓN documentada = lo que el motor ejecuta. Aquí
vive el "secreto" en forma de parámetros, para poder auditarlo y ajustarlo.

Idea del sistema (palabras del usuario):
  Ciclo del mercado: COMPRESIÓN -> ACUMULACIÓN -> SATURACIÓN -> REVERSIÓN.
  Se leen 12 temporalidades a la vez (la "sinfonía de dirección"); la ventaja
  está en ENTRAR cuando muchas coinciden. La EMA 200 en 1H manda la dirección
  absoluta: no se opera en su contra.

⚠️ HONESTIDAD: el 90-95% es la experiencia MANUAL del usuario. Este módulo
reproduce su sistema; el acierto real del bot lo mide signal_log, no se promete.

SRP: solo define parámetros. Sin red. Testeable con asserts.
"""

# --- Los 10 indicadores del sistema (misma config en todas las temporalidades) ---
# EL PORQUÉ de cada uno lo da la lectura del trader (compresión/acumulación/
# saturación/reversión + dirección por medias).
INDICADORES_OTC = [
    {"clave": "ema8",   "nombre": "EMA 8",   "tipo": "ema",    "periodo": 8,
     "rol": "dirección inmediata"},
    {"clave": "ema20",  "nombre": "EMA 20",  "tipo": "ema",    "periodo": 20,
     "rol": "tendencia corta / soporte dinámico"},
    {"clave": "ema50",  "nombre": "EMA 50",  "tipo": "ema",    "periodo": 50,
     "rol": "tendencia media / soporte-resistencia"},
    {"clave": "ema200", "nombre": "EMA 200", "tipo": "ema",    "periodo": 200,
     "rol": "dirección macro (en 1H = dirección ABSOLUTA)"},
    {"clave": "stochastic", "nombre": "Stochastic", "tipo": "stochastic",
     "k": 5, "d": 3, "suavizado": 3, "rol": "cruces en extremos (entrada)"},
    {"clave": "bollinger", "nombre": "Bollinger Bands", "tipo": "bollinger",
     "periodo": 14, "desv": 1.02, "rol": "compresión / saturación (bandas)"},
    {"clave": "donchian", "nombre": "Donchian Channel", "tipo": "donchian",
     "periodo": 20, "rol": "rango / ruptura (acumulación)"},
    {"clave": "rsi", "nombre": "RSI", "tipo": "rsi", "periodo": 5,
     "rol": "sobrecompra/sobreventa rápida"},
    {"clave": "macd", "nombre": "MACD", "tipo": "macd",
     "fast": 12, "slow": 26, "signal": 9, "rol": "momentum / cruces"},
    {"clave": "soporte_resistencia", "nombre": "Soportes/Resistencias",
     "tipo": "niveles", "lookback": 20,
     "rol": "últimos 20 máximos/mínimos = niveles clave"},
]

# --- Las 12 temporalidades que se leen a la vez (segundos) ---
TIMEFRAMES_OTC = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600]

# --- SINFONÍA DE DIRECCIÓN: peso de cada temporalidad en la alineación (%) ---
# Los tiempos altos mandan (1H define, 30m/15m confirman); los cortos afinan la
# entrada. Suman 100. Las temporalidades no listadas se LEEN pero pesan 0 en la
# alineación (5s, 3m, 10m son lectura fina, no deciden la dirección mayor).
PESOS_ALINEACION = {
    3600: 30,   # 1H  - dirección absoluta (EMA 200)
    1800: 20,   # 30m - EMA 50 y 200 alineadas
    900: 15,    # 15m - EMA 50 alineada con 1H
    300: 10,    # 5m  - EMA 50 y 200 alineadas
    120: 10,    # 2m  - EMA 20/50/200 alineadas
    60: 5,      # 1m  - precio vs EMA 20
    30: 5,      # 30s - MACD confirma
    15: 3,      # 15s - Stochastic en zona favorable
    10: 2,      # 10s - RSI 5 no en extremo contrario
}

# Regla de oro: mínimo de temporalidades alineadas para entrar (de 12).
ALINEACION_MINIMA = 7

# Ciclo del mercado (la "fórmula" del usuario), en orden.
CICLO_MERCADO = ["compresión", "acumulación", "saturación", "reversión"]

# --- FILTRO DE PAGO (payout, %) ---
# 75% mínimo. 75-85% bueno. 85-92% peligroso (el broker gana más). <75% NO operar.
PAYOUT_MINIMO = 75
PAYOUT_BUENO = (75, 85)
PAYOUT_PELIGROSO = (85, 92)


def clasificar_payout(payout):
    """
    Devuelve 'no_operar' | 'bueno' | 'peligroso' según el %.
    <75 no se opera; 75-85 es la zona buena; >85 es peligrosa (inestable).
    """
    if payout is None or payout < PAYOUT_MINIMO:
        return "no_operar"
    if payout <= PAYOUT_BUENO[1]:            # 75-85
        return "bueno"
    return "peligroso"                        # 85 en adelante


# --- FILTRO DE NOTICIAS (minutos) ---
NOTICIAS_ANTES_MIN = 15      # no operar 15 min ANTES
NOTICIAS_DESPUES_MIN = 30    # ni 30 min DESPUÉS (esperar a que se calme)

# --- SESIONES (horas EST) ---
# Mejores ventanas y ventanas a evitar (según el usuario). Se guardan como
# (nombre, hora_inicio, hora_fin) en horario EST; el filtro real convierte luego.
SESIONES_BUENAS = [("London Open", 2.0, 5.0), ("NY Open", 9.5, 11.0)]
SESIONES_EVITAR = [("Asia", 20.0, 24.0), ("NY PM", 13.0, 16.0)]

# Regla dura de tendencia mayor.
REGLA_DIRECCION_ABSOLUTA = ("EMA 200 en 1H define la dirección absoluta: si "
                            "apunta arriba, solo CALL; si abajo, solo PUT.")


def indicador(clave):
    """Devuelve la config de un indicador por su clave, o None."""
    for ind in INDICADORES_OTC:
        if ind["clave"] == clave:
            return ind
    return None


def peso_alineacion(tf_seconds):
    """Peso (%) de una temporalidad en la sinfonía de dirección (0 si no pesa)."""
    return PESOS_ALINEACION.get(int(tf_seconds), 0)
