from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time
from .setup_scanner import MomentumSetup


@dataclass
class TimingSignal:
    signal: str  # "ENTER" | "WAIT" | "AVOID"
    reason: str
    ideal_window: str


class EntryTimer:
    AVOID_OPEN_MINUTES = 15
    AVOID_CLOSE_MINUTES = 30
    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(16, 0)

    def get_timing(self, setup: MomentumSetup,
                   now: Optional[datetime] = None) -> TimingSignal:
        if now is None:
            now = datetime.utcnow()

        current_time = now.time()
        market_open_plus = time(9, 30 + self.AVOID_OPEN_MINUTES)
        market_close_minus = time(15, 60 - self.AVOID_CLOSE_MINUTES)

        if current_time < self.MARKET_OPEN:
            return TimingSignal("WAIT", "Market not open", "09:45-15:30 ET")

        if current_time < market_open_plus:
            if setup.setup_type == "gap":
                return TimingSignal("ENTER", "Gap play: enter within first 15min",
                                    "09:30-09:45 ET")
            return TimingSignal("WAIT", "Avoid first 15min for non-gap setups",
                                "09:45-15:30 ET")

        if current_time > market_close_minus:
            return TimingSignal("AVOID", "Too close to market close", "09:45-15:30 ET")

        if setup.setup_type == "breakout" and setup.confidence >= 0.75:
            return TimingSignal("ENTER", "High-confidence breakout confirmed",
                                "09:45-15:30 ET")

        if setup.setup_type == "squeeze":
            return TimingSignal("ENTER", "Squeeze release — enter on direction confirmation",
                                "09:45-15:30 ET")

        if setup.setup_type == "vwap_reclaim":
            return TimingSignal("ENTER", "VWAP reclaim confirmed", "09:45-15:30 ET")

        if setup.confidence >= 0.70:
            return TimingSignal("ENTER", "Confidence threshold met", "09:45-15:30 ET")

        return TimingSignal("WAIT", "Setup confidence below threshold", "09:45-15:30 ET")


from typing import Optional
