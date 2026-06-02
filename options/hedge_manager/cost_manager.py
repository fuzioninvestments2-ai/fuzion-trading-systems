from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class HedgeCostReport:
    annual_cost: float
    annual_cost_pct: float
    monthly_cost: float
    cost_per_hedge: Dict[str, float]
    within_budget: bool
    budget_pct: float


class CostManager:
    def __init__(self, account_size: float, max_annual_cost_pct: float = 0.02):
        self.account_size = account_size
        self.max_annual_cost_pct = max_annual_cost_pct

    def hedge_cost_pct(self, hedge_premium: float, portfolio_value: float) -> float:
        if portfolio_value <= 0:
            return 0.0
        return hedge_premium / portfolio_value

    def annualized_cost(self, premium: float, dte: int) -> float:
        if dte <= 0:
            return 0.0
        return premium * (365 / dte)

    def is_within_budget(self, total_hedge_cost: float, portfolio_value: float) -> bool:
        cost_pct = self.hedge_cost_pct(total_hedge_cost, portfolio_value)
        return cost_pct <= self.max_annual_cost_pct

    def analyze_costs(self, hedge_positions: List[dict],
                      portfolio_value: float) -> HedgeCostReport:
        total_annual = 0.0
        cost_per_hedge: Dict[str, float] = {}
        for pos in hedge_positions:
            hedge_type = pos.get("hedge_type", "unknown")
            premium = pos.get("premium", 0.0)
            dte = pos.get("dte", 30)
            ann = self.annualized_cost(premium * 100, dte)
            total_annual += ann
            cost_per_hedge[hedge_type] = cost_per_hedge.get(hedge_type, 0.0) + ann

        annual_cost_pct = self.hedge_cost_pct(total_annual, portfolio_value)
        return HedgeCostReport(
            annual_cost=round(total_annual, 2),
            annual_cost_pct=round(annual_cost_pct, 4),
            monthly_cost=round(total_annual / 12, 2),
            cost_per_hedge={k: round(v, 2) for k, v in cost_per_hedge.items()},
            within_budget=annual_cost_pct <= self.max_annual_cost_pct,
            budget_pct=self.max_annual_cost_pct,
        )
