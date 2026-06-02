from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common.chain_models import ChainData, OptionContract


REGIME_DELTA = {"BULL": 0.30, "NEUTRAL": 0.30, "BEAR": 0.35}


@dataclass
class CCCandidate:
    symbol: str
    strike: float
    expiration: str
    dte: int
    delta: float
    premium: float
    cost_basis: float
    annualized_yield: float
    above_cost_basis: bool
    score: float = 0.0


class CCSelector:
    def build_candidate(self, symbol: str, chain: ChainData, cost_basis: float,
                        iv_rank: float, regime: str = "NEUTRAL") -> Optional[CCCandidate]:
        target_delta = REGIME_DELTA.get(regime, 0.30)
        if iv_rank > 60:
            delta_range = (0.30, 0.40)
        elif iv_rank < 30:
            delta_range = (0.15, 0.25)
        else:
            delta_range = (target_delta - 0.05, target_delta + 0.05)

        best: Optional[OptionContract] = None
        best_dist = float("inf")
        for call in chain.calls:
            if call.strike <= cost_basis:
                continue
            if not (delta_range[0] <= call.delta_estimate <= delta_range[1]):
                continue
            dist = abs(call.delta_estimate - target_delta)
            if dist < best_dist:
                best_dist = dist
                best = call

        if best is None:
            return None

        annualized = (best.mid_price / cost_basis) * (365 / chain.dte) if chain.dte > 0 else 0
        return CCCandidate(
            symbol=symbol,
            strike=best.strike,
            expiration=best.expiration,
            dte=chain.dte,
            delta=best.delta_estimate,
            premium=best.mid_price,
            cost_basis=cost_basis,
            annualized_yield=round(annualized, 4),
            above_cost_basis=best.strike > cost_basis,
        )

    def select_cc(self, candidates: List[CCCandidate]) -> List[CCCandidate]:
        filtered = [c for c in candidates if c.above_cost_basis and c.premium > 0]
        for c in filtered:
            c.score = c.annualized_yield * 0.60 + (c.premium / c.cost_basis) * 0.40
        return sorted(filtered, key=lambda x: x.score, reverse=True)
