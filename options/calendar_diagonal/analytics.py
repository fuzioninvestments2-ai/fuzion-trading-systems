"""Analytics para calendar/diagonal spreads."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from options.calendar_diagonal.portfolio_manager import CalendarPosition


@dataclass
class CalendarAnalytics:
    total_positions: int
    open_positions: int
    total_pnl: float
    avg_pnl_per_trade: float
    win_rate: float
    avg_vega_exposure: float


def compute_analytics(positions: List[CalendarPosition]) -> CalendarAnalytics:
    closed = [p for p in positions if p.status == "closed"]
    open_pos = [p for p in positions if p.status == "open"]
    wins = [p for p in closed if p.pnl > 0]
    win_rate = len(wins) / max(len(closed), 1)
    total_pnl = sum(p.pnl for p in positions)
    avg_pnl = total_pnl / max(len(closed), 1)
    avg_vega = sum(p.spread.vega_exposure for p in open_pos) / max(len(open_pos), 1)
    return CalendarAnalytics(
        total_positions=len(positions),
        open_positions=len(open_pos),
        total_pnl=total_pnl,
        avg_pnl_per_trade=avg_pnl,
        win_rate=win_rate,
        avg_vega_exposure=avg_vega,
    )
