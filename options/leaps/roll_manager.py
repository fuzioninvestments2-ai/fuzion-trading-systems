from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from options.common import OptionsChainFetcher
from options.common.chain_models import ChainData, OptionContract


@dataclass
class RollResult:
    action: str
    old_strike: float
    old_expiration: str
    new_strike: float
    new_expiration: str
    credit_received: float
    reason: str


class RollManager:
    ROLL_DTE_THRESHOLD = 21
    TARGET_DELTA = 0.30

    def __init__(self):
        self._fetcher = OptionsChainFetcher()

    def should_roll(self, dte: int, current_delta: float,
                    profit_pct: float) -> bool:
        if dte <= self.ROLL_DTE_THRESHOLD:
            return True
        if profit_pct >= 0.75:
            return True
        return False

    def roll_short_call(self, symbol: str, current_strike: float,
                        current_expiration: str, current_dte: int,
                        profit_pct: float, long_strike: float) -> Optional[RollResult]:
        if not self.should_roll(current_dte, 0.0, profit_pct):
            return None

        try:
            chains = self._fetcher.get_multi_expiry_chain(symbol, dte_range=(25, 45))
            for exp, chain in chains.items():
                new_short = self._find_short(chain, long_strike)
                if new_short is None:
                    continue
                credit = new_short.mid_price
                return RollResult(
                    action="ROLL_SHORT_CALL",
                    old_strike=current_strike,
                    old_expiration=current_expiration,
                    new_strike=new_short.strike,
                    new_expiration=new_short.expiration,
                    credit_received=round(credit, 2),
                    reason=f"DTE={current_dte} or profit {profit_pct:.0%}",
                )
        except Exception:
            pass
        return None

    def _find_short(self, chain: ChainData, long_strike: float) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in chain.calls:
            if c.strike <= long_strike:
                continue
            if not (0.25 <= c.delta_estimate <= 0.40):
                continue
            dist = abs(c.delta_estimate - self.TARGET_DELTA)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best
