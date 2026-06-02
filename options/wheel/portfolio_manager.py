from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class WheelPosition:
    symbol: str
    phase: str  # "CSP" | "STOCK" | "CC"
    cost_basis: float
    shares: int = 0
    strike: float = 0.0
    expiration: str = ""
    premium_collected: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    current_premium: float = 0.0


class WheelPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, WheelPosition] = {}

    def add_position(self, pos: WheelPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[WheelPosition]:
        return self._positions.get(symbol)

    def update(self, symbol: str, current_price: float = 0.0,
               current_premium: float = 0.0) -> None:
        pos = self._positions.get(symbol)
        if pos:
            if current_price:
                pos.current_price = current_price
            if current_premium:
                pos.current_premium = current_premium

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def summary(self) -> List[dict]:
        rows = []
        for sym, pos in self._positions.items():
            unrealized = 0.0
            if pos.phase in ("STOCK", "CC") and pos.current_price and pos.cost_basis:
                unrealized = (pos.current_price - pos.cost_basis) * pos.shares
            rows.append({
                "symbol": sym,
                "phase": pos.phase,
                "cost_basis": pos.cost_basis,
                "shares": pos.shares,
                "strike": pos.strike,
                "premium_collected": pos.premium_collected,
                "unrealized_pnl": round(unrealized, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, WheelPosition]:
        return self._positions
