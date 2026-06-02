from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MomentumSetup:
    symbol: str
    setup_type: str  # "breakout" | "gap" | "squeeze" | "vwap_reclaim"
    direction: str   # "BULL" | "BEAR"
    confidence: float
    details: str


class SetupScanner:
    BREAKOUT_VOL_MULT = 2.0
    GAP_THRESHOLD = 0.02

    def scan(self, symbol: str, data: Optional[Dict] = None) -> List[MomentumSetup]:
        if data is None:
            return []
        setups = []

        breakout = self._check_breakout(symbol, data)
        if breakout:
            setups.append(breakout)

        gap = self._check_gap(symbol, data)
        if gap:
            setups.append(gap)

        squeeze = self._check_squeeze(symbol, data)
        if squeeze:
            setups.append(squeeze)

        vwap = self._check_vwap_reclaim(symbol, data)
        if vwap:
            setups.append(vwap)

        return setups

    def _check_breakout(self, symbol: str, data: Dict) -> Optional[MomentumSetup]:
        prices = data.get("prices", [])
        volumes = data.get("volumes", [])
        if len(prices) < 20 or len(volumes) < 20:
            return None
        recent_high = max(prices[-20:-1])
        avg_vol = sum(volumes[-20:-1]) / 19
        current_vol = volumes[-1]
        current = prices[-1]

        if current > recent_high and current_vol > avg_vol * self.BREAKOUT_VOL_MULT:
            return MomentumSetup(symbol=symbol, setup_type="breakout", direction="BULL",
                                 confidence=0.80,
                                 details=f"Breakout vol {current_vol/avg_vol:.1f}x above {recent_high:.2f}")
        return None

    def _check_gap(self, symbol: str, data: Dict) -> Optional[MomentumSetup]:
        prices = data.get("prices", [])
        if len(prices) < 2:
            return None
        gap_pct = (prices[-1] - prices[-2]) / prices[-2] if prices[-2] != 0 else 0
        if gap_pct > self.GAP_THRESHOLD:
            return MomentumSetup(symbol=symbol, setup_type="gap", direction="BULL",
                                 confidence=0.70, details=f"Gap up {gap_pct:.1%}")
        elif gap_pct < -self.GAP_THRESHOLD:
            return MomentumSetup(symbol=symbol, setup_type="gap", direction="BEAR",
                                 confidence=0.70, details=f"Gap down {gap_pct:.1%}")
        return None

    def _check_squeeze(self, symbol: str, data: Dict) -> Optional[MomentumSetup]:
        squeeze_released = data.get("squeeze_released", False)
        squeeze_direction = data.get("squeeze_direction", "BULL")
        if squeeze_released:
            return MomentumSetup(symbol=symbol, setup_type="squeeze",
                                 direction=squeeze_direction, confidence=0.75,
                                 details="Bollinger/Keltner squeeze released")
        return None

    def _check_vwap_reclaim(self, symbol: str, data: Dict) -> Optional[MomentumSetup]:
        price = data.get("prices", [None])[-1]
        vwap = data.get("vwap")
        prev_price = data.get("prices", [None, None])[-2] if len(data.get("prices", [])) >= 2 else None
        if price is None or vwap is None or prev_price is None:
            return None
        if prev_price < vwap <= price:
            return MomentumSetup(symbol=symbol, setup_type="vwap_reclaim", direction="BULL",
                                 confidence=0.65, details=f"Reclaimed VWAP at {vwap:.2f}")
        return None
