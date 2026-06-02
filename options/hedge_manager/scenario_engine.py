from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CrashScenario:
    crash_pct: float
    portfolio_loss: float
    hedge_gain: float
    net_loss: float
    protection_pct: float


class ScenarioEngine:
    def simulate_crash(self, portfolio_positions: List[dict],
                       spot: float, crash_pct: float) -> CrashScenario:
        new_spot = spot * (1 + crash_pct)
        portfolio_loss = 0.0
        hedge_gain = 0.0

        for pos in portfolio_positions:
            pos_type = pos.get("type", "stock")
            value = pos.get("value", 0.0)
            if pos_type == "stock":
                portfolio_loss += value * abs(crash_pct)
            elif pos_type == "put":
                strike = pos.get("strike", 0.0)
                quantity = pos.get("quantity", 1)
                intrinsic = max(0.0, strike - new_spot)
                entry_premium = pos.get("premium", 0.0)
                hedge_gain += max(0.0, intrinsic - entry_premium) * quantity * 100

        net_loss = portfolio_loss - hedge_gain
        protection_pct = hedge_gain / portfolio_loss if portfolio_loss > 0 else 0.0
        return CrashScenario(
            crash_pct=crash_pct,
            portfolio_loss=round(portfolio_loss, 2),
            hedge_gain=round(hedge_gain, 2),
            net_loss=round(net_loss, 2),
            protection_pct=round(protection_pct, 4),
        )

    def simulate_scenarios(self, spot: float, put_strike: float,
                           put_premium: float) -> Dict[float, float]:
        result = {}
        for crash_pct in [-0.10, -0.20, -0.30, -0.50]:
            new_spot = spot * (1 + crash_pct)
            intrinsic = max(0.0, put_strike - new_spot)
            pnl = intrinsic - put_premium
            result[crash_pct] = round(pnl, 2)
        return result
