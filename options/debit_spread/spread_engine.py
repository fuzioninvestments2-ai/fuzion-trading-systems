from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer
from options.common.chain_models import ChainData, OptionContract
from .signal_engine import SignalEngine
from .signal_tracker import SignalTracker
from .portfolio_manager import DebitSpreadPortfolioManager
from .journal import DebitSpreadJournal


@dataclass
class DebitSpreadCandidate:
    symbol: str
    direction: str  # "bull_call" | "bear_put"
    long_strike: float
    short_strike: float
    expiration: str
    dte: int
    long_delta: float
    short_delta: float
    debit: float
    width: float
    max_profit: float
    debit_pct_of_max: float
    iv_rank: float
    setup_type: str
    score: float = 0.0


class DebitSpreadEngine:
    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._signal = SignalEngine()
        self._tracker = SignalTracker()
        self.portfolio = DebitSpreadPortfolioManager()
        self.journal = DebitSpreadJournal()

    def find_spreads(self, symbols: List[str]) -> List[DebitSpreadCandidate]:
        results = []
        for sym in symbols:
            try:
                iv_rank = self._iv.iv_rank(sym)
                if iv_rank >= 50:
                    continue
                signal = self._signal.get_signal(sym)
                if not self._tracker.is_setup_active(signal.setup_type):
                    continue
                direction = signal.direction
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(30, 60))
                for exp, chain in chains.items():
                    cand = self._build_spread(sym, chain, direction, iv_rank, signal.setup_type)
                    if cand:
                        results.append(cand)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _build_spread(self, symbol: str, chain: ChainData,
                      direction: str, iv_rank: float, setup_type: str) -> Optional[DebitSpreadCandidate]:
        if direction in ("BULL", "NEUTRAL"):
            contracts = chain.calls
            spread_dir = "bull_call"
        else:
            contracts = chain.puts
            spread_dir = "bear_put"

        long_c = self._find_delta_strike(contracts, 0.60)
        if long_c is None:
            return None
        short_c = self._find_delta_strike(contracts, 0.35)
        if short_c is None or short_c.strike == long_c.strike:
            return None

        if spread_dir == "bull_call":
            if short_c.strike <= long_c.strike:
                return None
            debit = long_c.mid_price - short_c.mid_price
            width = short_c.strike - long_c.strike
        else:
            if short_c.strike >= long_c.strike:
                return None
            debit = long_c.mid_price - short_c.mid_price
            width = long_c.strike - short_c.strike

        if debit <= 0 or width <= 0:
            return None
        max_profit = width - debit
        debit_pct = debit / max_profit if max_profit > 0 else 1.0
        if debit_pct > 0.50:
            return None

        score = (1 - debit_pct) * 0.50 + (long_c.delta_estimate - 0.50) * 2 * 0.30 + (1 - iv_rank / 100) * 0.20
        return DebitSpreadCandidate(
            symbol=symbol,
            direction=spread_dir,
            long_strike=long_c.strike,
            short_strike=short_c.strike,
            expiration=chain.expiration,
            dte=chain.dte,
            long_delta=long_c.delta_estimate,
            short_delta=short_c.delta_estimate,
            debit=round(debit, 2),
            width=round(width, 2),
            max_profit=round(max_profit, 2),
            debit_pct_of_max=round(debit_pct, 4),
            iv_rank=iv_rank,
            setup_type=setup_type,
            score=round(score, 4),
        )

    def _find_delta_strike(self, contracts: List[OptionContract],
                           target_delta: float) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            dist = abs(abs(c.delta_estimate) - target_delta)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    def manage_position(self, symbol: str, current_value: float,
                        entry_debit: float, dte: int) -> dict:
        if entry_debit <= 0:
            return {"action": "HOLD"}
        profit_pct = (current_value - entry_debit) / entry_debit
        if profit_pct >= 0.50:
            return {"action": "CLOSE", "reason": "50% profit target"}
        if dte <= 7:
            return {"action": "CLOSE", "reason": "DTE <= 7"}
        loss_pct = (entry_debit - current_value) / entry_debit
        if loss_pct >= 0.50:
            return {"action": "CLOSE", "reason": "50% max loss"}
        return {"action": "HOLD", "profit_pct": round(profit_pct, 4)}
