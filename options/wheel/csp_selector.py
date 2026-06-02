from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from options.common.chain_models import ChainData, OptionContract, UnderlyingInfo


@dataclass
class CSPCandidate:
    symbol: str
    strike: float
    expiration: str
    dte: int
    delta: float
    premium: float
    iv_rank: float
    open_interest: int
    volume: int
    spread_pct: float
    premium_yield: float
    score: float = 0.0


class CSPSelector:
    def build_candidate(self, symbol: str, chain: ChainData, put: OptionContract,
                        iv_rank: float, underlying: UnderlyingInfo) -> Optional[CSPCandidate]:
        if put.mid_price <= 0:
            return None
        spread_pct = put.bid_ask_spread / put.mid_price
        premium_yield = put.mid_price / put.strike if put.strike > 0 else 0
        return CSPCandidate(
            symbol=symbol,
            strike=put.strike,
            expiration=put.expiration,
            dte=put.dte if put.dte else chain.dte,
            delta=put.delta_estimate,
            premium=put.mid_price,
            iv_rank=iv_rank,
            open_interest=put.open_interest,
            volume=put.volume,
            spread_pct=round(spread_pct, 4),
            premium_yield=round(premium_yield, 4),
        )

    def select_csp(self, candidates: List[CSPCandidate]) -> List[CSPCandidate]:
        filtered = [
            c for c in candidates
            if c.iv_rank >= 30
            and -0.35 <= c.delta <= -0.25
            and 30 <= c.dte <= 45
            and c.spread_pct <= 0.10
            and c.open_interest >= 500
            and c.volume >= 100
        ]
        return self.rank(filtered)

    def rank(self, candidates: List[CSPCandidate]) -> List[CSPCandidate]:
        for c in candidates:
            c.score = (
                c.iv_rank * 0.30
                + c.premium_yield * 1000 * 0.30
                + (c.open_interest / 1000) * 0.20
                + (1 - c.spread_pct) * 0.20
            )
        return sorted(candidates, key=lambda x: x.score, reverse=True)
