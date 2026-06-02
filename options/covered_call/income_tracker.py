from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List


@dataclass
class PremiumEvent:
    timestamp: str
    symbol: str
    premium_per_share: float
    contracts: int
    expiration: str
    total_income: float


class IncomeTracker:
    def __init__(self):
        self._events: List[PremiumEvent] = []

    def track_premium(self, symbol: str, premium_per_share: float,
                      contracts: int = 1, expiration: str = "") -> PremiumEvent:
        total = premium_per_share * contracts * 100
        event = PremiumEvent(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol,
            premium_per_share=premium_per_share,
            contracts=contracts,
            expiration=expiration,
            total_income=round(total, 2),
        )
        self._events.append(event)
        return event

    def monthly_income(self) -> Dict[str, float]:
        monthly: Dict[str, float] = {}
        for e in self._events:
            try:
                dt = datetime.fromisoformat(e.timestamp)
                key = dt.strftime("%Y-%m")
            except Exception:
                key = "unknown"
            monthly[key] = monthly.get(key, 0.0) + e.total_income
        return monthly

    def annual_income(self) -> Dict[int, float]:
        annual: Dict[int, float] = {}
        for e in self._events:
            try:
                year = datetime.fromisoformat(e.timestamp).year
            except Exception:
                year = 0
            annual[year] = annual.get(year, 0.0) + e.total_income
        return annual

    def income_by_symbol(self) -> Dict[str, float]:
        by_sym: Dict[str, float] = {}
        for e in self._events:
            by_sym[e.symbol] = by_sym.get(e.symbol, 0.0) + e.total_income
        return by_sym

    def total_income(self) -> float:
        return round(sum(e.total_income for e in self._events), 2)

    def avg_monthly_income(self) -> float:
        monthly = self.monthly_income()
        if not monthly:
            return 0.0
        return round(sum(monthly.values()) / len(monthly), 2)
