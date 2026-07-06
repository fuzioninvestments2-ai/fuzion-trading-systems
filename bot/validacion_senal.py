"""
bot/validacion_senal.py
=======================
PUERTA FINAL DE CALIDAD (reglas ESTRICTAS del trader, no negociables). Aunque la
fórmula diga OPERAR, esta función es el último filtro: si CUALQUIER regla falla,
devuelve NO OPERAR con el motivo EXACTO. El foco es NO PERDER: mejor no operar que
operar una señal mediocre (49% win-rate, en resistencia, indicador en ruido...).

Reglas (todas deben pasar):
  1. Timeframes completos: no operar si faltan tiempos por datos.
  2. Alineación de timeframes >= 80%.
  3. Win-rate histórico >= 60% (una vez hay historial suficiente).
  4. Umbral aprendido >= 25%.
  5. Fuerza de indicadores (RSI, Estocástico, MACD, Bandas) >= 60%; rechazo si
     alguno cae en 45-55% (zona de ruido).
  6. Precio NO pegado a soporte/resistencia (>= 15 pips de la zona).
  7. Confirmación por timeframe: cortos (1m-5m) y medios (10m-30m) >= 60%,
     largos (1h+) >= 70%.

SRP: solo valida. Sin red. Pura y testeable con asserts.
"""

# --- Umbrales ESTRICTOS (calibrables aquí; regla del trader) ---
ALINEACION_MIN = 80.0        # % mínimo de timeframes alineados con la dirección
WINRATE_MIN = 0.60           # win-rate histórico mínimo
UMBRAL_MIN = 0.25            # umbral aprendido mínimo
INDICADOR_MIN = 0.60         # fuerza mínima por indicador
RUIDO_LO, RUIDO_HI = 0.45, 0.55   # zona de RUIDO: cualquier indicador aquí -> rechazo
SR_PIPS_MIN = 15.0           # distancia mínima a soporte/resistencia (pips)
CONF_CORTO_MIN = 0.60        # confirmación mínima en 1m-5m
CONF_MEDIO_MIN = 0.60        # confirmación mínima en 10m-30m
CONF_LARGO_MIN = 0.70        # confirmación mínima en 1h+

# Fase de arranque: hasta tener este nº de señales RESUELTAS, la regla de win-rate
# no puede aplicarse (no hay con qué medir). Se avisa, no se inventa un 60%.
MIN_SENALES_WINRATE = 10


def _rechazo(motivo):
    return {"operar": False, "motivo": f"Rechazado: {motivo}"}


def _etq(tf):
    return ("1H" if tf >= 3600 else f"{tf}s" if tf < 60 else f"{tf // 60}m")


def _min_conf_tf(tf):
    """Confirmación mínima según el grupo de la temporalidad."""
    if tf >= 3600:
        return CONF_LARGO_MIN          # largos (1h+)
    if tf >= 600:
        return CONF_MEDIO_MIN          # medios (10m-30m)
    return CONF_CORTO_MIN              # cortos (1m-5m y sub-minuto)


def validate_signal(datos):
    """
    `datos` (dict) — todo lo necesario para decidir:
      direccion         : "CALL"|"PUT" (informativo)
      alineacion_pct    : float 0-100  (% de timeframes alineados)
      tiempos_presentes : int          (timeframes con datos)
      tiempos_config    : int          (timeframes que DEBE haber)
      win_rate_hist     : float 0-1 | None
      senales_medidas   : int          (nº de señales resueltas del activo)
      umbral_aprendido  : float 0-1 | None
      indicadores       : {nombre: fuerza 0-1}   (RSI, Estocástico, MACD, Bandas)
      cerca_sr          : bool
      dist_sr_pips      : float
      conf_por_tiempo   : {tf_segundos: fuerza 0-1}

    Devuelve {"operar": bool, "motivo": str}. Si algo falla -> operar=False con el
    motivo EXACTO (ej. "Rechazado: Alineación 67% < 80%").
    """
    # 1) TIMEFRAMES COMPLETOS.
    pres = int(datos.get("tiempos_presentes", 0))
    conf = int(datos.get("tiempos_config", 0))
    if conf and pres < conf:
        return _rechazo(f"faltan {conf - pres} tiempos por datos "
                        f"(deben estar los {conf})")

    # 2) ALINEACIÓN >= 80%.
    ali = float(datos.get("alineacion_pct", 0.0))
    if ali < ALINEACION_MIN:
        return _rechazo(f"Alineación {ali:.0f}% < {ALINEACION_MIN:.0f}%")

    # 3) WIN-RATE HISTÓRICO >= 60% (cuando ya hay historial suficiente).
    medidas = int(datos.get("senales_medidas", 0))
    wr = datos.get("win_rate_hist")
    if medidas >= MIN_SENALES_WINRATE:
        if wr is None or wr < WINRATE_MIN:
            return _rechazo(f"win-rate {((wr or 0) * 100):.0f}% "
                            f"< {WINRATE_MIN * 100:.0f}%")

    # 4) UMBRAL APRENDIDO >= 25%.
    um = datos.get("umbral_aprendido")
    if um is not None and um < UMBRAL_MIN:
        return _rechazo(f"umbral aprendido {um * 100:.0f}% "
                        f"< {UMBRAL_MIN * 100:.0f}%")

    # 5) FUERZA DE INDICADORES (RSI/Estocástico/MACD/Bandas) >= 60%; nada en ruido.
    for nombre, f in (datos.get("indicadores") or {}).items():
        if RUIDO_LO <= f <= RUIDO_HI:
            return _rechazo(f"{nombre} {f * 100:.0f}% en zona de ruido "
                            f"({int(RUIDO_LO*100)}-{int(RUIDO_HI*100)}%)")
        if f < INDICADOR_MIN:
            return _rechazo(f"{nombre} {f * 100:.0f}% < {INDICADOR_MIN * 100:.0f}%")

    # 6) PRECIO NO PEGADO A SOPORTE/RESISTENCIA.
    if datos.get("cerca_sr"):
        d = float(datos.get("dist_sr_pips", 0.0))
        return _rechazo(f"precio pegado a soporte/resistencia "
                        f"({d:.0f} pips < {SR_PIPS_MIN:.0f})")

    # 7) CONFIRMACIÓN POR TIMEFRAME.
    for tf, f in (datos.get("conf_por_tiempo") or {}).items():
        minimo = _min_conf_tf(int(tf))
        if f < minimo:
            return _rechazo(f"tiempo {_etq(int(tf))} confirmación "
                            f"{f * 100:.0f}% < {minimo * 100:.0f}%")

    return {"operar": True, "motivo": "Señal de ALTA CALIDAD: todas las reglas pasan."}
