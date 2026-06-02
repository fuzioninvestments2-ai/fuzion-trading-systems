from __future__ import annotations
from datetime import datetime
from typing import List
from .journal import LEAPSTradeRecord


class LEAPSAnalytics:
    def __init__(self, records: List[LEAPSTradeRecord]):
        self._records = records

    def win_rate(self) -> float:
        closed = [r for r in self._records if r.action == "CLOSE"]
        if not closed:
            return 0.0
        return round(sum(1 for r in closed if r.pnl > 0) / len(closed), 4)

    def total_premium_collected(self) -> float:
        rolls = [r for r in self._records if r.action in ("SELL_SHORT", "ROLL_SHORT")]
        return round(sum(r.net_debit * -1 for r in rolls if r.net_debit < 0), 2)

    def income_monthly(self) -> float:
        rolls = [r for r in self._records if r.action in ("SELL_SHORT", "ROLL_SHORT")]
        if not rolls:
            return 0.0
        total = sum(abs(r.net_debit) * 100 for r in rolls if r.net_debit < 0)
        try:
            first = datetime.fromisoformat(rolls[0].timestamp)
            last = datetime.fromisoformat(rolls[-1].timestamp)
            months = max((last - first).days / 30, 1)
        except Exception:
            months = 1
        return round(total / months, 2)

    def total_pnl(self) -> float:
        return round(sum(r.pnl for r in self._records), 2)

    def summary(self) -> dict:
        return {
            "win_rate": self.win_rate(),
            "income_monthly": self.income_monthly(),
            "total_pnl": self.total_pnl(),
            "total_trades": len(self._records),
        }
