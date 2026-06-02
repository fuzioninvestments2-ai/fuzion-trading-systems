from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class DebitSpreadTradeRecord:
    timestamp: str
    symbol: str
    action: str
    direction: str
    long_strike: float
    short_strike: float
    expiration: str
    debit: float
    setup_type: str
    pnl: float = 0.0
    notes: str = ""


class DebitSpreadJournal:
    def __init__(self):
        self._records: List[DebitSpreadTradeRecord] = []

    def log_trade(self, symbol: str, action: str, direction: str,
                  long_strike: float, short_strike: float, expiration: str,
                  debit: float, setup_type: str = "", pnl: float = 0.0,
                  notes: str = "") -> DebitSpreadTradeRecord:
        rec = DebitSpreadTradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol, action=action, direction=direction,
            long_strike=long_strike, short_strike=short_strike,
            expiration=expiration, debit=debit, setup_type=setup_type,
            pnl=pnl, notes=notes,
        )
        self._records.append(rec)
        return rec

    def get_history(self, symbol: Optional[str] = None) -> List[DebitSpreadTradeRecord]:
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
