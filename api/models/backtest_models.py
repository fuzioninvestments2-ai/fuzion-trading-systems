from pydantic import BaseModel
from typing import List, Optional


class BacktestRequest(BaseModel):
    symbol: str
    start: str = "2020-01-01"
    end: str = "2024-12-31"
    initial_equity: float = 100_000
    strategy: str = "trend_following"


class StressTestRequest(BaseModel):
    symbol: str
    n_simulations: int = 10_000
    crash_scenarios: Optional[List[str]] = None
    gap_sizes: Optional[List[float]] = None
