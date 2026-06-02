from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer, GreeksCalculator
from .wing_selector import WingSelector, CondorCandidate
from .adjustment_engine import AdjustmentEngine
from .portfolio_manager import CondorPortfolioManager
from .journal import CondorJournal


@dataclass
class CondorPosition:
    symbol: str
    put_short: float
    put_long: float
    call_short: float
    call_long: float
    expiration: str
    dte: int
    credit: float
    width: float
    max_loss: float
    pop: float
    adjustments: int = 0
    entry_credit: float = 0.0


class IronCondorEngine:
    MAX_ADJUSTMENTS = 2

    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._greeks = GreeksCalculator()
        self._wing_sel = WingSelector()
        self._adj_eng = AdjustmentEngine()
        self.portfolio = CondorPortfolioManager()
        self.journal = CondorJournal()

    def find_condors(self, symbols: List[str]) -> List[CondorCandidate]:
        results = []
        for sym in symbols:
            try:
                iv_rank = self._iv.iv_rank(sym)
                if iv_rank < 25:
                    continue
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(30, 45))
                for exp, chain in chains.items():
                    cand = self._wing_sel.build_condor(sym, chain, iv_rank, self.account_size)
                    if cand is None:
                        continue
                    if cand.credit < 0.33 * cand.width:
                        continue
                    if cand.max_loss > 0.02 * self.account_size:
                        continue
                    if cand.pop < 65:
                        continue
                    results.append(cand)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.credit / x.width if x.width else 0, reverse=True)

    def adjust_position(self, pos: CondorPosition, current_delta: float,
                        current_value: float) -> dict:
        if pos.adjustments >= self.MAX_ADJUSTMENTS:
            return {"action": "CLOSE", "reason": "Max adjustments reached"}

        profit_pct = (pos.entry_credit - current_value) / pos.entry_credit if pos.entry_credit > 0 else 0
        if profit_pct >= 0.50:
            return {"action": "CLOSE", "reason": "50% profit target"}

        if abs(current_delta) > 0.30:
            pos.adjustments += 1
            return {
                "action": "ROLL_WING",
                "reason": f"Delta {current_delta:.2f} exceeded 0.30",
                "adjustments_used": pos.adjustments,
            }

        return {"action": "HOLD", "reason": "Within parameters", "profit_pct": round(profit_pct, 4)}
