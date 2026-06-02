from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class LEAPSTradeRecord:
    timestamp: str
    symbol: str
    action: str
    position_type: str
    long_strike: float
    long_expiration: str
    short_strike: float
    short_expiration: str
    net_debit: float
    pnl: float = 0.0
    notes: str = ""


class LEAPSJournal:
    def __init__(self):
        self._records: List[LEAPSTradeRecord] = []

    def log_trade(self, symbol: str, action: str, position_type: str,
                  long_strike: float, long_expiration: str,
                  short_strike: float = 0.0, short_expiration: str = "",
                  net_debit: float = 0.0, pnl: float = 0.0,
                  notes: str = "") -> LEAPSTradeRecord:
        rec = LEAPSTradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol, action=action, position_type=position_type,
            long_strike=long_strike, long_expiration=long_expiration,
            short_strike=short_strike, short_expiration=short_expiration,
            net_debit=net_debit, pnl=pnl, notes=notes,
        )
        self._records.append(rec)
        return rec

    def get_history(self, symbol: Optional[str] = None) -> List[LEAPSTradeRecord]:
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
