from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer
from options.common.chain_models import ChainData
from .setup_scanner import SetupScanner, MomentumSetup
from .entry_timer import EntryTimer
from .portfolio_manager import MomentumPortfolioManager
from .journal import MomentumJournal


@dataclass
class MomentumPlay:
    symbol: str
    setup_type: str  # "breakout" | "gap" | "squeeze" | "vwap_reclaim"
    direction: str
    option_type: str  # "call" | "put"
    strike: float
    expiration: str
    dte: int
    delta: float
    debit: float
    max_loss: float
    confidence: float
    entry_timing: str
    score: float = 0.0


class MomentumEngine:
    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._scanner = SetupScanner()
        self._timer = EntryTimer()
        self.portfolio = MomentumPortfolioManager()
        self.journal = MomentumJournal()

    def scan_setups(self, symbols: List[str],
                    market_data: Optional[dict] = None) -> List[MomentumPlay]:
        results = []
        for sym in symbols:
            try:
                setups = self._scanner.scan(sym, market_data.get(sym) if market_data else None)
                for setup in setups:
                    iv_rank = self._iv.iv_rank(sym)
                    if iv_rank >= 50:
                        continue
                    chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(15, 45))
                    for exp, chain in chains.items():
                        play = self._build_play(sym, chain, setup)
                        if play:
                            results.append(play)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _build_play(self, symbol: str, chain: ChainData,
                    setup: MomentumSetup) -> Optional[MomentumPlay]:
        timing = self._timer.get_timing(setup)
        if timing.signal == "WAIT":
            return None

        if setup.direction == "BULL":
            contracts = chain.calls
            option_type = "call"
        else:
            contracts = chain.puts
            option_type = "put"

        target = next((c for c in contracts
                       if 0.55 <= abs(c.delta_estimate) <= 0.75), None)
        if target is None:
            return None

        debit = target.mid_price
        max_loss = debit * 100

        return MomentumPlay(
            symbol=symbol,
            setup_type=setup.setup_type,
            direction=setup.direction,
            option_type=option_type,
            strike=target.strike,
            expiration=target.expiration,
            dte=chain.dte,
            delta=target.delta_estimate,
            debit=round(debit, 2),
            max_loss=round(max_loss, 2),
            confidence=setup.confidence,
            entry_timing=timing.signal,
            score=round(setup.confidence * (1 - debit / (target.strike or 1)) * 10, 4),
        )
