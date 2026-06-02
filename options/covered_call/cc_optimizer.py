from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer
from options.common.chain_models import ChainData, OptionContract
from .holdings_manager import HoldingsManager, Holding
from .income_tracker import IncomeTracker
from .portfolio_manager import CCPortfolioManager
from .journal import CCJournal


REGIME_DELTA = {"BULL": 0.20, "NEUTRAL": 0.30, "BEAR": 0.40}
IV_HIGH_THRESHOLD = 60
IV_LOW_THRESHOLD = 30


@dataclass
class CCOpportunity:
    symbol: str
    cost_basis: float
    strike: float
    expiration: str
    dte: int
    delta: float
    premium: float
    annualized_yield: float
    above_cost_basis: bool
    iv_rank: float
    regime: str
    score: float = 0.0


class CoveredCallOptimizer:
    def __init__(self, account_size: float = 100_000.0, regime: str = "NEUTRAL"):
        self.account_size = account_size
        self.regime = regime
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self.holdings = HoldingsManager()
        self.income_tracker = IncomeTracker()
        self.portfolio = CCPortfolioManager()
        self.journal = CCJournal()

    def optimize_calls(self, symbols: Optional[List[str]] = None) -> List[CCOpportunity]:
        if symbols is None:
            symbols = [h.symbol for h in self.holdings.all_holdings()]

        results = []
        for sym in symbols:
            holding = self.holdings.get_holding(sym)
            if holding is None:
                continue
            try:
                iv_rank = self._iv.iv_rank(sym)
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(30, 45))
                for exp, chain in chains.items():
                    opp = self._find_best_call(sym, chain, holding.cost_basis, iv_rank)
                    if opp:
                        results.append(opp)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _find_best_call(self, symbol: str, chain: ChainData,
                        cost_basis: float, iv_rank: float) -> Optional[CCOpportunity]:
        delta_range = self._delta_range(iv_rank)
        target_delta = REGIME_DELTA.get(self.regime, 0.30)

        best: Optional[OptionContract] = None
        best_dist = float("inf")
        for call in chain.calls:
            if call.strike <= cost_basis:
                continue
            d = call.delta_estimate
            if not (delta_range[0] <= d <= delta_range[1]):
                continue
            dist = abs(d - target_delta)
            if dist < best_dist:
                best_dist = dist
                best = call

        if best is None:
            return None

        annualized = (best.mid_price / cost_basis) * (365 / chain.dte) if chain.dte > 0 else 0
        score = annualized * 0.60 + (iv_rank / 100) * 0.40
        return CCOpportunity(
            symbol=symbol,
            cost_basis=cost_basis,
            strike=best.strike,
            expiration=best.expiration,
            dte=chain.dte,
            delta=best.delta_estimate,
            premium=best.mid_price,
            annualized_yield=round(annualized, 4),
            above_cost_basis=True,
            iv_rank=iv_rank,
            regime=self.regime,
            score=round(score, 4),
        )

    def _delta_range(self, iv_rank: float) -> tuple:
        if iv_rank > IV_HIGH_THRESHOLD:
            return (0.30, 0.40)
        elif iv_rank < IV_LOW_THRESHOLD:
            return (0.15, 0.25)
        else:
            regime_target = REGIME_DELTA.get(self.regime, 0.30)
            return (regime_target - 0.05, regime_target + 0.05)
