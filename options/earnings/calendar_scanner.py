"""Scanner de calendarios de earnings."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import datetime


@dataclass
class EarningsEvent:
    symbol: str
    expected_date: str
    confirmed: bool
    quarter: str
    estimated_eps: Optional[float] = None

    # avoid circular import
    from typing import Optional


class EarningsCalendarScanner:
    """Escanea upcoming earnings para identificar oportunidades."""

    def __init__(self, universe: List[str], lookforward_days: int = 30):
        self.universe = universe
        self.lookforward_days = lookforward_days

    def get_upcoming(self) -> List[EarningsEvent]:
        """
        Retorna earnings próximos del universo.
        En producción conectar a yfinance o API de earnings.
        """
        try:
            import yfinance as yf
            events = []
            for symbol in self.universe:
                try:
                    tk = yf.Ticker(symbol)
                    cal = tk.calendar
                    if cal is not None and "Earnings Date" in cal:
                        edate = cal["Earnings Date"]
                        if isinstance(edate, list) and edate:
                            edate = edate[0]
                        events.append(EarningsEvent(
                            symbol=symbol,
                            expected_date=str(edate)[:10],
                            confirmed=True,
                            quarter="Q?",
                        ))
                except Exception:
                    continue
            return events
        except ImportError:
            return []
