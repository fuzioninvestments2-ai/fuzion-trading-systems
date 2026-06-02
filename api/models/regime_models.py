from pydantic import BaseModel
from typing import List, Optional


class RegimeAnalysisRequest(BaseModel):
    symbol: str
    bars_data: Optional[List[dict]] = None
    period: str = "5y"


class GreeksRequest(BaseModel):
    # Notación Black-Scholes (S, K, T) o nombres amigables para el frontend
    S: Optional[float] = None
    K: Optional[float] = None
    T: Optional[float] = None
    spot: Optional[float] = None
    strike: Optional[float] = None
    expiry_days: Optional[int] = None
    r: float = 0.05
    risk_free_rate: Optional[float] = None
    sigma: Optional[float] = None
    iv: Optional[float] = None
    option_type: str = "call"

    def resolved_S(self) -> float:
        return self.S or self.spot or 0.0

    def resolved_K(self) -> float:
        return self.K or self.strike or 0.0

    def resolved_T(self) -> float:
        if self.T:
            return self.T
        if self.expiry_days:
            return self.expiry_days / 365.0
        return 0.0

    def resolved_r(self) -> float:
        return self.r if self.r != 0.05 else (self.risk_free_rate or 0.05)

    def resolved_sigma(self) -> float:
        return self.sigma or self.iv or 0.20


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
