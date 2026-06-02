from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class StrangleTradeRecord:
    timestamp: str
    symbol: str
    action: str
    put_strike: float
    call_strike: float
    expiration: str
    total_credit: float
    pnl: float = 0.0
    notes: str = ""


class StrangleJournal:
    def __init__(self):
        self._records: List[StrangleTradeRecord] = []

    def log_trade(self, symbol: str, action: str, put_strike: float,
                  call_strike: float, expiration: str, total_credit: float,
                  pnl: float = 0.0, notes: str = "") -> StrangleTradeRecord:
        rec = StrangleTradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol, action=action, put_strike=put_strike,
            call_strike=call_strike, expiration=expiration,
            total_credit=total_credit, pnl=pnl, notes=notes,
        )
        self._records.append(rec)
        return rec

    def get_history(self, symbol: Optional[str] = None) -> List[StrangleTradeRecord]:
        if symbol:
            return [r for r in self._records if r.symbol == symbol]
        return list(self._records)

    def export_csv(self) -> str:
        buf = io.StringIO()
        if not self._records:
            return ""
        writer = csv.DictWriter(buf, fieldnames=list(self._records[0].__dataclass_fields__.keys()))
        writer.writeheader()
        for r in self._records:
            writer.writerow(r.__dict__)
        return buf.getvalue()
