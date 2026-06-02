from __future__ import annotations
from typing import List
from datetime import datetime
from .journal import TradeRecord


class WheelAnalytics:
    def __init__(self, records: List[TradeRecord]):
        self._records = records

    def win_rate(self) -> float:
        closed = [r for r in self._records if r.action == "CLOSE"]
        if not closed:
            return 0.0
        wins = [r for r in closed if r.pnl > 0]
        return round(len(wins) / len(closed), 4)

    def avg_premium_yield(self) -> float:
        sells = [r for r in self._records if r.action in ("SELL_CSP", "SELL_CC")]
        if not sells:
            return 0.0
        yields = [r.premium / r.strike for r in sells if r.strike > 0]
        return round(sum(yields) / len(yields), 4) if yields else 0.0

    def income_monthly(self) -> float:
        sells = [r for r in self._records if r.action in ("SELL_CSP", "SELL_CC")]
        if not sells:
            return 0.0
        total = sum(r.premium * r.contracts * 100 for r in sells)
        try:
            first = datetime.fromisoformat(sells[0].timestamp)
            last = datetime.fromisoformat(sells[-1].timestamp)
            months = max((last - first).days / 30, 1)
        except Exception:
            months = 1
        return round(total / months, 2)

    def total_premium_collected(self) -> float:
        return sum(r.premium * r.contracts * 100
                   for r in self._records if r.action in ("SELL_CSP", "SELL_CC"))

    def total_pnl(self) -> float:
        return sum(r.pnl for r in self._records)

    def summary(self) -> dict:
        return {
            "win_rate": self.win_rate(),
            "avg_premium_yield": self.avg_premium_yield(),
            "income_monthly": self.income_monthly(),
            "total_premium_collected": round(self.total_premium_collected(), 2),
            "total_pnl": round(self.total_pnl(), 2),
            "total_trades": len(self._records),
        }
