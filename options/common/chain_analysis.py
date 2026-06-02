"""Análisis de la cadena de opciones: flujo de opciones, OI analysis, anomalías."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import pandas as pd

from options.common.chain_models import ChainData, OptionContract


@dataclass
class FlowSignal:
    symbol: str
    direction: str          # "bullish" | "bearish" | "neutral"
    call_put_ratio: float
    net_premium: float      # premium comprado (calls) - premium vendido (puts)
    unusual_strikes: List[str]
    confidence: float       # 0-1


@dataclass
class OpenInterestAnalysis:
    symbol: str
    max_pain: float
    call_wall: float        # mayor OI de calls
    put_wall: float         # mayor OI de puts
    resistance_levels: List[float]
    support_levels: List[float]


@dataclass
class ChainAnalysisResult:
    flow: FlowSignal
    oi_analysis: OpenInterestAnalysis
    skew_summary: str
    term_structure_bias: str    # "contango" | "backwardation" | "flat"
    recommended_strategy: str


class ChainAnalyzer:
    """Analiza la cadena de opciones para señales de flujo e interés abierto."""

    def analyze(self, chain: ChainData) -> ChainAnalysisResult:
        flow = self._analyze_flow(chain)
        oi = self._analyze_oi(chain)
        skew = self._summarize_skew(chain)
        term = self._term_structure_bias(chain)
        strategy = self._recommend_strategy(flow, oi, skew, term)
        return ChainAnalysisResult(flow, oi, skew, term, strategy)

    def _analyze_flow(self, chain: ChainData) -> FlowSignal:
        calls = chain.calls
        puts = chain.puts
        call_vol = sum(c.volume for c in calls)
        put_vol = sum(p.volume for p in puts)
        ratio = call_vol / max(put_vol, 1)
        call_premium = sum(c.volume * c.mid_price for c in calls)
        put_premium = sum(p.volume * p.mid_price for p in puts)
        net = call_premium - put_premium

        if ratio > 1.5:
            direction = "bullish"
        elif ratio < 0.7:
            direction = "bearish"
        else:
            direction = "neutral"

        unusual = self._find_unusual_strikes(calls + puts)
        confidence = min(abs(ratio - 1.0) / 1.0, 1.0)

        return FlowSignal(
            symbol=chain.underlying.symbol,
            direction=direction,
            call_put_ratio=ratio,
            net_premium=net,
            unusual_strikes=unusual,
            confidence=confidence,
        )

    def _find_unusual_strikes(self, contracts: List[OptionContract]) -> List[str]:
        if not contracts:
            return []
        avg_vol = sum(c.volume for c in contracts) / len(contracts)
        unusual = [
            f"{c.option_type.upper()} {c.strike}"
            for c in contracts
            if c.volume > avg_vol * 3 and c.volume > 500
        ]
        return unusual[:5]

    def _analyze_oi(self, chain: ChainData) -> OpenInterestAnalysis:
        calls = chain.calls
        puts = chain.puts
        spot = chain.underlying.last_price

        max_pain = self._compute_max_pain(calls, puts)
        call_wall = max((c.strike for c in calls), key=lambda s: sum(c.open_interest for c in calls if c.strike == s), default=spot)
        put_wall = max((p.strike for p in puts), key=lambda s: sum(p.open_interest for p in puts if p.strike == s), default=spot)

        resistances = sorted({c.strike for c in calls if c.open_interest > 1000 and c.strike > spot})[:3]
        supports = sorted({p.strike for p in puts if p.open_interest > 1000 and p.strike < spot}, reverse=True)[:3]

        return OpenInterestAnalysis(
            symbol=chain.underlying.symbol,
            max_pain=max_pain,
            call_wall=float(call_wall),
            put_wall=float(put_wall),
            resistance_levels=list(resistances),
            support_levels=list(supports),
        )

    def _compute_max_pain(self, calls: List[OptionContract], puts: List[OptionContract]) -> float:
        strikes = sorted(set(c.strike for c in calls + puts))
        if not strikes:
            return 0.0
        min_pain = float("inf")
        max_pain_strike = strikes[0]
        for s in strikes:
            pain = sum(max(0, s - c.strike) * c.open_interest for c in calls)
            pain += sum(max(0, p.strike - s) * p.open_interest for p in puts)
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = s
        return float(max_pain_strike)

    def _summarize_skew(self, chain: ChainData) -> str:
        puts = [p for p in chain.puts if p.implied_volatility is not None]
        calls = [c for c in chain.calls if c.implied_volatility is not None]
        if not puts or not calls:
            return "unknown"
        avg_put_iv = sum(p.implied_volatility for p in puts) / len(puts)
        avg_call_iv = sum(c.implied_volatility for c in calls) / len(calls)
        if avg_put_iv > avg_call_iv * 1.1:
            return "put_skew"
        elif avg_call_iv > avg_put_iv * 1.1:
            return "call_skew"
        return "flat"

    def _term_structure_bias(self, chain: ChainData) -> str:
        exps = chain.expirations
        if len(exps) < 2:
            return "flat"
        ivs = [e.atm_iv for e in exps if e.atm_iv is not None]
        if len(ivs) < 2:
            return "flat"
        return "contango" if ivs[0] < ivs[-1] else "backwardation"

    def _recommend_strategy(self, flow: FlowSignal, oi: OpenInterestAnalysis,
                            skew: str, term: str) -> str:
        if flow.direction == "bullish" and skew == "put_skew" and term == "contango":
            return "bull_put_spread"
        elif flow.direction == "bearish" and skew == "call_skew":
            return "bear_call_spread"
        elif flow.direction == "neutral" and term == "contango":
            return "iron_condor"
        elif term == "backwardation":
            return "calendar_spread"
        return "covered_call"
