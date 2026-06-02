from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
from options.common.chain_models import ChainData, OptionContract


@dataclass
class TermStructureResult:
    front_iv: float
    back_iv: float
    spread: float
    contango: bool
    backwardation: bool
    slope: float


class TermStructure:
    def analyze_contango(self, front_chain: ChainData,
                         back_chain: ChainData) -> bool:
        result = self.analyze(front_chain, back_chain)
        return result.contango

    def analyze(self, front_chain: ChainData,
                back_chain: ChainData) -> TermStructureResult:
        front_iv = self._avg_iv(front_chain)
        back_iv = self._avg_iv(back_chain)
        spread = back_iv - front_iv
        return TermStructureResult(
            front_iv=round(front_iv, 4),
            back_iv=round(back_iv, 4),
            spread=round(spread, 4),
            contango=back_iv > front_iv,
            backwardation=front_iv > back_iv,
            slope=round(spread / max(back_chain.dte - front_chain.dte, 1), 6),
        )

    def analyze_multi(self, chains: Dict[str, ChainData]) -> List[TermStructureResult]:
        expirations = sorted(chains.keys())
        results = []
        for i in range(len(expirations) - 1):
            front = chains[expirations[i]]
            back = chains[expirations[i + 1]]
            results.append(self.analyze(front, back))
        return results

    def _avg_iv(self, chain: ChainData) -> float:
        ivs = []
        for c in chain.calls + chain.puts:
            if c.implied_volatility > 0:
                ivs.append(c.implied_volatility)
        return sum(ivs) / len(ivs) if ivs else 0.25
