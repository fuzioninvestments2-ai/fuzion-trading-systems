from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer, GreeksCalculator
from options.common.chain_models import ChainData, OptionContract
from .defense_engine import DefenseEngine
from .portfolio_manager import StranglePortfolioManager
from .journal import StrangleJournal


@dataclass
class StrangleCandidate:
    symbol: str
    put_strike: float
    call_strike: float
    expiration: str
    dte: int
    put_delta: float
    call_delta: float
    put_premium: float
    call_premium: float
    total_credit: float
    iv_rank: float
    breakeven_lower: float
    breakeven_upper: float
    score: float = 0.0


class ShortStrangleEngine:
    ACCOUNT_MINIMUM = 50_000.0
    MAX_PORTFOLIO_STRANGLES = 0.30
    MANDATORY_HEDGE = True
    TARGET_DTE = 45
    TARGET_DELTA = 0.16

    def __init__(self, account_size: float = 100_000.0, regime: str = "NEUTRAL"):
        if account_size < self.ACCOUNT_MINIMUM:
            raise ValueError(f"Account minimum for short strangles is ${self.ACCOUNT_MINIMUM:,.0f}")
        self.account_size = account_size
        self.regime = regime
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._greeks = GreeksCalculator()
        self.defense = DefenseEngine()
        self.portfolio = StranglePortfolioManager()
        self.journal = StrangleJournal()

    def find_strangles(self, symbols: List[str]) -> List[StrangleCandidate]:
        if self.regime not in ("NEUTRAL", "BULL"):
            return []

        max_notional = self.account_size * self.MAX_PORTFOLIO_STRANGLES
        current_notional = self.portfolio.total_notional()
        if current_notional >= max_notional:
            return []

        results = []
        for sym in symbols:
            try:
                iv_rank = self._iv.iv_rank(sym)
                if iv_rank < 40:
                    continue
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(40, 50))
                for exp, chain in chains.items():
                    cand = self._build_strangle(sym, chain, iv_rank)
                    if cand:
                        results.append(cand)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _build_strangle(self, symbol: str, chain: ChainData,
                        iv_rank: float) -> Optional[StrangleCandidate]:
        S = chain.underlying_price
        put_short = self._find_delta_strike(chain.puts, -self.TARGET_DELTA, "put")
        call_short = self._find_delta_strike(chain.calls, self.TARGET_DELTA, "call")
        if put_short is None or call_short is None:
            return None

        total_credit = put_short.mid_price + call_short.mid_price
        breakeven_lower = put_short.strike - total_credit
        breakeven_upper = call_short.strike + total_credit

        iv = chain.calls[0].implied_volatility if chain.calls else 0.30
        daily_sd = S * iv / math.sqrt(252)
        total_sd = daily_sd * math.sqrt(chain.dte or 45)

        score = (iv_rank / 100) * 0.50 + (total_credit / S) * 500 * 0.50
        return StrangleCandidate(
            symbol=symbol,
            put_strike=put_short.strike,
            call_strike=call_short.strike,
            expiration=chain.expiration,
            dte=chain.dte,
            put_delta=put_short.delta_estimate,
            call_delta=call_short.delta_estimate,
            put_premium=put_short.mid_price,
            call_premium=call_short.mid_price,
            total_credit=round(total_credit, 2),
            iv_rank=iv_rank,
            breakeven_lower=round(breakeven_lower, 2),
            breakeven_upper=round(breakeven_upper, 2),
            score=round(score, 4),
        )

    def _find_delta_strike(self, contracts: List[OptionContract],
                           target_delta: float, option_type: str) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            d = abs(c.delta_estimate)
            dist = abs(d - abs(target_delta))
            if dist < best_dist:
                best_dist = dist
                best = c
        return best
