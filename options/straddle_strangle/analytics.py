from __future__ import annotations
from datetime import datetime
from typing import List
from .journal import LongVolTradeRecord


class LongVolAnalytics:
    def __init__(self, records: List[LongVolTradeRecord]):
        self._records = records

    def win_rate(self) -> float:
        closed = [r for r in self._records if r.action == "CLOSE"]
        if not closed:
            return 0.0
        return round(sum(1 for r in closed if r.pnl > 0) / len(closed), 4)

    def avg_debit(self) -> float:
        opens = [r for r in self._records if r.action == "OPEN"]
        if not opens:
            return 0.0
        return round(sum(r.total_debit for r in opens) / len(opens), 4)

    def total_pnl(self) -> float:
        return round(sum(r.pnl for r in self._records), 2)

    def avg_win(self) -> float:
        wins = [r.pnl for r in self._records if r.action == "CLOSE" and r.pnl > 0]
        return round(sum(wins) / len(wins), 2) if wins else 0.0

    def avg_loss(self) -> float:
        losses = [r.pnl for r in self._records if r.action == "CLOSE" and r.pnl < 0]
        return round(sum(losses) / len(losses), 2) if losses else 0.0

    def summary(self) -> dict:
        return {
            "win_rate": self.win_rate(),
            "avg_debit": self.avg_debit(),
            "avg_win": self.avg_win(),
            "avg_loss": self.avg_loss(),
            "total_pnl": self.total_pnl(),
            "total_trades": len(self._records),
        }
