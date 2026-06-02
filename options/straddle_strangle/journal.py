from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class LongVolTradeRecord:
    timestamp: str
    symbol: str
    action: str
    structure: str
    call_strike: float
    put_strike: float
    expiration: str
    total_debit: float
    catalyst: str
    pnl: float = 0.0
    notes: str = ""


class LongVolJournal:
    def __init__(self):
        self._records: List[LongVolTradeRecord] = []

    def log_trade(self, symbol: str, action: str, structure: str,
                  call_strike: float, put_strike: float, expiration: str,
                  total_debit: float, catalyst: str = "",
                  pnl: float = 0.0, notes: str = "") -> LongVolTradeRecord:
        rec = LongVolTradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol, action=action, structure=structure,
            call_strike=call_strike, put_strike=put_strike,
            expiration=expiration, total_debit=total_debit,
            catalyst=catalyst, pnl=pnl, notes=notes,
        )
        self._records.append(rec)
        return rec

    def get_history(self, symbol: Optional[str] = None) -> List[LongVolTradeRecord]:
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
