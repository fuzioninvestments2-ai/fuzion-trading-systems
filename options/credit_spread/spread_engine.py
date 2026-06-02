from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer, GreeksCalculator
from options.common.chain_models import ChainData, OptionContract
from .signal_engine import SignalEngine
from .portfolio_manager import CreditSpreadPortfolioManager
from .journal import CreditSpreadJournal


@dataclass
class SpreadCandidate:
    symbol: str
    direction: str  # "bull_put" | "bear_call"
    short_strike: float
    long_strike: float
    expiration: str
    dte: int
    short_delta: float
    credit: float
    width: float
    credit_pct: float
    pop: float
    iv_rank: float
    score: float = 0.0


class CreditSpreadEngine:
    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._greeks = GreeksCalculator()
        self._signal = SignalEngine()
        self.portfolio = CreditSpreadPortfolioManager()
        self.journal = CreditSpreadJournal()

    def find_spreads(self, symbols: List[str]) -> List[SpreadCandidate]:
        results = []
        for sym in symbols:
            try:
                iv_rank = self._iv.iv_rank(sym)
                if iv_rank < 20:
                    continue
                direction = self._signal.get_direction(sym)
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(30, 45))
                for exp, chain in chains.items():
                    cand = self._build_spread(sym, chain, direction, iv_rank)
                    if cand:
                        results.append(cand)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _build_spread(self, symbol: str, chain: ChainData,
                      direction: str, iv_rank: float) -> Optional[SpreadCandidate]:
        S = chain.underlying_price
        iv = chain.calls[0].implied_volatility if chain.calls else 0.25
        daily_sd = S * iv / math.sqrt(252)
        total_sd = daily_sd * math.sqrt(chain.dte or 30)

        if direction in ("BULL", "NEUTRAL"):
            contracts = chain.puts
            option_type = "put"
        else:
            contracts = chain.calls
            option_type = "call"

        short = self._find_delta_strike(contracts, 0.30, option_type)
        if short is None:
            return None

        target_long_strike = short.strike - 5 if option_type == "put" else short.strike + 5
        long = self._find_nearest_strike(contracts, target_long_strike)
        if long is None or long.strike == short.strike:
            return None

        if option_type == "put":
            credit = short.mid_price - long.mid_price
            width = short.strike - long.strike
            spread_dir = "bull_put"
        else:
            credit = short.mid_price - long.mid_price
            width = long.strike - short.strike
            spread_dir = "bear_call"

        if width < 2 or width > 5:
            return None
        if credit <= 0:
            return None
        credit_pct = credit / width
        if credit_pct < 0.33:
            return None

        from scipy.stats import norm
        if option_type == "put":
            distance = (S - short.strike) / total_sd if total_sd > 0 else 0
            pop = norm.cdf(distance) * 100
        else:
            distance = (short.strike - S) / total_sd if total_sd > 0 else 0
            pop = norm.cdf(distance) * 100

        if pop < 60:
            return None

        score = credit_pct * 0.40 + (pop / 100) * 0.40 + (iv_rank / 100) * 0.20
        return SpreadCandidate(
            symbol=symbol,
            direction=spread_dir,
            short_strike=short.strike,
            long_strike=long.strike,
            expiration=chain.expiration,
            dte=chain.dte,
            short_delta=short.delta_estimate,
            credit=round(credit, 2),
            width=round(width, 2),
            credit_pct=round(credit_pct, 4),
            pop=round(pop, 2),
            iv_rank=iv_rank,
            score=round(score, 4),
        )

    def _find_delta_strike(self, contracts: List[OptionContract],
                           target_delta: float, option_type: str) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            d = abs(c.delta_estimate)
            if not (0.25 <= d <= 0.35):
                continue
            dist = abs(d - target_delta)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    def _find_nearest_strike(self, contracts: List[OptionContract],
                              target: float) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            dist = abs(c.strike - target)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    def manage_position(self, symbol: str, current_value: float,
                        entry_credit: float, dte: int) -> dict:
        if entry_credit <= 0:
            return {"action": "HOLD", "reason": "No entry credit"}
        profit_pct = (entry_credit - current_value) / entry_credit
        if profit_pct >= 0.50:
            return {"action": "CLOSE", "reason": "50% profit target"}
        if dte <= 7:
            return {"action": "CLOSE", "reason": "DTE <= 7"}
        return {"action": "HOLD", "profit_pct": round(profit_pct, 4)}
