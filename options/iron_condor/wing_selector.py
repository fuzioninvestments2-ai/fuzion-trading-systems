from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional
from options.common.chain_models import ChainData, OptionContract


@dataclass
class CondorCandidate:
    symbol: str
    expiration: str
    dte: int
    put_long: float
    put_short: float
    call_short: float
    call_long: float
    credit: float
    width: float
    max_loss: float
    pop: float
    iv_rank: float
    score: float = 0.0


class WingSelector:
    TARGET_DELTA = 0.16

    def build_condor(self, symbol: str, chain: ChainData,
                     iv_rank: float, account_size: float) -> Optional[CondorCandidate]:
        S = chain.underlying_price
        put_short = self._find_strike(chain.puts, -self.TARGET_DELTA, "put")
        call_short = self._find_strike(chain.calls, self.TARGET_DELTA, "call")
        if put_short is None or call_short is None:
            return None

        put_long = self._find_wing(chain.puts, put_short.strike - 5, "put")
        call_long = self._find_wing(chain.calls, call_short.strike + 5, "call")
        if put_long is None or call_long is None:
            return None

        credit = (put_short.mid_price - put_long.mid_price
                  + call_short.mid_price - call_long.mid_price)
        width = put_short.strike - put_long.strike
        max_loss = (width - credit) * 100

        iv = chain.calls[0].implied_volatility if chain.calls else 0.20
        daily_sd = S * iv / math.sqrt(252)
        dte = chain.dte or 30
        total_sd = daily_sd * math.sqrt(dte)
        distance_put = (S - put_short.strike) / total_sd if total_sd > 0 else 0
        distance_call = (call_short.strike - S) / total_sd if total_sd > 0 else 0
        from scipy.stats import norm
        pop = (norm.cdf(distance_call) - norm.cdf(-distance_put)) * 100

        return CondorCandidate(
            symbol=symbol,
            expiration=chain.expiration,
            dte=dte,
            put_long=put_long.strike,
            put_short=put_short.strike,
            call_short=call_short.strike,
            call_long=call_long.strike,
            credit=round(credit, 2),
            width=round(width, 2),
            max_loss=round(max_loss, 2),
            pop=round(pop, 2),
            iv_rank=iv_rank,
        )

    def _find_strike(self, contracts, target_delta: float,
                     option_type: str) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            if c.delta_estimate == 0:
                continue
            dist = abs(c.delta_estimate - target_delta)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    def _find_wing(self, contracts, target_strike: float,
                   option_type: str) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            dist = abs(c.strike - target_strike)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best
