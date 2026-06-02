from __future__ import annotations
from datetime import datetime
from typing import List
from .journal import SpreadTradeRecord


class CreditSpreadAnalytics:
    def __init__(self, records: List[SpreadTradeRecord]):
        self._records = records

    def win_rate(self) -> float:
        closed = [r for r in self._records if r.action == "CLOSE"]
        if not closed:
            return 0.0
        wins = [r for r in closed if r.pnl > 0]
        return round(len(wins) / len(closed), 4)

    def avg_credit(self) -> float:
        opens = [r for r in self._records if r.action == "OPEN"]
        if not opens:
            return 0.0
        return round(sum(r.credit for r in opens) / len(opens), 4)

    def income_monthly(self) -> float:
        opens = [r for r in self._records if r.action == "OPEN"]
        if not opens:
            return 0.0
        total = sum(r.credit * 100 for r in opens)
        try:
            first = datetime.fromisoformat(opens[0].timestamp)
            last = datetime.fromisoformat(opens[-1].timestamp)
            months = max((last - first).days / 30, 1)
        except Exception:
            months = 1
        return round(total / months, 2)

    def win_rate_by_direction(self) -> dict:
        result = {}
        for direction in ("bull_put", "bear_call"):
            closed = [r for r in self._records if r.action == "CLOSE" and r.direction == direction]
            if not closed:
                result[direction] = 0.0
                continue
            wins = [r for r in closed if r.pnl > 0]
            result[direction] = round(len(wins) / len(closed), 4)
        return result

    def total_pnl(self) -> float:
        return round(sum(r.pnl for r in self._records), 2)

    def summary(self) -> dict:
        return {
            "win_rate": self.win_rate(),
            "win_rate_by_direction": self.win_rate_by_direction(),
            "avg_credit": self.avg_credit(),
            "income_monthly": self.income_monthly(),
            "total_pnl": self.total_pnl(),
            "total_trades": len(self._records),
        }
