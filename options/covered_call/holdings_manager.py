from __future__ import annotations
import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Holding:
    symbol: str
    shares: int
    cost_basis: float
    purchase_date: str = ""
    notes: str = ""


class HoldingsManager:
    def __init__(self):
        self._holdings: Dict[str, Holding] = {}

    def add_holding(self, holding: Holding) -> None:
        self._holdings[holding.symbol] = holding

    def get_holding(self, symbol: str) -> Optional[Holding]:
        return self._holdings.get(symbol)

    def update_cost_basis(self, symbol: str, new_cost_basis: float) -> None:
        h = self._holdings.get(symbol)
        if h:
            h.cost_basis = new_cost_basis

    def reduce_cost_basis(self, symbol: str, premium_per_share: float) -> None:
        h = self._holdings.get(symbol)
        if h and h.cost_basis > 0:
            h.cost_basis = max(0.0, h.cost_basis - premium_per_share)

    def all_holdings(self) -> List[Holding]:
        return list(self._holdings.values())

    def load_from_csv(self, filepath: str) -> None:
        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                h = Holding(
                    symbol=row["symbol"],
                    shares=int(row.get("shares", 100)),
                    cost_basis=float(row["cost_basis"]),
                    purchase_date=row.get("purchase_date", ""),
                    notes=row.get("notes", ""),
                )
                self._holdings[h.symbol] = h

    def remove_holding(self, symbol: str) -> None:
        self._holdings.pop(symbol, None)

    def summary(self) -> List[dict]:
        return [
            {
                "symbol": h.symbol,
                "shares": h.shares,
                "cost_basis": h.cost_basis,
                "purchase_date": h.purchase_date,
            }
            for h in self._holdings.values()
        ]
