from __future__ import annotations
from datetime import datetime
from typing import Dict, List
from .journal import DebitSpreadTradeRecord


class DebitSpreadAnalytics:
    def __init__(self, records: List[DebitSpreadTradeRecord]):
        self._records = records

    def win_rate(self) -> float:
        closed = [r for r in self._records if r.action == "CLOSE"]
        if not closed:
            return 0.0
        return round(sum(1 for r in closed if r.pnl > 0) / len(closed), 4)

    def win_rate_by_setup(self) -> Dict[str, float]:
        setups = set(r.setup_type for r in self._records)
        result = {}
        for s in setups:
            closed = [r for r in self._records if r.action == "CLOSE" and r.setup_type == s]
            if not closed:
                result[s] = 0.0
                continue
            result[s] = round(sum(1 for r in closed if r.pnl > 0) / len(closed), 4)
        return result

    def avg_debit(self) -> float:
        opens = [r for r in self._records if r.action == "OPEN"]
        if not opens:
            return 0.0
        return round(sum(r.debit for r in opens) / len(opens), 4)

    def total_pnl(self) -> float:
        return round(sum(r.pnl for r in self._records), 2)

    def income_monthly(self) -> float:
        closed_wins = [r for r in self._records if r.action == "CLOSE" and r.pnl > 0]
        if not closed_wins:
            return 0.0
        total = sum(r.pnl for r in closed_wins)
        try:
            first = datetime.fromisoformat(closed_wins[0].timestamp)
            last = datetime.fromisoformat(closed_wins[-1].timestamp)
            months = max((last - first).days / 30, 1)
        except Exception:
            months = 1
        return round(total / months, 2)

    def summary(self) -> dict:
        return {
            "win_rate": self.win_rate(),
            "win_rate_by_setup": self.win_rate_by_setup(),
            "avg_debit": self.avg_debit(),
            "income_monthly": self.income_monthly(),
            "total_pnl": self.total_pnl(),
            "total_trades": len(self._records),
        }
