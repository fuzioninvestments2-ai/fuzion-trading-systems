from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


WIN_RATE_THRESHOLD = 0.40
MIN_TRADES_TO_EVALUATE = 10


@dataclass
class SetupStats:
    setup_type: str
    total_trades: int = 0
    winning_trades: int = 0
    active: bool = True

    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    def should_deactivate(self) -> bool:
        return (self.total_trades >= MIN_TRADES_TO_EVALUATE
                and self.win_rate() < WIN_RATE_THRESHOLD)


class SignalTracker:
    def __init__(self):
        self._stats: Dict[str, SetupStats] = {}

    def record_trade(self, setup_type: str, won: bool) -> None:
        if setup_type not in self._stats:
            self._stats[setup_type] = SetupStats(setup_type=setup_type)
        stats = self._stats[setup_type]
        stats.total_trades += 1
        if won:
            stats.winning_trades += 1
        if stats.should_deactivate():
            stats.active = False

    def is_setup_active(self, setup_type: str) -> bool:
        if setup_type not in self._stats:
            return True
        return self._stats[setup_type].active

    def reactivate_setup(self, setup_type: str) -> None:
        if setup_type in self._stats:
            self._stats[setup_type].active = True

    def win_rate_by_setup(self) -> Dict[str, float]:
        return {k: round(v.win_rate(), 4) for k, v in self._stats.items()}

    def summary(self) -> List[dict]:
        return [
            {
                "setup_type": s.setup_type,
                "total_trades": s.total_trades,
                "win_rate": round(s.win_rate(), 4),
                "active": s.active,
            }
            for s in self._stats.values()
        ]
