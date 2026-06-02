from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer, GreeksCalculator, OptionsScreener
from .csp_selector import CSPSelector, CSPCandidate
from .cc_selector import CCSelector, CCCandidate
from .assignment_manager import AssignmentManager
from .portfolio_manager import WheelPortfolioManager
from .journal import WheelJournal


@dataclass
class WheelPosition:
    symbol: str
    phase: str  # "CSP" | "STOCK" | "CC"
    cost_basis: float
    shares: int = 0
    strike: float = 0.0
    expiration: str = ""
    premium_collected: float = 0.0
    entry_price: float = 0.0


class WheelEngine:
    def __init__(self, account_size: float = 100_000.0, regime: str = "NEUTRAL"):
        self.account_size = account_size
        self.regime = regime
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._greeks = GreeksCalculator()
        self._screener = OptionsScreener()
        self._csp_sel = CSPSelector()
        self._cc_sel = CCSelector()
        self._assign_mgr = AssignmentManager()
        self.portfolio = WheelPortfolioManager()
        self.journal = WheelJournal()

    def scan_csp_candidates(self, symbols: List[str]) -> List[CSPCandidate]:
        candidates = []
        for sym in symbols:
            try:
                iv_rank = self._iv.iv_rank(sym)
                if iv_rank < 30:
                    continue
                underlying = self._fetcher.get_underlying_price(sym)
                if underlying.avg_volume < 100:
                    continue
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(30, 45))
                for exp, chain in chains.items():
                    for put in chain.puts:
                        if put.volume < 100 or put.open_interest < 500:
                            continue
                        if put.delta_estimate < -0.35 or put.delta_estimate > -0.25:
                            continue
                        if put.mid_price > 0:
                            spread_pct = put.bid_ask_spread / put.mid_price
                            if spread_pct > 0.10:
                                continue
                        cand = self._csp_sel.build_candidate(sym, chain, put, iv_rank, underlying)
                        if cand:
                            candidates.append(cand)
            except Exception:
                continue
        return self._csp_sel.rank(candidates)

    def scan_cc_candidates(self, symbols: List[str]) -> List[CCCandidate]:
        candidates = []
        for sym in symbols:
            pos = self.portfolio.get_position(sym)
            if pos is None or pos.phase not in ("STOCK", "CC"):
                continue
            try:
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(30, 45))
                iv_rank = self._iv.iv_rank(sym)
                for exp, chain in chains.items():
                    cand = self._cc_sel.build_candidate(
                        sym, chain, pos.cost_basis, iv_rank, self.regime
                    )
                    if cand:
                        candidates.append(cand)
            except Exception:
                continue
        return candidates

    def manage_position(self, symbol: str, current_price: float,
                        current_premium: float, entry_premium: float,
                        dte: int, delta: float) -> dict:
        action = "HOLD"
        reason = ""

        profit_pct = (entry_premium - current_premium) / entry_premium if entry_premium > 0 else 0
        if profit_pct >= 0.50:
            action = "CLOSE"
            reason = "50% profit target reached"
        elif dte <= 7:
            action = "ROLL"
            reason = "DTE <= 7, roll forward"
        elif abs(delta) > 0.35:
            pos = self.portfolio.get_position(symbol)
            if pos and pos.phase == "CSP":
                underlying_move = (pos.entry_price - current_price) / pos.entry_price if pos.entry_price > 0 else 0
                if underlying_move > 0.10:
                    action = "DEFEND"
                    reason = "Underlying dropped >10% from entry"

        return {"symbol": symbol, "action": action, "reason": reason,
                "profit_pct": round(profit_pct, 4), "dte": dte, "delta": delta}
