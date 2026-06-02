"""Journal de trades para calendar/diagonal spreads."""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import asdict
from options.calendar_diagonal.portfolio_manager import CalendarPosition


class CalendarJournal:
    def __init__(self, path: str = "logs/calendar_journal.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, position: CalendarPosition, event: str) -> None:
        entry = {
            "event": event,
            "symbol": position.spread.symbol,
            "strategy": position.spread.strategy,
            "status": position.status,
            "pnl": position.pnl,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
