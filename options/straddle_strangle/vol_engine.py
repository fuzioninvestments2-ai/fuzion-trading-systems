from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from options.common import OptionsChainFetcher, IVAnalyzer
from options.common.chain_models import ChainData, OptionContract
from .catalyst_scanner import CatalystScanner, Catalyst
from .portfolio_manager import LongVolPortfolioManager
from .journal import LongVolJournal


@dataclass
class LongVolPlay:
    symbol: str
    structure: str  # "straddle" | "strangle"
    call_strike: float
    put_strike: float
    expiration: str
    dte: int
    call_premium: float
    put_premium: float
    total_debit: float
    straddle_price: float
    expected_move: float
    move_exceeds_cost: bool
    iv_rank: float
    catalyst: str
    score: float = 0.0


class LongVolEngine:
    MAX_IV_RANK = 20

    def __init__(self, account_size: float = 100_000.0):
        self.account_size = account_size
        self._fetcher = OptionsChainFetcher()
        self._iv = IVAnalyzer()
        self._catalyst = CatalystScanner()
        self.portfolio = LongVolPortfolioManager()
        self.journal = LongVolJournal()

    def find_vol_plays(self, symbols: List[str]) -> List[LongVolPlay]:
        results = []
        for sym in symbols:
            try:
                iv_rank = self._iv.iv_rank(sym)
                if iv_rank > self.MAX_IV_RANK:
                    continue
                catalysts = self._catalyst.get_catalysts(sym)
                if not catalysts:
                    continue
                chains = self._fetcher.get_multi_expiry_chain(sym, dte_range=(20, 45))
                for exp, chain in chains.items():
                    play = self._build_play(sym, chain, iv_rank, catalysts[0])
                    if play:
                        results.append(play)
            except Exception:
                continue
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _build_play(self, symbol: str, chain: ChainData,
                    iv_rank: float, catalyst: Catalyst) -> Optional[LongVolPlay]:
        S = chain.underlying_price
        atm_call = self._find_atm(chain.calls, S)
        atm_put = self._find_atm(chain.puts, S)
        if atm_call is None or atm_put is None:
            return None

        straddle_price = atm_call.mid_price + atm_put.mid_price
        iv = atm_call.implied_volatility or 0.25
        import math
        expected_move = S * iv * math.sqrt(chain.dte / 365) if chain.dte > 0 else 0

        if expected_move <= straddle_price:
            return None

        score = (expected_move / straddle_price - 1) * 0.60 + (1 - iv_rank / 100) * 0.40
        return LongVolPlay(
            symbol=symbol,
            structure="straddle",
            call_strike=atm_call.strike,
            put_strike=atm_put.strike,
            expiration=chain.expiration,
            dte=chain.dte,
            call_premium=atm_call.mid_price,
            put_premium=atm_put.mid_price,
            total_debit=round(straddle_price, 2),
            straddle_price=round(straddle_price, 2),
            expected_move=round(expected_move, 2),
            move_exceeds_cost=True,
            iv_rank=iv_rank,
            catalyst=catalyst.event_type,
            score=round(score, 4),
        )

    def _find_atm(self, contracts: List[OptionContract],
                  underlying_price: float) -> Optional[OptionContract]:
        best = None
        best_dist = float("inf")
        for c in contracts:
            dist = abs(c.strike - underlying_price)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best
