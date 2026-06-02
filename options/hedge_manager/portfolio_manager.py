"""Portfolio manager para coberturas."""
from __future__ import annotations
from typing import List
from options.hedge_manager.hedge_engine import HedgePosition


class HedgePortfolioManager:
    def __init__(self):
        self.hedges: List[HedgePosition] = []

    def add(self, hedge: HedgePosition) -> None:
        self.hedges.append(hedge)

    def remove(self, symbol: str, hedge_type: str) -> None:
        for h in self.hedges:
            if h.symbol == symbol and h.hedge_type == hedge_type and h.status == "active":
                h.status = "expired"

    def active(self) -> List[HedgePosition]:
        return [h for h in self.hedges if h.status == "active"]

    def total_cost(self) -> float:
        return sum(h.cost for h in self.active())
