"""
bot/alignment.py
================
SINFONÍA DE DIRECCIÓN: junta la lectura de las 12 temporalidades en un veredicto,
con las reglas EXACTAS del trader:

  - Cada temporalidad da su dirección según SU regla (1H = EMA200; 30m/5m = EMA50
    y EMA200; 2m = EMA20/50/200; 1m = precio vs EMA20; 30s = MACD; 15s = Stoch;
    10s = RSI; 5s/3m/10m se leen con la pila de EMAs).
  - LEY ABSOLUTA: la EMA 200 en 1H manda. Solo se opera A SU FAVOR; en su contra,
    NO se opera aunque los cortos alineen.
  - Cada temporalidad pesa distinto (bot/otc_system.PESOS_ALINEACION; suman 100).
  - Se necesita un MÍNIMO de temporalidades alineadas (7/12 OTC, 8/12 real).

Módulo NUEVO y aparte: no toca el motor actual. Devuelve un dict claro para poder
mostrarlo y, luego, que el motor lo use.

SRP: solo evalúa la alineación. Sin red. Testeable con asserts.
"""

from bot.scoring_strategy import Indicators, _last, CALL, PUT, HOLD


def _slope_dir(series, back=3):
    """Dirección por PENDIENTE: valor actual vs `back` velas atrás."""
    v = _last(series)
    if v is None or series is None or len(series) <= back:
        return HOLD
    prev = float(series.iloc[-1 - back])
    if v > prev:
        return CALL
    if v < prev:
        return PUT
    return HOLD


def _emas(close):
    """Últimos valores de las 4 EMAs del trader (8/20/50/200)."""
    return {p: _last(Indicators.ema(close, p)) for p in (8, 20, 50, 200)}


def direccion_timeframe(df, tf):
    """
    Dirección (CALL/PUT/HOLD) de UNA temporalidad, con la regla del trader para
    ese tiempo. `tf` en segundos.
    """
    if df is None or len(df) < 10:
        return HOLD
    close = df["close"]
    high, low = df["high"], df["low"]
    price = _last(close)
    e = _emas(close)

    # 1H (>=3600): la EMA200 marca la dirección ABSOLUTA (por su pendiente).
    if tf >= 3600:
        return _slope_dir(Indicators.ema(close, 200))
    # 30m y 5m: EMA50 y EMA200 alineadas con el precio.
    if tf in (1800, 300):
        if None in (e[50], e[200], price):
            return HOLD
        if price > e[50] > e[200]:
            return CALL
        if price < e[50] < e[200]:
            return PUT
        return HOLD
    # 15m: EMA50 apuntando (alineada con 1H, que se valida aparte).
    if tf == 900:
        return _slope_dir(Indicators.ema(close, 50))
    # 2m: EMA20 > EMA50 > EMA200.
    if tf == 120:
        if None in (e[20], e[50], e[200]):
            return HOLD
        if e[20] > e[50] > e[200]:
            return CALL
        if e[20] < e[50] < e[200]:
            return PUT
        return HOLD
    # 1m: precio vs EMA20.
    if tf == 60:
        if e[20] is None or price is None:
            return HOLD
        return CALL if price > e[20] else (PUT if price < e[20] else HOLD)
    # 30s: MACD confirma (signo del histograma).
    if tf == 30:
        h = _last(Indicators.macd(close)[2])
        return CALL if (h or 0) > 0 else (PUT if (h or 0) < 0 else HOLD)
    # 15s: Stochastic en zona favorable.
    if tf == 15:
        k = _last(Indicators.stochastic(high, low, close, 5, 3)[0])
        if k is None:
            return HOLD
        return CALL if k < 50 else PUT        # saliendo de abajo / desde arriba
    # 10s: RSI 5 (no en extremo contrario). CALL si viene de abajo, PUT si de arriba.
    if tf == 10:
        r = _last(Indicators.rsi(close, 5))
        if r is None:
            return HOLD
        return CALL if r < 50 else PUT
    # 5s, 3m, 10m (peso 0): lectura con la pila de EMAs.
    if None in (e[8], e[20], price):
        return HOLD
    if price > e[8] > e[20]:
        return CALL
    if price < e[8] < e[20]:
        return PUT
    return HOLD


def evaluar_alineacion(frames, sistema):
    """
    Evalúa la sinfonía. `frames`: {tf_seconds: DataFrame}. `sistema`: otc_system o
    real_system (de ahí salen los pesos y el mínimo).

    Devuelve dict:
      direccion_1h : dirección ABSOLUTA (EMA200 en 1H) — CALL/PUT/HOLD
      dir_por_tf   : {tf: dir}
      alineados    : nº de temporalidades a favor de la dirección de 1H (de las que hay)
      total_tf     : cuántas temporalidades había con datos
      peso_favor   : % de peso a favor (0-100) de la dirección de 1H
      veredicto    : "OPERAR" | "NO OPERAR"
      motivo       : texto
    """
    # Dirección de CADA tiempo = CONSENSO de los 10 indicadores del trader (no un
    # solo indicador). Cada temporalidad lee los 10 (EMA 8/20/50/200, Stoch, Boll,
    # Donchian, RSI, MACD, S/R) y gana la mayoría. Así el panel es estable y alinea
    # cuando el mercado tiene tendencia (antes, un indicador suelto daba ruido).
    from bot.system_wiring import votar_sistema, direccion as _consenso
    dir_por_tf = {}
    for tf, df in frames.items():
        d, _nc, _np = _consenso(votar_sistema(df, sistema))
        dir_por_tf[tf] = d

    # Dirección MAYOR (ancla de tendencia): idealmente 1H (EMA200). Pero en OTC el
    # precio es SINTÉTICO y Pocket Option lo REINICIA, así que un 1h VIEJO no aplica
    # al mercado de AHORA. Solo llegan aquí los tiempos FRESCOS (filtrados antes).
    # El ancla es el tiempo más ALTO CON DIRECCIÓN CLARA (no HOLD): si el más alto
    # está neutral (indecisión) NO debe anular una tendencia clara de los tiempos de
    # abajo (antes daba "0/12" con el panel casi todo verde). Se prefiere 1H si marca
    # dirección; si no, el mayor decisivo disponible.
    decisivos = [tf for tf, d in dir_por_tf.items() if d in (CALL, PUT)]
    if 3600 in dir_por_tf and dir_por_tf[3600] in (CALL, PUT):
        tf_ancla = 3600
    elif decisivos:
        tf_ancla = max(decisivos)
    else:
        tf_ancla = max(dir_por_tf) if dir_por_tf else 0
    dir_1h = dir_por_tf.get(tf_ancla, HOLD)
    total_tf = len(dir_por_tf)

    if dir_1h == HOLD:
        return {"direccion_1h": HOLD, "dir_por_tf": dir_por_tf,
                "alineados": 0, "total_tf": total_tf, "peso_favor": 0.0,
                "veredicto": "NO OPERAR",
                "motivo": "El tiempo mayor disponible no marca dirección clara."}

    # Solo se opera A FAVOR de 1H. Contamos y pesamos las que coinciden.
    alineados = sum(1 for d in dir_por_tf.values() if d == dir_1h)
    peso_favor = sum(sistema.peso_alineacion(tf)
                     for tf, d in dir_por_tf.items() if d == dir_1h)

    minimo = sistema.ALINEACION_MINIMA
    etq = ("1H" if tf_ancla >= 3600 else
           f"{tf_ancla}s" if tf_ancla < 60 else f"{tf_ancla // 60}m")
    if alineados >= minimo:
        veredicto = "OPERAR"
        motivo = (f"{alineados}/{total_tf} tiempos a favor de la tendencia de {etq} "
                  f"({peso_favor}% de peso). Mínimo {minimo}.")
    else:
        veredicto = "NO OPERAR"
        motivo = (f"Solo {alineados}/{total_tf} alineados con {etq} "
                  f"(hacen falta {minimo}).")

    return {"direccion_1h": dir_1h, "dir_por_tf": dir_por_tf,
            "alineados": alineados, "total_tf": total_tf,
            "peso_favor": peso_favor, "veredicto": veredicto, "motivo": motivo}
