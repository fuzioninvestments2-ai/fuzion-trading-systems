from pydantic import BaseModel
from typing import List, Optional


class RegimeAnalysisRequest(BaseModel):
    symbol: str
    bars_data: Optional[List[dict]] = None
    period: str = "5y"


class GreeksRequest(BaseModel):
    S: float
    K: float
    T: float
    r: float = 0.05
    sigma: float
    option_type: str = "call"


class ScreenRequest(BaseModel):
    universe: List[str]
    min_iv_rank: float = 0.0
    max_iv_rank: float = 100.0
    min_dte: int = 20
    max_dte: int = 60


class WheelScanRequest(BaseModel):
    universe: List[str]
    account_size: float
    regime: Optional[str] = None


class CondorScanRequest(BaseModel):
    symbol: str
    account_size: float
    regime: Optional[str] = None


class SpreadScanRequest(BaseModel):
    symbol: str
    direction: str = "bull"
    account_size: float
    regime: Optional[str] = None


class EarningsScanRequest(BaseModel):
    universe: List[str]
    regime: Optional[str] = None
