"""
Strategy Orchestrator — Orquesta estrategias según el régimen HMM detectado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd

from .hmm_engine import RegimeInfo, RegimeLabel, RegimeState


class SignalDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass
class Signal:
    symbol: str
    direction: SignalDirection
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    position_size_pct: float
    leverage: float
    regime_id: int
    regime_name: str
    regime_probability: float
    timestamp: pd.Timestamp
    reasoning: str
    strategy_name: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "entry_price": round(self.entry_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "take_profit": round(self.take_profit, 4) if self.take_profit else None,
            "position_size_pct": round(self.position_size_pct, 4),
            "leverage": round(self.leverage, 2),
            "regime": {
                "id": self.regime_id,
                "name": self.regime_name,
                "probability": round(self.regime_probability, 4),
            },
            "strategy": self.strategy_name,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }


class BaseStrategy(ABC):
    strategy_name: str = "base"

    def __init__(self, config: dict, regime_info: RegimeInfo):
        self._config = config
        self._regime_info = regime_info

    @abstractmethod
    def generate_signal(
        self, symbol: str, bars: pd.DataFrame, regime_state: RegimeState
    ) -> Optional[Signal]:
        ...

    def _make_signal(
        self,
        symbol: str,
        direction: SignalDirection,
        entry_price: float,
        stop_loss: float,
        regime_state: RegimeState,
        reasoning: str,
        take_profit: Optional[float] = None,
        position_size_pct: Optional[float] = None,
        leverage: Optional[float] = None,
        confidence_boost: float = 0.0,
        **extra_metadata,
    ) -> Signal:
        regime = regime_state.current_regime
        size = position_size_pct if position_size_pct is not None else regime.position_size_pct
        lev = leverage if leverage is not None else regime.leverage
        confidence = min(1.0, regime_state.regime_probability + confidence_boost)

        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_pct=size,
            leverage=lev,
            regime_id=regime.regime_id,
            regime_name=regime.label.value,
            regime_probability=regime_state.regime_probability,
            timestamp=pd.Timestamp.now(),
            reasoning=reasoning,
            strategy_name=self.strategy_name,
            metadata=extra_metadata,
        )


# ---------------------------------------------------------------------------
# Estrategias concretas por régimen
# ---------------------------------------------------------------------------

class TrendFollowingStrategy(BaseStrategy):
    """Trend following para régimen BULL."""
    strategy_name = "trend_following"

    def generate_signal(self, symbol: str, bars: pd.DataFrame,
                        regime_state: RegimeState) -> Optional[Signal]:
        regime = regime_state.current_regime
        if regime.label not in (RegimeLabel.BULL, RegimeLabel.EUPHORIA):
            return None
        if len(bars) < 50:
            return None

        close = bars["close"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        atr = self._atr(bars, 14)

        if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]:
            entry = close.iloc[-1]
            stop = entry - 2 * atr
            if stop >= entry:
                return None
            tp = entry + 3 * atr
            reasoning = (f"EMA20 ({ema20.iloc[-1]:.2f}) > EMA50 ({ema50.iloc[-1]:.2f}), "
                         f"precio en tendencia alcista, régimen {regime.label.value}")
            return self._make_signal(symbol, SignalDirection.LONG, entry, stop,
                                     regime_state, reasoning, take_profit=tp,
                                     atr_14=round(atr, 4), rr_ratio=round(3.0, 2))
        return None

    @staticmethod
    def _atr(bars: pd.DataFrame, period: int) -> float:
        high = bars.get("high", bars["close"])
        low = bars.get("low", bars["close"])
        close = bars["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion para régimen NEUTRAL."""
    strategy_name = "mean_reversion"

    def generate_signal(self, symbol: str, bars: pd.DataFrame,
                        regime_state: RegimeState) -> Optional[Signal]:
        regime = regime_state.current_regime
        if regime.label != RegimeLabel.NEUTRAL:
            return None
        if len(bars) < 21:
            return None

        close = bars["close"]
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        z = (close - sma20) / std20

        if z.iloc[-1] < -2.0:
            entry = close.iloc[-1]
            stop = entry - 1.5 * float(std20.iloc[-1])
            tp = float(sma20.iloc[-1])
            reasoning = (f"Z-score: {z.iloc[-1]:.2f} (oversold), "
                         f"mean reversion hacia SMA20 ({sma20.iloc[-1]:.2f})")
            return self._make_signal(symbol, SignalDirection.LONG, entry, stop,
                                     regime_state, reasoning, take_profit=tp,
                                     zscore=round(float(z.iloc[-1]), 4))
        return None


class DefensiveStrategy(BaseStrategy):
    """Estrategia defensiva para régimen BEAR o CRASH."""
    strategy_name = "defensive"

    def generate_signal(self, symbol: str, bars: pd.DataFrame,
                        regime_state: RegimeState) -> Optional[Signal]:
        regime = regime_state.current_regime
        if regime.label not in (RegimeLabel.BEAR, RegimeLabel.CRASH):
            return None

        close = bars["close"]
        entry = close.iloc[-1]
        reasoning = (f"Régimen {regime.label.value} — señal FLAT, "
                     "preservar capital, no abrir nuevas posiciones largas")
        return self._make_signal(symbol, SignalDirection.FLAT, entry, entry,
                                 regime_state, reasoning, position_size_pct=0.0)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

class RegimeOrchestrator:
    """
    Asigna estrategias por régimen (vol_rank) y genera señales.
    """

    def __init__(self, config: dict):
        self._config = config
        self._min_confidence: float = config.get("min_confidence", 0.55)
        self._strategies: Dict[str, BaseStrategy] = {}

    def setup_strategies(self, regimes: List[RegimeInfo]) -> None:
        sorted_regimes = sorted(regimes, key=lambda r: r.expected_volatility)
        for rank, regime in enumerate(sorted_regimes):
            if rank <= len(sorted_regimes) // 3:
                strategy_cls = MeanReversionStrategy
            elif rank >= 2 * len(sorted_regimes) // 3:
                strategy_cls = TrendFollowingStrategy
            else:
                strategy_cls = TrendFollowingStrategy

            if regime.label in (RegimeLabel.CRASH, RegimeLabel.BEAR):
                strategy_cls = DefensiveStrategy

            self._strategies[regime.label.value] = strategy_cls(self._config, regime)

    def generate_signal(
        self, symbol: str, bars: pd.DataFrame, regime_state: RegimeState
    ) -> Optional[Signal]:
        label = regime_state.current_regime.label.value
        strategy = self._strategies.get(label)
        if strategy is None:
            return None

        # Si hay flickering o baja probabilidad → mitad tamaño, leverage=1.0
        if regime_state.is_uncertain or regime_state.regime_probability < self._min_confidence:
            from copy import deepcopy
            regime_state_copy = deepcopy(regime_state)
            regime_state_copy.current_regime.position_size_pct *= 0.5
            regime_state_copy.current_regime.leverage = 1.0
            return strategy.generate_signal(symbol, bars, regime_state_copy)

        return strategy.generate_signal(symbol, bars, regime_state)
