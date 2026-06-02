from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CCPosition:
    symbol: str
    cost_basis: float
    strike: float
    expiration: str
    dte: int
    premium: float
    contracts: int = 1
    current_call_value: float = 0.0
    entry_premium: float = 0.0


class CCPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, CCPosition] = {}

    def add_position(self, pos: CCPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[CCPosition]:
        return self._positions.get(symbol)

    def update(self, symbol: str, current_call_value: float = 0.0, dte: int = 0) -> None:
        pos = self._positions.get(symbol)
        if pos:
            if current_call_value:
                pos.current_call_value = current_call_value
            if dte:
                pos.dte = dte

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def summary(self) -> List[dict]:
        rows = []
        for sym, pos in self._positions.items():
            pnl = (pos.entry_premium - pos.current_call_value) * 100 * pos.contracts if pos.current_call_value else 0
            rows.append({
                "symbol": sym,
                "cost_basis": pos.cost_basis,
                "strike": pos.strike,
                "expiration": pos.expiration,
                "dte": pos.dte,
                "premium": pos.premium,
                "above_cost_basis": pos.strike > pos.cost_basis,
                "unrealized_pnl": round(pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, CCPosition]:
        return self._positions
