from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .portfolio_manager import WheelPortfolioManager, WheelPosition


@dataclass
class AssignmentResult:
    symbol: str
    shares_received: int
    cost_basis: float
    total_premiums_collected: float
    effective_cost_basis: float
    recommended_action: str


class AssignmentManager:
    def handle_assignment(self, symbol: str, strike: float, contracts: int,
                          premiums_collected: float,
                          portfolio: WheelPortfolioManager) -> AssignmentResult:
        shares = contracts * 100
        effective_cb = strike - (premiums_collected / shares) if shares > 0 else strike

        pos = portfolio.get_position(symbol)
        if pos:
            pos.phase = "STOCK"
            pos.shares = shares
            pos.cost_basis = effective_cb
        else:
            portfolio.add_position(WheelPosition(
                symbol=symbol,
                phase="STOCK",
                cost_basis=effective_cb,
                shares=shares,
                strike=strike,
                premium_collected=premiums_collected,
                entry_price=strike,
            ))

        return AssignmentResult(
            symbol=symbol,
            shares_received=shares,
            cost_basis=strike,
            total_premiums_collected=premiums_collected,
            effective_cost_basis=round(effective_cb, 2),
            recommended_action="SELL_COVERED_CALL",
        )
