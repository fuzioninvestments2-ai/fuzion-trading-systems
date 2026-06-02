from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class LongVolPosition:
    symbol: str
    structure: str
    call_strike: float
    put_strike: float
    expiration: str
    dte: int
    total_debit: float
    catalyst: str
    contracts: int = 1
    current_value: float = 0.0
    entry_debit: float = 0.0


class LongVolPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, LongVolPosition] = {}

    def add_position(self, pos: LongVolPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[LongVolPosition]:
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
                "structure": pos.structure,
                "call_strike": pos.call_strike,
                "put_strike": pos.put_strike,
                "expiration": pos.expiration,
                "dte": pos.dte,
                "total_debit": pos.total_debit,
                "catalyst": pos.catalyst,
                "unrealized_pnl": round(pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, LongVolPosition]:
        return self._positions
