from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from options.common.chain_models import OptionContract


@dataclass
class EarningsIVProfile:
    symbol: str
    current_iv: float
    iv_rank: float
    implied_move: float
    implied_move_pct: float
    historical_moves: List[float]
    avg_historical_move: float
    max_historical_move: float
    iv_premium: float


class EarningsIVAnalyzer:
    def __init__(self):
        self._historical_moves: Dict[str, List[float]] = {}

    def implied_move(self, atm_call: OptionContract, atm_put: OptionContract,
                     underlying_price: float) -> float:
        straddle = atm_call.mid_price + atm_put.mid_price
        return straddle

    def implied_move_pct(self, atm_call: OptionContract, atm_put: OptionContract,
                          underlying_price: float) -> float:
        move = self.implied_move(atm_call, atm_put, underlying_price)
        return move / underlying_price if underlying_price > 0 else 0.0

    def historical_move(self, symbol: str, last_n: int = 8) -> List[float]:
        moves = self._historical_moves.get(symbol, [])
        return moves[-last_n:]

    def register_historical_move(self, symbol: str, move_pct: float) -> None:
        if symbol not in self._historical_moves:
            self._historical_moves[symbol] = []
        self._historical_moves[symbol].append(move_pct)

    def analyze(self, symbol: str, atm_call: OptionContract, atm_put: OptionContract,
                underlying_price: float, iv_rank: float) -> EarningsIVProfile:
        imp_move = self.implied_move(atm_call, atm_put, underlying_price)
        imp_move_pct = self.implied_move_pct(atm_call, atm_put, underlying_price)
        hist_moves = self.historical_move(symbol, 8)
        avg_hist = sum(hist_moves) / len(hist_moves) if hist_moves else 0.0
        max_hist = max(hist_moves) if hist_moves else 0.0
        iv_premium = (imp_move_pct / avg_hist - 1) if avg_hist > 0 else 0.0
        current_iv = atm_call.implied_volatility

        return EarningsIVProfile(
            symbol=symbol,
            current_iv=current_iv,
            iv_rank=iv_rank,
            implied_move=round(imp_move, 2),
            implied_move_pct=round(imp_move_pct, 4),
            historical_moves=hist_moves,
            avg_historical_move=round(avg_hist, 4),
            max_historical_move=round(max_hist, 4),
            iv_premium=round(iv_premium, 4),
        )
