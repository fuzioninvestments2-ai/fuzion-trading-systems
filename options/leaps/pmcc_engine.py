from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer
from options.common.chain_models import ChainData, OptionContract
from .roll_manager import RollManager
from .portfolio_manager import LEAPSPortfolioManager
from .journal import LEAPSJournal


@dataclass
class PMCCCandidate:
    symbol: str
    long_strike: float
    long_expiration: str
    long_dte: int
    long_delta: float
    long_premium: float
    short_strike: float
    short_expiration: str
    short_dte: int
    short_delta: float
    short_premium: float
    net_debit: float
    width: float
    max_profit: float
    debit_pct_of_width: float
    score: float = 0.0


class PMCCEngine:
    MAX_DEBIT_PCT = 0.75

    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._roll_mgr = RollManager()
        self.portfolio = LEAPSPortfolioManager()
        self.journal = LEAPSJournal()

    def find_pmcc(self, symbols: List[str]) -> List[PMCCCandidate]:
        results = []
        for sym in symbols:
            try:
                long_chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(365, 730))
                short_chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(25, 45))
                for lexp, lchain in long_chains.items():
                    if lchain.dte < 365:
                        continue
                    long_call = self._find_long(lchain)
                    if long_call is None:
                        continue
                    for sexp, schain in short_chains.items():
                        short_call = self._find_short(schain, long_call.strike)
                        if short_call is None:
                            continue
                        cand = self._build_pmcc(sym, lchain, long_call, schain, short_call)
                        if cand:
                            results.append(cand)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _find_long(self, chain: ChainData) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in chain.calls:
            if not (0.70 <= c.delta_estimate <= 0.80):
                continue
            dist = abs(c.delta_estimate - 0.75)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    def _find_short(self, chain: ChainData, long_strike: float) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in chain.calls:
            if c.strike <= long_strike:
                continue
            if not (0.25 <= c.delta_estimate <= 0.40):
                continue
            dist = abs(c.delta_estimate - 0.30)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    def _build_pmcc(self, symbol: str, lchain: ChainData, long_call: OptionContract,
                    schain: ChainData, short_call: OptionContract) -> Optional[PMCCCandidate]:
        net_debit = long_call.mid_price - short_call.mid_price
        width = short_call.strike - long_call.strike
        if width <= 0 or net_debit <= 0:
            return None
        debit_pct = net_debit / width
        if debit_pct > self.MAX_DEBIT_PCT:
            return None
        max_profit = width - net_debit
        score = (1 - debit_pct) * 0.60 + long_call.delta_estimate * 0.40
        return PMCCCandidate(
            symbol=symbol,
            long_strike=long_call.strike,
            long_expiration=long_call.expiration,
            long_dte=lchain.dte,
            long_delta=long_call.delta_estimate,
            long_premium=long_call.mid_price,
            short_strike=short_call.strike,
            short_expiration=short_call.expiration,
            short_dte=schain.dte,
            short_delta=short_call.delta_estimate,
            short_premium=short_call.mid_price,
            net_debit=round(net_debit, 2),
            width=round(width, 2),
            max_profit=round(max_profit, 2),
            debit_pct_of_width=round(debit_pct, 4),
            score=round(score, 4),
        )
