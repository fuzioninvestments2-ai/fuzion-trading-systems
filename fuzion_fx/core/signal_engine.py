"""
core/signal_engine.py (fuzion_fx)
=================================
Detecta CALL / PUT / NEUTRAL por CONFIRMACIONES de indicadores.

Cada indicador emite un voto (+1 CALL, -1 PUT, 0 neutral). Si un lado junta al
menos `min_confirmations` votos y domina al otro, esa es la senal; si no, NEUTRAL.
PORQUE: exigir varias confirmaciones independientes reduce las falsas senales de
un solo indicador. El `setup_id` (que indicadores confirmaron + direccion)
identifica el "tipo de jugada" para que el aprendizaje mida su acierto real.

Sin red. Se prueba con velas sinteticas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from indicators.ema import calculate_ema_pair
from indicators.rsi import rsi as _rsi
from indicators.macd import macd as _macd
from indicators.bollinger import bollinger as _bollinger
from indicators.atr import atr as _atr

CALL = "CALL"
PUT = "PUT"
NEUTRAL = "NEUTRAL"


class SignalEngine:
    def __init__(self, indicators_cfg: Dict[str, Any],
                 signal_cfg: Dict[str, Any]) -> None:
        self.ind = indicators_cfg
        self.min_confirmations = int(signal_cfg.get("min_confirmations", 3))

    def _votos(self, candles: Dict[str, Sequence[float]]) -> Dict[str, int]:
        close = list(candles["close"])
        high = list(candles.get("high", close))
        low = list(candles.get("low", close))
        precio = close[-1]
        i = self.ind

        votos: Dict[str, int] = {}

        # EMA: rapida sobre lenta = alcista.
        ef, es = calculate_ema_pair(close, i["ema_fast"], i["ema_slow"])
        votos["ema"] = 1 if ef > es else (-1 if ef < es else 0)

        # RSI: sobreventa -> CALL, sobrecompra -> PUT.
        r = _rsi(close, i["rsi_period"])
        votos["rsi"] = 1 if r < 30 else (-1 if r > 70 else 0)

        # MACD: histograma positivo -> impulso alcista.
        _, _, hist = _macd(close, i["macd_fast"], i["macd_slow"], i["macd_signal"])
        votos["macd"] = 1 if hist > 0 else (-1 if hist < 0 else 0)

        # Bollinger: precio bajo la banda inferior -> CALL; sobre la superior -> PUT.
        up, _, low_b = _bollinger(close, i["bb_period"], i["bb_std"])
        votos["bollinger"] = 1 if precio < low_b else (-1 if precio > up else 0)

        return votos

    def analyze(self, candles: Dict[str, Sequence[float]]) -> Dict[str, Any]:
        """
        Devuelve el veredicto: {signal, confirmations, votes, confirming, setup_id,
        atr, price}. NEUTRAL si ningun lado llega a `min_confirmations` o hay empate.
        """
        close = list(candles["close"])
        high = list(candles.get("high", close))
        low = list(candles.get("low", close))
        if len(close) < 2:
            return {"signal": NEUTRAL, "confirmations": 0, "votes": {},
                    "confirming": [], "setup_id": None, "atr": 0.0,
                    "price": close[-1] if close else 0.0}

        votos = self._votos(candles)
        call = [k for k, v in votos.items() if v > 0]
        put = [k for k, v in votos.items() if v < 0]

        if len(call) >= self.min_confirmations and len(call) > len(put):
            signal, confirming = CALL, sorted(call)
        elif len(put) >= self.min_confirmations and len(put) > len(call):
            signal, confirming = PUT, sorted(put)
        else:
            signal, confirming = NEUTRAL, []

        setup_id = f"{signal}|{','.join(confirming)}" if signal != NEUTRAL else None
        return {
            "signal": signal,
            "confirmations": len(confirming),
            "votes": votos,
            "confirming": confirming,
            "setup_id": setup_id,
            "atr": _atr(high, low, close, self.ind["atr_period"]),
            "price": close[-1],
        }
