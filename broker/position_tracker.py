"""Seguimiento de posiciones abiertas."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class TrackedPosition:
    symbol: str
    direction: str
    entry_price: float
    qty: float
    stop_loss: float
    take_profit: Optional[float]
    strategy_name: str
    open_time: pd.Timestamp = field(default_factory=pd.Timestamp.now)
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0


class PositionTracker:
    def __init__(self):
        self._positions: Dict[str, TrackedPosition] = {}

    def add_position(self, pos: TrackedPosition) -> None:
        self._positions[pos.symbol] = pos

    def remove_position(self, symbol: str) -> Optional[TrackedPosition]:
        return self._positions.pop(symbol, None)

    def update_price(self, symbol: str, current_price: float) -> None:
        if symbol not in self._positions:
            return
        p = self._positions[symbol]
        p.current_price = current_price
        if p.direction.upper() == "LONG":
            p.unrealized_pnl = (current_price - p.entry_price) * p.qty
        else:
            p.unrealized_pnl = (p.entry_price - current_price) * p.qty
        p.unrealized_pnl_pct = p.unrealized_pnl / (p.entry_price * p.qty)

    def check_stop_loss(self, symbol: str) -> bool:
        p = self._positions.get(symbol)
        if not p:
            return False
        if p.direction.upper() == "LONG":
            return p.current_price <= p.stop_loss
        return p.current_price >= p.stop_loss

    def check_take_profit(self, symbol: str) -> bool:
        p = self._positions.get(symbol)
        if not p or not p.take_profit:
            return False
        if p.direction.upper() == "LONG":
            return p.current_price >= p.take_profit
        return p.current_price <= p.take_profit

    def get_all(self) -> List[TrackedPosition]:
        return list(self._positions.values())

    def get(self, symbol: str) -> Optional[TrackedPosition]:
        return self._positions.get(symbol)

    def summary(self) -> dict:
        positions = self.get_all()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        return {
            "count": len(positions),
            "symbols": [p.symbol for p in positions],
            "total_unrealized_pnl": round(total_pnl, 2),
        }
