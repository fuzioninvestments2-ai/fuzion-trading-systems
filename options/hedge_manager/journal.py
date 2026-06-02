"""Journal de coberturas."""
import json
from pathlib import Path
from options.hedge_manager.hedge_engine import HedgePosition


class HedgeJournal:
    def __init__(self, path: str = "logs/hedge_journal.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, hedge: HedgePosition, event: str) -> None:
        entry = {"event": event, "symbol": hedge.symbol, "type": hedge.hedge_type,
                 "cost": hedge.cost, "protection": hedge.protection_level, "status": hedge.status}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
