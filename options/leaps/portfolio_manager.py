from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LEAPSPosition:
    symbol: str
    position_type: str  # "LEAPS" | "PMCC"
    long_strike: float
    long_expiration: str
    long_dte: int
    long_premium: float
    short_strike: float = 0.0
    short_expiration: str = ""
    short_dte: int = 0
    short_premium: float = 0.0
    net_debit: float = 0.0
    contracts: int = 1
    current_long_value: float = 0.0
    current_short_value: float = 0.0
    premium_collected: float = 0.0


class LEAPSPortfolioManager:
    def __init__(self):
        self._positions: Dict[str, LEAPSPosition] = {}

    def add_position(self, pos: LEAPSPosition) -> None:
        self._positions[pos.symbol] = pos

    def get_position(self, symbol: str) -> Optional[LEAPSPosition]:
        return self._positions.get(symbol)

    def update(self, symbol: str, current_long_value: float = 0.0,
               current_short_value: float = 0.0) -> None:
        pos = self._positions.get(symbol)
        if pos:
            if current_long_value:
                pos.current_long_value = current_long_value
            if current_short_value:
                pos.current_short_value = current_short_value

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def summary(self) -> List[dict]:
        rows = []
        for sym, pos in self._positions.items():
            net_value = pos.current_long_value - pos.current_short_value if pos.current_long_value else 0
            pnl = (net_value - pos.net_debit) * 100 * pos.contracts if net_value else 0
            rows.append({
                "symbol": sym,
                "type": pos.position_type,
                "long_strike": pos.long_strike,
                "long_expiration": pos.long_expiration,
                "long_dte": pos.long_dte,
                "short_strike": pos.short_strike,
                "short_expiration": pos.short_expiration,
                "net_debit": pos.net_debit,
                "premium_collected": pos.premium_collected,
                "unrealized_pnl": round(pnl, 2),
            })
        return rows

    @property
    def positions(self) -> Dict[str, LEAPSPosition]:
        return self._positions
