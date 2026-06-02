from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class CondorTradeRecord:
    timestamp: str
    symbol: str
    action: str
    expiration: str
    put_short: float
    call_short: float
    credit: float
    max_loss: float
    pnl: float = 0.0
    notes: str = ""


class CondorJournal:
    def __init__(self):
        self._records: List[CondorTradeRecord] = []

    def log_trade(self, symbol: str, action: str, expiration: str,
                  put_short: float, call_short: float, credit: float,
                  max_loss: float, pnl: float = 0.0, notes: str = "") -> CondorTradeRecord:
        rec = CondorTradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol,
            action=action,
            expiration=expiration,
            put_short=put_short,
            call_short=call_short,
            credit=credit,
            max_loss=max_loss,
            pnl=pnl,
            notes=notes,
        )
        self._records.append(rec)
        return rec

    def get_history(self, symbol: Optional[str] = None) -> List[CondorTradeRecord]:
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
