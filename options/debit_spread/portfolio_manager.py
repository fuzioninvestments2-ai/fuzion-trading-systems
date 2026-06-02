from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class DebitSpreadPosition:
    symbol: str
    direction: str
    long_strike: float
    short_strike: float
    expiration: str
    dte: int
    debit: float
    width: float
    max_profit: float
    entry_debit: float = 0.0
    current_value: float = 0.0
    contracts: int = 1


class DebitSpreadPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, DebitSpreadPosition] = {}

    def add_position(self, pos: DebitSpreadPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[DebitSpreadPosition]:
        return self._positions.get(symbol)

    def update(self, symbol: str, current_value: float = 0.0, dte: int = 0) -> None:
        pos = self._positions.get(symbol)
        if pos:
            if current_value:
                pos.current_value = current_value
            if dte:
                pos.dte = dte

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def summary(self) -> List[dict]:
        rows = []
        for sym, pos in self._positions.items():
            pnl = (pos.current_value - pos.entry_debit) * 100 * pos.contracts if pos.current_value else 0
            rows.append({
                "symbol": sym,
                "direction": pos.direction,
                "long_strike": pos.long_strike,
                "short_strike": pos.short_strike,
                "expiration": pos.expiration,
                "dte": pos.dte,
                "debit": pos.debit,
                "max_profit": pos.max_profit,
                "unrealized_pnl": round(pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, DebitSpreadPosition]:
        return self._positions
