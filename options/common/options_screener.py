"""Options Screener — escanea universo con criterios."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from .chain_fetcher import OptionsChainFetcher
from .iv_analyzer import IVAnalyzer


@dataclass
class ScreenCriteria:
    min_iv_rank: float = 0.0
    max_iv_rank: float = 100.0
    min_volume: int = 100
    min_oi: int = 500
    max_dte: int = 60
    min_dte: int = 20
    exclude_earnings_within_days: int = 30


@dataclass
class ScreenResult:
    symbol: str
    iv_rank: float
    iv_percentile: float
    current_iv: float
    score: float
    notes: List[str] = field(default_factory=list)


@dataclass
class UnusualActivity:
    symbol: str
    option_type: str
    strike: float
    expiration: str
    volume: int
    open_interest: int
    volume_oi_ratio: float


class OptionsScreener:
    def __init__(self, fetcher: Optional[OptionsChainFetcher] = None,
                 analyzer: Optional[IVAnalyzer] = None):
        self._fetcher = fetcher or OptionsChainFetcher()
        self._analyzer = analyzer or IVAnalyzer(self._fetcher)

    def scan_universe(self, universe: List[str],
                      criteria: ScreenCriteria) -> List[ScreenResult]:
        results = []
        for symbol in universe:
            try:
                ivr = self._analyzer.iv_rank(symbol)
                ivp = self._analyzer.iv_percentile(symbol)
                iv_hv = self._analyzer.iv_vs_hv(symbol)

                if not (criteria.min_iv_rank <= ivr <= criteria.max_iv_rank):
                    continue

                score = ivr * 0.6 + ivp * 0.4
                notes = []
                if iv_hv.iv_premium > 0.05:
                    notes.append("IV elevada vs HV")
                results.append(ScreenResult(
                    symbol=symbol, iv_rank=ivr, iv_percentile=ivp,
                    current_iv=iv_hv.current_iv, score=round(score, 2), notes=notes,
                ))
            except Exception as e:
                pass
        return sorted(results, key=lambda r: r.score, reverse=True)

    def unusual_activity(self, universe: List[str],
                          volume_threshold: float = 2.0) -> List[UnusualActivity]:
        results = []
        for symbol in universe:
            try:
                chain = self._fetcher.get_chain(symbol)
                for contract in chain.calls + chain.puts:
                    if contract.open_interest > 0:
                        ratio = contract.volume / contract.open_interest
                        if ratio >= volume_threshold and contract.volume >= 500:
                            results.append(UnusualActivity(
                                symbol=symbol,
                                option_type=contract.option_type,
                                strike=contract.strike,
                                expiration=chain.expiration,
                                volume=contract.volume,
                                open_interest=contract.open_interest,
                                volume_oi_ratio=round(ratio, 2),
                            ))
            except Exception:
                pass
        return sorted(results, key=lambda u: u.volume_oi_ratio, reverse=True)
