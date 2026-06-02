from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SpreadPosition:
    symbol: str
    direction: str
    short_strike: float
    long_strike: float
    expiration: str
    dte: int
    credit: float
    width: float
    entry_credit: float = 0.0
    current_value: float = 0.0
    contracts: int = 1


class CreditSpreadPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, SpreadPosition] = {}

    def add_position(self, pos: SpreadPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[SpreadPosition]:
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
            pnl = (pos.entry_credit - pos.current_value) * 100 * pos.contracts if pos.current_value else 0
            rows.append({
                "symbol": sym,
                "direction": pos.direction,
                "short_strike": pos.short_strike,
                "long_strike": pos.long_strike,
                "expiration": pos.expiration,
                "dte": pos.dte,
                "credit": pos.credit,
                "unrealized_pnl": round(pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, SpreadPosition]:
        return self._positions
