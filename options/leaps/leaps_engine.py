from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer
from options.common.chain_models import OptionContract
from .portfolio_manager import LEAPSPortfolioManager
from .journal import LEAPSJournal


@dataclass
class LEAPSCandidate:
    symbol: str
    strike: float
    expiration: str
    dte: int
    delta: float
    premium: float
    bid_ask_spread: float
    bid_ask_pct: float
    intrinsic: float
    extrinsic: float
    extrinsic_pct: float
    iv: float
    score: float = 0.0


class LEAPSEngine:
    MIN_DTE = 365
    TARGET_DELTA_LOW = 0.70
    TARGET_DELTA_HIGH = 0.80
    MAX_EXTRINSIC_PCT = 0.15
    MAX_BID_ASK_PCT = 0.05

    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self.portfolio = LEAPSPortfolioManager()
        self.journal = LEAPSJournal()

    def find_leaps(self, symbols: List[str]) -> List[LEAPSCandidate]:
        results = []
        for sym in symbols:
            try:
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(365, 730))
                for exp, chain in chains.items():
                    if chain.dte < self.MIN_DTE:
                        continue
                    for call in chain.calls:
                        cand = self._evaluate_leaps(sym, chain.underlying_price, call, chain.dte)
                        if cand:
                            results.append(cand)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _evaluate_leaps(self, symbol: str, underlying_price: float,
                        contract: OptionContract, dte: int) -> Optional[LEAPSCandidate]:
        d = contract.delta_estimate
        if not (self.TARGET_DELTA_LOW <= d <= self.TARGET_DELTA_HIGH):
            return None

        if contract.mid_price <= 0:
            return None

        bid_ask_pct = contract.bid_ask_spread / contract.mid_price
        if bid_ask_pct > self.MAX_BID_ASK_PCT:
            return None

        intrinsic = max(0.0, underlying_price - contract.strike)
        extrinsic = contract.mid_price - intrinsic
        extrinsic_pct = extrinsic / contract.mid_price if contract.mid_price > 0 else 1.0
        if extrinsic_pct > self.MAX_EXTRINSIC_PCT:
            return None

        score = d * 0.40 + (1 - extrinsic_pct) * 0.40 + (1 - bid_ask_pct) * 0.20
        return LEAPSCandidate(
            symbol=symbol,
            strike=contract.strike,
            expiration=contract.expiration,
            dte=dte,
            delta=d,
            premium=contract.mid_price,
            bid_ask_spread=contract.bid_ask_spread,
            bid_ask_pct=round(bid_ask_pct, 4),
            intrinsic=round(intrinsic, 2),
            extrinsic=round(extrinsic, 2),
            extrinsic_pct=round(extrinsic_pct, 4),
            iv=contract.implied_volatility,
            score=round(score, 4),
        )
