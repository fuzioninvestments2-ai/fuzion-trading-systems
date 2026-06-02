from __future__ import annotations
import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TradeRecord:
    timestamp: str
    symbol: str
    action: str  # SELL_CSP | ASSIGN | SELL_CC | CLOSE | ROLL
    strike: float
    expiration: str
    premium: float
    contracts: int
    phase: str
    pnl: float = 0.0
    notes: str = ""


class WheelJournal:
    def __init__(self):
        self._records: List[TradeRecord] = []

    def log_trade(self, symbol: str, action: str, strike: float, expiration: str,
                  premium: float, contracts: int = 1, phase: str = "CSP",
                  pnl: float = 0.0, notes: str = "") -> TradeRecord:
        rec = TradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol,
            action=action,
            strike=strike,
            expiration=expiration,
            premium=premium,
            contracts=contracts,
            phase=phase,
            pnl=pnl,
            notes=notes,
        )
        self._records.append(rec)
        return rec

    def get_history(self, symbol: Optional[str] = None) -> List[TradeRecord]:
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
