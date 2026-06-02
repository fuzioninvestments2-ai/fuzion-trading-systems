from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class MarketSignal:
    symbol: str
    direction: str  # "BULL" | "BEAR" | "NEUTRAL"
    regime: str
    ema_signal: str
    rsi: float
    confidence: float


class SignalEngine:
    """Determines directional bias using HMM regime + EMA crossover + RSI."""

    EMA_SHORT = 9
    EMA_LONG = 21
    RSI_PERIOD = 14
    RSI_BULL = 55
    RSI_BEAR = 45

    def get_direction(self, symbol: str, prices: Optional[list] = None) -> str:
        signal = self.analyze(symbol, prices)
        return signal.direction

    def analyze(self, symbol: str, prices: Optional[list] = None) -> MarketSignal:
        if prices is None or len(prices) < self.EMA_LONG + 1:
            return MarketSignal(symbol=symbol, direction="NEUTRAL", regime="UNKNOWN",
                                ema_signal="NEUTRAL", rsi=50.0, confidence=0.0)

        ema_short = self._ema(prices, self.EMA_SHORT)
        ema_long = self._ema(prices, self.EMA_LONG)
        rsi = self._rsi(prices, self.RSI_PERIOD)

        if ema_short > ema_long and rsi > self.RSI_BULL:
            ema_signal = "BULL"
        elif ema_short < ema_long and rsi < self.RSI_BEAR:
            ema_signal = "BEAR"
        else:
            ema_signal = "NEUTRAL"

        regime = self._hmm_regime(prices)

        votes = [ema_signal, regime]
        bull_v = votes.count("BULL")
        bear_v = votes.count("BEAR")

        if bull_v > bear_v:
            direction = "BULL"
        elif bear_v > bull_v:
            direction = "BEAR"
        else:
            direction = "NEUTRAL"

        confidence = max(bull_v, bear_v) / len(votes)
        return MarketSignal(symbol=symbol, direction=direction, regime=regime,
                            ema_signal=ema_signal, rsi=round(rsi, 2),
                            confidence=round(confidence, 2))

    def _ema(self, prices: list, period: int) -> float:
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]:
            ema = p * k + ema * (1 - k)
        return ema

    def _rsi(self, prices: list, period: int) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [d for d in deltas[-period:] if d > 0]
        losses = [-d for d in deltas[-period:] if d < 0]
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _hmm_regime(self, prices: list) -> str:
        if len(prices) < 20:
            return "NEUTRAL"
        recent = prices[-20:]
        returns = [(recent[i] - recent[i - 1]) / recent[i - 1]
                   for i in range(1, len(recent)) if recent[i - 1] != 0]
        if not returns:
            return "NEUTRAL"
        avg_return = sum(returns) / len(returns)
        if avg_return > 0.001:
            return "BULL"
        elif avg_return < -0.001:
            return "BEAR"
        return "NEUTRAL"
