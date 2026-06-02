from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class Catalyst:
    symbol: str
    event_type: str  # "earnings" | "macro" | "fda" | "product_launch"
    event_date: str
    days_until: int
    magnitude_estimate: float
    confirmed: bool


class CatalystScanner:
    def __init__(self):
        self._earnings_calendar: Dict[str, str] = {}
        self._macro_events: List[dict] = []

    def get_catalysts(self, symbol: str) -> List[Catalyst]:
        catalysts = []
        earnings = self.upcoming_earnings(symbol)
        if earnings:
            catalysts.append(earnings)
        macro = self.macro_events(symbol)
        catalysts.extend(macro)
        return sorted(catalysts, key=lambda c: c.days_until)

    def upcoming_earnings(self, symbol: str) -> Optional[Catalyst]:
        if symbol not in self._earnings_calendar:
            return None
        date_str = self._earnings_calendar[symbol]
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            days_until = (event_date - datetime.utcnow()).days
        except Exception:
            return None
        if days_until < 0 or days_until > 45:
            return None
        return Catalyst(
            symbol=symbol,
            event_type="earnings",
            event_date=date_str,
            days_until=days_until,
            magnitude_estimate=0.0,
            confirmed=True,
        )

    def macro_events(self, symbol: str) -> List[Catalyst]:
        results = []
        for event in self._macro_events:
            if event.get("affects_all", False) or symbol in event.get("symbols", []):
                try:
                    event_date = datetime.strptime(event["date"], "%Y-%m-%d")
                    days_until = (event_date - datetime.utcnow()).days
                except Exception:
                    continue
                if 0 <= days_until <= 30:
                    results.append(Catalyst(
                        symbol=symbol,
                        event_type="macro",
                        event_date=event["date"],
                        days_until=days_until,
                        magnitude_estimate=event.get("magnitude", 0.0),
                        confirmed=event.get("confirmed", False),
                    ))
        return results

    def register_earnings(self, symbol: str, date_str: str) -> None:
        self._earnings_calendar[symbol] = date_str

    def register_macro_event(self, date_str: str, event_name: str,
                              affects_all: bool = True,
                              symbols: Optional[List[str]] = None,
                              magnitude: float = 0.0) -> None:
        self._macro_events.append({
            "date": date_str,
            "name": event_name,
            "affects_all": affects_all,
            "symbols": symbols or [],
            "magnitude": magnitude,
            "confirmed": True,
        })
