from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StranglePosition:
    symbol: str
    put_strike: float
    call_strike: float
    expiration: str
    dte: int
    total_credit: float
    entry_credit: float = 0.0
    current_value: float = 0.0
    underlying_price: float = 0.0
    contracts: int = 1
    hedge_in_place: bool = False


class StranglePortfolioManager:
    def __init__(self):
        self._positions: Dict[str, StranglePosition] = {}

    def add_position(self, pos: StranglePosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[StranglePosition]:
        return self._positions.get(symbol)

    def update(self, symbol: str, current_value: float = 0.0,
               underlying_price: float = 0.0, dte: int = 0) -> None:
        pos = self._positions.get(symbol)
        if pos:
            if current_value:
                pos.current_value = current_value
            if underlying_price:
                pos.underlying_price = underlying_price
            if dte:
                pos.dte = dte

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def total_notional(self) -> float:
        return sum(pos.put_strike * pos.contracts * 100 for pos in self._positions.values())

    def summary(self) -> List[dict]:
        rows = []
        for sym, pos in self._positions.items():
            pnl = (pos.entry_credit - pos.current_value) * 100 * pos.contracts if pos.current_value else 0
            rows.append({
                "symbol": sym,
                "put_strike": pos.put_strike,
                "call_strike": pos.call_strike,
                "expiration": pos.expiration,
                "dte": pos.dte,
                "total_credit": pos.total_credit,
                "hedge_in_place": pos.hedge_in_place,
                "unrealized_pnl": round(pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, StranglePosition]:
        return self._positions
