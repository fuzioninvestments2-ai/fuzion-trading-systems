from __future__ import annotations
from datetime import datetime
from typing import Dict, List
from .journal import MomentumTradeRecord


class MomentumAnalytics:
    def __init__(self, records: List[MomentumTradeRecord]):
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

    def total_pnl(self) -> float:
        return round(sum(r.pnl for r in self._records), 2)

    def avg_win(self) -> float:
        wins = [r.pnl for r in self._records if r.action == "CLOSE" and r.pnl > 0]
        return round(sum(wins) / len(wins), 2) if wins else 0.0

    def avg_loss(self) -> float:
        losses = [r.pnl for r in self._records if r.action == "CLOSE" and r.pnl < 0]
        return round(sum(losses) / len(losses), 2) if losses else 0.0

    def income_monthly(self) -> float:
        wins = [r for r in self._records if r.action == "CLOSE" and r.pnl > 0]
        if not wins:
            return 0.0
        total = sum(r.pnl for r in wins)
        try:
            first = datetime.fromisoformat(wins[0].timestamp)
            last = datetime.fromisoformat(wins[-1].timestamp)
            months = max((last - first).days / 30, 1)
        except Exception:
            months = 1
        return round(total / months, 2)

    def summary(self) -> dict:
        return {
            "win_rate": self.win_rate(),
            "win_rate_by_setup": self.win_rate_by_setup(),
            "avg_win": self.avg_win(),
            "avg_loss": self.avg_loss(),
            "income_monthly": self.income_monthly(),
            "total_pnl": self.total_pnl(),
            "total_trades": len(self._records),
        }
