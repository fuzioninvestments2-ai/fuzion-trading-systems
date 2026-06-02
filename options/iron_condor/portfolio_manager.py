from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CondorPosition:
    symbol: str
    put_short: float
    put_long: float
    call_short: float
    call_long: float
    expiration: str
    dte: int
    credit: float
    width: float
    max_loss: float
    pop: float
    entry_credit: float = 0.0
    adjustments: int = 0
    current_value: float = 0.0


class CondorPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, CondorPosition] = {}

    def add_position(self, pos: CondorPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[CondorPosition]:
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
            unrealized_pnl = (pos.entry_credit - pos.current_value) * 100 if pos.current_value else 0
            rows.append({
                "symbol": sym,
                "expiration": pos.expiration,
                "dte": pos.dte,
                "credit": pos.credit,
                "max_loss": pos.max_loss,
                "pop": pos.pop,
                "adjustments": pos.adjustments,
                "unrealized_pnl": round(unrealized_pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, CondorPosition]:
        return self._positions
