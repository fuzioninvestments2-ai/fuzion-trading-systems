"""Portfolio manager para calendar/diagonal spreads."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict
from options.calendar_diagonal.calendar_engine import CalendarSpread


@dataclass
class CalendarPosition:
    spread: CalendarSpread
    entry_price: float
    quantity: int
    open_date: str
    pnl: float = 0.0
    status: str = "open"


class CalendarPortfolioManager:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.positions: List[CalendarPosition] = []

    def add_position(self, spread: CalendarSpread, entry_price: float, qty: int, date: str) -> None:
        self.positions.append(CalendarPosition(spread, entry_price, qty, date))

    def update_pnl(self, symbol: str, current_value: float) -> None:
        for p in self.positions:
            if p.spread.symbol == symbol and p.status == "open":
                p.pnl = (current_value - p.entry_price) * p.quantity

    def close_position(self, symbol: str) -> None:
        for p in self.positions:
            if p.spread.symbol == symbol and p.status == "open":
                p.status = "closed"

    def open_positions(self) -> List[CalendarPosition]:
        return [p for p in self.positions if p.status == "open"]

    def total_pnl(self) -> float:
        return sum(p.pnl for p in self.positions)
