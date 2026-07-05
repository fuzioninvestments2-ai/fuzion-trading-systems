"""
bot/system_wiring.py
====================
CABLEADO del sistema del usuario al cálculo real: computa el voto de cada uno de
sus 10 indicadores con SUS parámetros exactos (EMA 8/20/50/200, Stochastic 5,3,3,
Bollinger 14/1.02, Donchian 20, RSI 5, MACD 12,26,9, Soportes/Resistencias).

Documentar = ejecutar: lee la config de bot/otc_system (o real_system) y produce
los votos tal como el trader los describió. Es un módulo NUEVO y aparte: NO toca
el motor existente (scoring_strategy), así nada se rompe; luego el motor puede
usar estos votos.

Cada voto es "CALL" | "PUT" | "HOLD". Reutiliza los indicadores de core (Regla 1).

SRP: solo vota con los parámetros del sistema. Sin red. Testeable con asserts.
"""

from bot.scoring_strategy import Indicators, _last, CALL, PUT, HOLD
from bot import otc_system


def _ema_vote(close, precio, periodo):
    """Precio por encima de la EMA -> CALL; por debajo -> PUT (regla del trader)."""
    e = _last(Indicators.ema(close, periodo))
    if e is None or precio is None or len(close) < periodo:
        return HOLD
    if precio > e:
        return CALL
    if precio < e:
        return PUT
    return HOLD


def _rsi_vote(close, periodo=5):
    """RSI rápido: <20 sobreventa (CALL), >80 sobrecompra (PUT)."""
    v = _last(Indicators.rsi(close, periodo))
    if v is None:
        return HOLD
    if v < 20:
        return CALL
    if v > 80:
        return PUT
    return HOLD


def _stochastic_vote(high, low, close, k=5, d=3):
    """Stochastic 5,3,3: cruce en zona extrema = entrada."""
    ks, ds = Indicators.stochastic(high, low, close, k, d)
    kv, dv = _last(ks), _last(ds)
    if kv is None or dv is None or len(ks) < 2:
        return HOLD
    kp, dp = float(ks.iloc[-2]), float(ds.iloc[-2])
    if kv < 20 and kv > dv and kp <= dp:      # cruce al alza en sobreventa
        return CALL
    if kv > 80 and kv < dv and kp >= dp:      # cruce a la baja en sobrecompra
        return PUT
    if kv < 20:
        return CALL
    if kv > 80:
        return PUT
    return HOLD


def _bollinger_vote(close, periodo=14, desv=1.02):
    """Bollinger 14/1.02: %B fuera de banda = saturación (reversión)."""
    upper, mid, lower, pct_b = Indicators.bollinger_bands(close, periodo, desv)
    b = _last(pct_b)
    if b is None:
        return HOLD
    if b < 0.10:                              # pegado/fuera de la banda baja
        return CALL
    if b > 0.90:                              # pegado/fuera de la banda alta
        return PUT
    return HOLD


def _macd_vote(close, fast=12, slow=26, signal=9):
    """MACD 12,26,9: histograma > 0 alcista, < 0 bajista (cruce = más fuerte)."""
    macd_line, signal_line, hist = Indicators.macd(close, fast, slow, signal)
    h = _last(hist)
    if h is None:
        return HOLD
    if h > 0:
        return CALL
    if h < 0:
        return PUT
    return HOLD


def _donchian_vote(high, low, close, periodo=20):
    """
    Donchian 20 = canal de RUPTURA (no reversión). El trader lo lee así: el precio
    tocando/rompiendo el BORDE SUPERIOR es fuerza alcista y CONTINUACIÓN (CALL);
    rompiendo el borde INFERIOR es fuerza bajista (PUT). Es lo contrario de un
    oscilador: en Donchian el extremo confirma el movimiento, no lo revierte.
    """
    if close is None or len(close) < periodo:
        return HOLD
    hh = _last(high.rolling(periodo).max())
    ll = _last(low.rolling(periodo).min())
    p = _last(close)
    if None in (hh, ll, p) or hh == ll:
        return HOLD
    pos = (p - ll) / (hh - ll)
    if pos >= 0.90:                           # pegado/rompiendo el techo -> fuerza alcista
        return CALL
    if pos <= 0.10:                           # pegado/rompiendo el piso -> fuerza bajista
        return PUT
    return HOLD


def _soporte_resistencia_vote(high, low, close, lookback=20):
    """
    Soportes/Resistencias dinámicos: últimos `lookback` máximos/mínimos. Precio
    pegado al soporte (mínimo reciente) -> CALL; pegado a la resistencia -> PUT.
    """
    if close is None or len(close) < lookback:
        return HOLD
    soporte = _last(low.rolling(lookback).min())
    resistencia = _last(high.rolling(lookback).max())
    p = _last(close)
    if None in (soporte, resistencia, p) or resistencia == soporte:
        return HOLD
    rango = resistencia - soporte
    if (p - soporte) <= 0.10 * rango:         # cerca del soporte
        return CALL
    if (resistencia - p) <= 0.10 * rango:     # cerca de la resistencia
        return PUT
    return HOLD


def votar_sistema(df, sistema=otc_system):
    """
    Devuelve los 10 votos del sistema con los parámetros del trader:
      {clave_indicador: "CALL"|"PUT"|"HOLD"}
    df: DataFrame con columnas open/high/low/close.
    sistema: módulo de config (otc_system o real_system) de donde salen los
    parámetros (períodos EMA, RSI 5, Stoch 5,3,3, Bollinger 14/1.02, ...).
    """
    votos = {}
    if df is None or len(df) == 0:
        return votos
    close = df["close"]
    high = df["high"]
    low = df["low"]
    precio = _last(close)

    for ind in sistema.INDICADORES:              # canónico (OTC o real)
        clave, tipo = ind["clave"], ind["tipo"]
        if tipo == "ema":
            votos[clave] = _ema_vote(close, precio, ind["periodo"])
        elif tipo == "rsi":
            votos[clave] = _rsi_vote(close, ind["periodo"])
        elif tipo == "stochastic":
            votos[clave] = _stochastic_vote(high, low, close, ind["k"], ind["d"])
        elif tipo == "bollinger":
            votos[clave] = _bollinger_vote(close, ind["periodo"], ind["desv"])
        elif tipo == "macd":
            votos[clave] = _macd_vote(close, ind["fast"], ind["slow"], ind["signal"])
        elif tipo == "donchian":
            votos[clave] = _donchian_vote(high, low, close, ind["periodo"])
        elif tipo == "niveles":
            votos[clave] = _soporte_resistencia_vote(high, low, close,
                                                     ind["lookback"])
    return votos


def direccion(votos):
    """
    Resume los votos en una dirección y su fuerza (cuántos coinciden).
    Devuelve (dir 'CALL'|'PUT'|'HOLD', n_call, n_put).
    """
    n_call = sum(1 for v in votos.values() if v == CALL)
    n_put = sum(1 for v in votos.values() if v == PUT)
    if n_call > n_put:
        return CALL, n_call, n_put
    if n_put > n_call:
        return PUT, n_call, n_put
    return HOLD, n_call, n_put
