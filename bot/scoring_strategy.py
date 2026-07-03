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

# Pesos BASE de cada indicador (de la especificación). MACD pesa más porque
# combina tendencia y momento; el estocástico menos porque es más ruidoso.
BASE_WEIGHTS = {
    "rsi": 2.0,
    "macd": 3.0,
    "bollinger": 2.0,
    "moving_averages": 2.0,
    "stochastic": 1.0,
    "donchian": 2.0,       # techo/piso (soporte-resistencia)
    "vwap": 2.0,           # precio "justo" (nivel de referencia profesional)
    "patterns": 1.5,       # forma de la vela (confirmación/reversión)
}
# Alias por compatibilidad con código/tests que aún usan WEIGHTS.
WEIGHTS = BASE_WEIGHTS


# ---------------------------------------------------------------------------
# CONFIGURACIÓN NO FIJA: los pesos cambian POR TIEMPO y POR RÉGIMEN.
# El usuario pidió expresamente que "la configuración de los indicadores no es
# fija, es por tiempo". Además, en tendencia (slide) vs rango (oscillate) los
# indicadores útiles NO son los mismos:
#   - En TENDENCIA fuerte, los osciladores (RSI/estocástico/Bollinger) dan
#     falsas señales de "reversión" que pelean contra la tendencia -> pesan menos;
#     MACD/medias/Donchian (seguidores de tendencia) pesan más.
#   - En RANGO, es al revés: los rebotes techo/piso (RSI/Bollinger/estocástico/
#     Donchian) mandan; MACD/medias dan cruces falsos -> pesan menos.
# Los factores son MULTIPLICADORES sobre los pesos base (1.0 = sin cambio).
# ---------------------------------------------------------------------------

# Por TIEMPO: en tiempos cortos (scalping) mandan los osciladores rápidos; las
# medias largas (SMA200) casi no tienen velas -> poco fiables. En tiempos largos
# manda la tendencia (medias/MACD/Donchian) y el estocástico ruidoso pesa menos.
def _factor_por_tiempo(tf_seconds):
    if tf_seconds is None:
        return {}
    if tf_seconds < 60:                 # corto: 5s..30s
        # En la entrada, la FORMA de la vela (patrones) informa mucho; el VWAP
        # es más ruidoso en tiempos muy cortos.
        return {"rsi": 1.3, "stochastic": 1.4, "bollinger": 1.2,
                "moving_averages": 0.5, "macd": 0.9,
                "patterns": 1.3, "vwap": 0.9}
    if tf_seconds <= 300:               # medio: 1m..5m (equilibrado)
        return {}
    return {"moving_averages": 1.3, "macd": 1.2, "donchian": 1.2,  # largo: >5m
            "stochastic": 0.6, "rsi": 0.9,
            "vwap": 1.1, "patterns": 0.8}


# Por RÉGIMEN (de scoring_strategy.regime()).
def _factor_por_regimen(regimen):
    if regimen == "slide":              # tendencia: seguir, no revertir
        # El VWAP confirma el lado de la tendencia; los patrones de reversión
        # pesan menos (pelean contra la corriente).
        return {"macd": 1.3, "moving_averages": 1.3, "donchian": 1.2,
                "rsi": 0.6, "bollinger": 0.6, "stochastic": 0.6,
                "vwap": 1.2, "patterns": 0.9}
    if regimen == "oscillate":          # rango: operar rebotes techo/piso
        # Los patrones de reversión en los extremos son oro; el VWAP se cruza
        # mucho en rango, así que pesa menos.
        return {"rsi": 1.3, "bollinger": 1.3, "stochastic": 1.3,
                "donchian": 1.2, "macd": 0.6, "moving_averages": 0.6,
                "patterns": 1.2, "vwap": 0.8}
    return {}                           # mixto/None: sin ajuste


def weights_for(tf_seconds=None, regimen=None, learned=None):
    """
    Devuelve los pesos AJUSTADOS para una temporalidad y un régimen concretos.
    Combina (multiplica) los factores de tiempo y de régimen sobre BASE_WEIGHTS.
    EL PORQUÉ: un mismo indicador no vale lo mismo en 15s que en 30m, ni en
    tendencia que en rango. Así la "configuración por tiempo" deja de ser fija.

    learned: dict opcional {indicador: multiplicador} APRENDIDO del historial del
    activo (bot/weight_learning). Sube el peso de los indicadores que más aciertan
    en ESE activo y baja el de los que fallan. Se aplica encima de tiempo/régimen.
    """
    ft = _factor_por_tiempo(tf_seconds)
    fr = _factor_por_regimen(regimen)
    lw = learned or {}
    out = {}
    for name, base in BASE_WEIGHTS.items():
        out[name] = (base * ft.get(name, 1.0) * fr.get(name, 1.0)
                     * lw.get(name, 1.0))
    return out


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


def _donchian_signal(high, low, close, period=20):
    """
    Canal de Donchian = TECHO (máx) y PISO (mín) de las últimas `period` velas.
    El porqué: mide dónde está el precio dentro de su rango — soporte/resistencia.
      - cerca del PISO -> posible rebote al alza (CALL)
      - cerca del TECHO -> posible rechazo a la baja (PUT)
    """
    if close is None or len(close) < period:
        return HOLD, 0.5
    hh_v = _last(high.rolling(period).max())
    ll_v = _last(low.rolling(period).min())
    price = _last(close)
    if None in (hh_v, ll_v, price) or hh_v == ll_v:
        return HOLD, 0.5
    pos = (price - ll_v) / (hh_v - ll_v)      # 0 = piso, 1 = techo
    if pos <= 0.10:
        return CALL, 0.8
    if pos >= 0.90:
        return PUT, 0.8
    if pos <= 0.25:
        return CALL, 0.6
    if pos >= 0.75:
        return PUT, 0.6
    return HOLD, 0.5


def _vwap_vote(df):
    """
    Voto del VWAP: precio por encima del 'precio justo' -> CALL; por debajo ->
    PUT. La fuerza crece con la distancia (más lejos = sesgo más marcado), con
    tope para no exagerar. Reutiliza bot/vwap (no reimplementa).
    """
    from bot.vwap import vwap_signal
    v = vwap_signal(df)
    side = v["side"]
    if side == HOLD:
        return HOLD, 0.5
    fuerza = min(0.85, 0.6 + abs(v["dist_pct"]) * 0.4)   # 0.6..0.85
    return side, fuerza


def _pattern_vote(df):
    """
    Voto por PATRÓN de vela: martillo/envolvente alcista -> CALL; estrella/
    envolvente bajista -> PUT. El doji NO vota (es indecisión). Reutiliza
    bot/candle_patterns (no reimplementa).
    """
    from bot.candle_patterns import detect_patterns
    p = detect_patterns(df)
    if p["indecision"] or p["bias"] is None:
        return HOLD, 0.5
    # Marubozu/envolvente son señales más fuertes que martillo/estrella sueltos.
    fuerte = any(("Marubozu" in x or "Envolvente" in x) for x in p["patrones"])
    return p["bias"], (0.8 if fuerte else 0.7)


def regime(high, low, close, period=14):
    """
    Detecta el RÉGIMEN del mercado con ADX (fuerza de tendencia):
      - ADX alto  (>=25) -> 'slide'     : hay TENDENCIA fuerte (seguir).
      - ADX bajo  (<=18) -> 'oscillate' : mercado en RANGO (rebotes techo/piso).
      - intermedio        -> 'mixto'.
    Devuelve (regimen, valor_adx).
    """
    adx_v = _last(Indicators.adx(high, low, close, period))
    if adx_v is None:
        return None, None
    if adx_v >= 25:
        return "slide", adx_v
    if adx_v <= 18:
        return "oscillate", adx_v
    return "mixto", adx_v


def compression(close, period=20, lookback=100, umbral_pct=0.25):
    """
    Detecta COMPRESIÓN (squeeze): cuando el mercado se lateraliza, las bandas de
    Bollinger se ESTRECHAN. Es el estado PREVIO a una ruptura, y la lectura del
    trader es: en compresión la entrada vive en el TIEMPO CORTO (el largo solo da
    el sesgo). EL PORQUÉ: un umbral de ancho FIJO no sirve (cada activo tiene su
    volatilidad); comparamos el ancho ACTUAL contra su propio historial reciente
    (percentil). Si está en el `umbral_pct` inferior (p.ej. 25% más estrecho que
    de costumbre), está comprimido.

    Devuelve (comprimido: bool, ancho_relativo: float 0-1). ancho_relativo es el
    percentil del ancho actual (0 = lo más estrecho visto; 1 = lo más ancho).
    """
    upper, mid, lower, _ = Indicators.bollinger_bands(close, period, 2.0)
    ancho = (upper - lower) / mid.replace(0, float("nan"))   # ancho normalizado
    ancho = ancho.dropna()
    if len(ancho) < max(period, 20):
        return False, None
    ventana = ancho.tail(int(lookback))
    actual = float(ventana.iloc[-1])
    # Percentil del ancho actual dentro de su ventana (rank empírico).
    percentil = float((ventana <= actual).mean())
    return percentil <= float(umbral_pct), round(percentil, 3)


class ScoringStrategy:
    """
    Estrategia principal. `analyze(df)` -> (señal, confianza, detalles).

    df: DataFrame con columnas open/high/low/close (volume opcional).
    cfg: TradingConfig (usa required_votes y min_confidence).
    """

    def __init__(self, cfg):
        self.cfg = cfg

    def analyze(self, df, weights=None):
        """
        weights: dict opcional de pesos por indicador. Si es None usa los BASE.
        Permite pasar pesos AJUSTADOS por tiempo/régimen (weights_for), para que
        la configuración de indicadores NO sea fija.
        """
        if df is None or len(df) < 2:
            return HOLD, 0.0, {"motivo": "datos insuficientes"}

        w_map = weights if weights else BASE_WEIGHTS

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
            "donchian": _donchian_signal(high, low, close),
            "vwap": _vwap_vote(df),
            "patterns": _pattern_vote(df),
        }

        call_score = put_score = 0.0
        call_votes = put_votes = 0
        for name, (sig, strength) in votes.items():
            w = w_map[name]
            if sig == CALL:
                call_score += w * strength
                call_votes += 1
            elif sig == PUT:
                put_score += w * strength
                put_votes += 1

        max_score = sum(w_map.values())
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
