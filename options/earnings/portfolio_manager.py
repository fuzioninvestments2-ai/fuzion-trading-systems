"""Portfolio manager para earnings plays."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
from options.earnings.earnings_engine import EarningsSetup


@dataclass
class EarningsPosition:
    setup: EarningsSetup
    entry_date: str
    quantity: int
    pnl: float = 0.0
    status: str = "open"


class EarningsPortfolioManager:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.max_concurrent = self.config.get("max_concurrent", 3)
        self.positions: List[EarningsPosition] = []

    def can_add(self) -> bool:
        return len(self.open_positions()) < self.max_concurrent

    def add(self, setup: EarningsSetup, entry_date: str, qty: int) -> None:
        if not self.can_add():
            raise ValueError("Max concurrent earnings positions reached")
        self.positions.append(EarningsPosition(setup, entry_date, qty))

    def close(self, symbol: str) -> None:
        for p in self.positions:
            if p.setup.symbol == symbol and p.status == "open":
                p.status = "closed"

    def open_positions(self) -> List[EarningsPosition]:
        return [p for p in self.positions if p.status == "open"]

    def total_pnl(self) -> float:
        return sum(p.pnl for p in self.positions)
