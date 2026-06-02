from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class TradingSignal:
    symbol: str
    direction: str  # "BULL" | "BEAR" | "NEUTRAL"
    setup_type: str  # "breakout" | "regime_shift" | "momentum" | "none"
    confidence: float
    details: str


class SignalEngine:
    """Detects breakouts and regime shifts to determine debit spread direction."""

    BREAKOUT_VOL_MULT = 2.0
    GAP_THRESHOLD = 0.02

    def get_signal(self, symbol: str, prices: Optional[list] = None,
                   volumes: Optional[list] = None) -> TradingSignal:
        if prices is None or len(prices) < 20:
            return TradingSignal(symbol=symbol, direction="NEUTRAL",
                                 setup_type="none", confidence=0.0,
                                 details="Insufficient data")

        breakout = self._detect_breakout(prices, volumes)
        if breakout["detected"]:
            return TradingSignal(
                symbol=symbol,
                direction=breakout["direction"],
                setup_type="breakout",
                confidence=breakout["confidence"],
                details=breakout["details"],
            )

        regime = self._detect_regime_shift(prices)
        if regime["detected"]:
            return TradingSignal(
                symbol=symbol,
                direction=regime["direction"],
                setup_type="regime_shift",
                confidence=regime["confidence"],
                details=regime["details"],
            )

        return TradingSignal(symbol=symbol, direction="NEUTRAL",
                             setup_type="none", confidence=0.0,
                             details="No clear setup detected")

    def _detect_breakout(self, prices: list, volumes: Optional[list]) -> dict:
        recent_high = max(prices[-20:-1]) if len(prices) >= 20 else max(prices[:-1])
        recent_low = min(prices[-20:-1]) if len(prices) >= 20 else min(prices[:-1])
        current = prices[-1]

        vol_confirm = False
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:-1]) / 19
            vol_confirm = volumes[-1] > avg_vol * self.BREAKOUT_VOL_MULT

        if current > recent_high * 1.005:
            confidence = 0.80 if vol_confirm else 0.55
            return {"detected": True, "direction": "BULL", "confidence": confidence,
                    "details": f"Breakout above {recent_high:.2f}"}
        elif current < recent_low * 0.995:
            confidence = 0.80 if vol_confirm else 0.55
            return {"detected": True, "direction": "BEAR", "confidence": confidence,
                    "details": f"Breakdown below {recent_low:.2f}"}
        return {"detected": False, "direction": "NEUTRAL", "confidence": 0.0, "details": ""}

    def _detect_regime_shift(self, prices: list) -> dict:
        if len(prices) < 40:
            return {"detected": False, "direction": "NEUTRAL", "confidence": 0.0, "details": ""}
        early = prices[-40:-20]
        recent = prices[-20:]
        early_avg = sum(early) / len(early)
        recent_avg = sum(recent) / len(recent)
        change_pct = (recent_avg - early_avg) / early_avg if early_avg != 0 else 0

        if change_pct > 0.03:
            return {"detected": True, "direction": "BULL", "confidence": 0.65,
                    "details": f"Regime shift bullish {change_pct:.1%}"}
        elif change_pct < -0.03:
            return {"detected": True, "direction": "BEAR", "confidence": 0.65,
                    "details": f"Regime shift bearish {change_pct:.1%}"}
        return {"detected": False, "direction": "NEUTRAL", "confidence": 0.0, "details": ""}
