from pydantic import BaseModel
from typing import List, Optional


class BacktestRequest(BaseModel):
    symbol: str
    start: Optional[str] = None
    end: Optional[str] = None
    start_date: Optional[str] = None   # alias frontend
    end_date: Optional[str] = None     # alias frontend
    initial_equity: float = 100_000
    strategy: str = "trend_following"

    def get_start(self) -> str:
        return self.start or self.start_date or "2020-01-01"

    def get_end(self) -> str:
        return self.end or self.end_date or "2024-12-31"


class StressTestRequest(BaseModel):
    symbol: str
    n_simulations: int = 10_000
    crash_scenarios: Optional[List[str]] = None
    gap_sizes: Optional[List[float]] = None
