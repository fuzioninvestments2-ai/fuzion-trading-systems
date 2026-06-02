from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional
from options.common.chain_models import OptionContract


@dataclass
class MoveEstimate:
    symbol: str
    implied_move: float
    implied_move_pct: float
    historical_avg: float
    historical_max: float
    consensus_move: float
    consensus_move_pct: float
    straddle_priced_at: float
    move_exceeds_straddle: bool
    confidence: float


class MoveEstimator:
    def estimate_move(self, symbol: str, atm_call: OptionContract,
                      atm_put: OptionContract, underlying_price: float,
                      historical_moves: Optional[List[float]] = None) -> MoveEstimate:
        straddle = atm_call.mid_price + atm_put.mid_price
        implied_pct = straddle / underlying_price if underlying_price > 0 else 0

        hist_moves = historical_moves or []
        hist_avg = sum(hist_moves) / len(hist_moves) if hist_moves else implied_pct
        hist_max = max(hist_moves) if hist_moves else implied_pct

        consensus = (implied_pct + hist_avg) / 2
        consensus_dollar = consensus * underlying_price

        move_exceeds = consensus_dollar > straddle
        confidence = min(1.0, len(hist_moves) / 8) * 0.50 + 0.50

        return MoveEstimate(
            symbol=symbol,
            implied_move=round(straddle, 2),
            implied_move_pct=round(implied_pct, 4),
            historical_avg=round(hist_avg, 4),
            historical_max=round(hist_max, 4),
            consensus_move=round(consensus_dollar, 2),
            consensus_move_pct=round(consensus, 4),
            straddle_priced_at=round(straddle, 2),
            move_exceeds_straddle=move_exceeds,
            confidence=round(confidence, 4),
        )

    def iv_expansion_score(self, current_iv: float, historical_avg_iv: float,
                           days_to_earnings: int) -> float:
        if historical_avg_iv <= 0:
            return 0.0
        premium = current_iv / historical_avg_iv - 1
        days_factor = max(0, 1 - days_to_earnings / 30)
        return round(premium * days_factor, 4)
