"""Journal de earnings plays."""
import json
from pathlib import Path
from options.earnings.portfolio_manager import EarningsPosition


class EarningsJournal:
    def __init__(self, path: str = "logs/earnings_journal.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, position: EarningsPosition, event: str) -> None:
        entry = {"event": event, "symbol": position.setup.symbol,
                 "strategy": position.setup.strategy, "status": position.status, "pnl": position.pnl}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
