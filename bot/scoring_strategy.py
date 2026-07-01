"""
bot/scoring_strategy.py
=======================
Estrategia de PUNTUACIÓN multi-indicador con "stack methods" (votación).

Combina varios indicadores. Cada uno "vota" CALL / PUT / HOLD con una fuerza.
Se suman votos ponderados y se decide según el método (conservative / moderate /
aggressive), que exige un número mínimo de indicadores coincidentes y una
confianza mínima.

EL PORQUÉ de votar en vez de fiarse de un solo indicador: cada indicador se
equivoca de forma distinta; exigir que VARIOS coincidan reduce señales falsas
(es justo la idea de "confluencia"/apilamiento de la especificación).

Reutiliza `core/indicators.py` (pandas) — NO reimplementa indicadores (Regla 1:
no duplicar). Trabaja sobre un DataFrame de velas (open/high/low/close).

Devuelve (señal, confianza, detalles) para poder registrar el porqué de cada
decisión (transparencia).
"""

import importlib.util
import os

import numpy as np

# Cargamos SOLO el archivo core/indicators.py (que únicamente depende de numpy y
# pandas), sin pasar por core/__init__.py — ese __init__ importa el motor HMM y
# librerías pesadas (hmmlearn) que no necesitamos aquí. Así reutilizamos los
# indicadores existentes sin arrastrar dependencias ajenas a este módulo.
_CORE_INDICATORS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "core", "indicators.py")
_spec = importlib.util.spec_from_file_location("fuzion_core_indicators",
                                               _CORE_INDICATORS)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Indicators = _mod.Indicators

CALL = "CALL"
PUT = "PUT"
HOLD = "HOLD"

# Pesos de cada indicador (de la especificación). MACD pesa más porque combina
# tendencia y momento; el estocástico menos porque es más ruidoso.
WEIGHTS = {
    "rsi": 2.0,
    "macd": 3.0,
    "bollinger": 2.0,
    "moving_averages": 2.0,
    "stochastic": 1.0,
}


def _last(series):
    """Último valor de una Series, o None si está vacío o es NaN."""
    if series is None or len(series) == 0:
        return None
    v = series.iloc[-1]
    return None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)


def _rsi_signal(close):
    v = _last(Indicators.rsi(close, 14))
    if v is None:
        return HOLD, 0.5
    if v < 30:
        return CALL, 0.8
    if v < 40:
        return CALL, 0.6
    if v > 70:
        return PUT, 0.8
    if v > 60:
        return PUT, 0.6
    return HOLD, 0.5


def _macd_signal(close):
    macd_line, signal_line, hist = Indicators.macd(close)
    m, s = _last(macd_line), _last(signal_line)
    h = _last(hist)
    if None in (m, s, h) or len(macd_line) < 2:
        return HOLD, 0.5
    m_prev, s_prev = float(macd_line.iloc[-2]), float(signal_line.iloc[-2])
    # Cruce alcista/bajista de la línea MACD sobre su señal.
    cross_up = m > s and m_prev <= s_prev
    cross_down = m < s and m_prev >= s_prev
    if cross_up and h > 0:
        return CALL, 0.85
    if cross_down and h < 0:
        return PUT, 0.85
    if h > 0:
        return CALL, 0.6
    if h < 0:
        return PUT, 0.6
    return HOLD, 0.5


def _bollinger_signal(close):
    upper, mid, lower, pct_b = Indicators.bollinger_bands(close, 20, 2.0)
    price = _last(close)
    b = _last(pct_b)
    if price is None or b is None:
        return HOLD, 0.5
    if b < 0:                       # precio por debajo de la banda inferior
        return CALL, 0.8
    if b > 1:                       # precio por encima de la banda superior
        return PUT, 0.8
    if b < 0.2:
        return CALL, 0.6
    if b > 0.8:
        return PUT, 0.6
    return HOLD, 0.5


def _ma_signal(close):
    sma20 = _last(Indicators.sma(close, 20))
    sma50 = _last(Indicators.sma(close, 50))
    sma200 = _last(Indicators.sma(close, 200))
    price = _last(close)
    if None in (sma20, sma50, sma200, price):
        return HOLD, 0.5           # no hay suficientes velas para las 3 SMAs
    if price > sma20 > sma50 > sma200:
        return CALL, 0.75          # tendencia alcista alineada
    if price < sma20 < sma50 < sma200:
        return PUT, 0.75           # tendencia bajista alineada
    return HOLD, 0.5


def _stochastic_signal(high, low, close):
    k_series, d_series = Indicators.stochastic(high, low, close, 14, 3)
    k, d = _last(k_series), _last(d_series)
    if k is None or d is None or len(k_series) < 2:
        return HOLD, 0.5
    k_prev, d_prev = float(k_series.iloc[-2]), float(d_series.iloc[-2])
    if k < 20 and d < 20 and k > d and k_prev <= d_prev:
        return CALL, 0.8
    if k > 80 and d > 80 and k < d and k_prev >= d_prev:
        return PUT, 0.8
    if k < 20 and d < 20:
        return CALL, 0.6
    if k > 80 and d > 80:
        return PUT, 0.6
    return HOLD, 0.5


class ScoringStrategy:
    """
    Estrategia principal. `analyze(df)` -> (señal, confianza, detalles).

    df: DataFrame con columnas open/high/low/close (volume opcional).
    cfg: TradingConfig (usa required_votes y min_confidence).
    """

    def __init__(self, cfg):
        self.cfg = cfg

    def analyze(self, df):
        if df is None or len(df) < 2:
            return HOLD, 0.0, {"motivo": "datos insuficientes"}

        close = df["close"]
        high = df.get("high", close)
        low = df.get("low", close)

        # Cada indicador emite su voto (señal, fuerza).
        votes = {
            "rsi": _rsi_signal(close),
            "macd": _macd_signal(close),
            "bollinger": _bollinger_signal(close),
            "moving_averages": _ma_signal(close),
            "stochastic": _stochastic_signal(high, low, close),
        }

        call_score = put_score = 0.0
        call_votes = put_votes = 0
        for name, (sig, strength) in votes.items():
            w = WEIGHTS[name]
            if sig == CALL:
                call_score += w * strength
                call_votes += 1
            elif sig == PUT:
                put_score += w * strength
                put_votes += 1

        max_score = sum(WEIGHTS.values())
        # Confianza: qué tan desequilibrada está la decisión (0..1).
        confidence = abs(call_score - put_score) / max_score

        required = self.cfg.required_votes
        min_conf = self.cfg.min_confidence

        signal = HOLD
        if (call_votes >= required and call_votes > put_votes
                and confidence >= min_conf):
            signal = CALL
        elif (put_votes >= required and put_votes > call_votes
              and confidence >= min_conf):
            signal = PUT

        details = {
            "votes": {k: v[0] for k, v in votes.items()},
            "call_votes": call_votes, "put_votes": put_votes,
            "call_score": round(call_score, 3), "put_score": round(put_score, 3),
            "confidence": round(confidence, 3),
            "required_votes": required, "min_confidence": min_conf,
        }
        return signal, confidence, details
