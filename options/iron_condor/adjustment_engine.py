from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class AdjustmentResult:
    action: str
    reason: str
    new_short_strike: Optional[float] = None
    credit_received: float = 0.0
    adjustments_used: int = 0


class AdjustmentEngine:
    def roll_wing(self, side: str, current_short: float, current_long: float,
                  direction: float, width: float) -> dict:
        if side == "put":
            new_short = current_short - 5
            new_long = new_short - width
        else:
            new_short = current_short + 5
            new_long = new_short + width
        return {
            "side": side,
            "old_short": current_short,
            "new_short": round(new_short, 2),
            "new_long": round(new_long, 2),
        }

    def evaluate(self, delta: float, profit_pct: float, adjustments: int) -> AdjustmentResult:
        if profit_pct >= 0.50:
            return AdjustmentResult("CLOSE", "50% profit target")
        if adjustments >= 2:
            return AdjustmentResult("CLOSE", "Max adjustments reached", adjustments_used=adjustments)
        if abs(delta) > 0.30:
            return AdjustmentResult(
                "ROLL_WING",
                f"Delta {delta:.2f} breached 0.30 threshold",
                adjustments_used=adjustments + 1,
            )
        return AdjustmentResult("HOLD", "Within parameters")
