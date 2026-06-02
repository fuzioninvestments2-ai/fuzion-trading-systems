"""Analytics de earnings plays."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from options.earnings.portfolio_manager import EarningsPosition


@dataclass
class EarningsAnalytics:
    total_plays: int
    wins: int
    losses: int
    win_rate: float
    avg_pnl: float
    by_strategy: dict


def compute_analytics(positions: List[EarningsPosition]) -> EarningsAnalytics:
    closed = [p for p in positions if p.status == "closed"]
    wins = [p for p in closed if p.pnl > 0]
    by_strategy: dict = {}
    for p in closed:
        s = p.setup.strategy
        by_strategy.setdefault(s, {"count": 0, "pnl": 0.0})
        by_strategy[s]["count"] += 1
        by_strategy[s]["pnl"] += p.pnl
    return EarningsAnalytics(
        total_plays=len(closed),
        wins=len(wins),
        losses=len(closed) - len(wins),
        win_rate=len(wins) / max(len(closed), 1),
        avg_pnl=sum(p.pnl for p in closed) / max(len(closed), 1),
        by_strategy=by_strategy,
    )
