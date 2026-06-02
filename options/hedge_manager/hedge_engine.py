"""Hedge Manager: protección de portfolio en regímenes BEAR/CRASH."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
from options.common.chain_models import OptionContract


@dataclass
class HedgePosition:
    symbol: str
    hedge_type: str     # "put_spread" | "collar" | "tail_hedge"
    cost: float
    protection_level: float     # % drawdown cubierto
    expiry: str
    quantity: int
    status: str = "active"


class HedgeEngine:
    """
    Gestiona coberturas de portfolio:
    - Put spreads para protección direccional
    - Collars para posiciones long
    - Tail hedges (far OTM puts) en regímenes CRASH
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.max_hedge_cost_pct = self.config.get("max_hedge_cost_pct", 0.02)  # 2% portfolio
        self.tail_hedge_dte = self.config.get("tail_hedge_dte", 90)
        self.positions: List[HedgePosition] = []

    def evaluate_hedge_need(self, regime_label: str, portfolio_delta: float, portfolio_value: float) -> str:
        """Determina qué tipo de cobertura es necesaria."""
        if regime_label == "CRASH":
            return "tail_hedge"
        elif regime_label == "BEAR":
            return "put_spread" if portfolio_delta > 0.3 else "none"
        elif portfolio_delta > 0.8:
            return "collar"
        return "none"

    def size_hedge(self, portfolio_value: float, protection_level: float, spot: float) -> int:
        """Calcula contratos necesarios para cubrir el portfolio."""
        notional_to_hedge = portfolio_value * protection_level
        contract_notional = spot * 100
        return max(1, int(notional_to_hedge / contract_notional))

    def build_put_spread(
        self,
        symbol: str,
        long_put: OptionContract,
        short_put: OptionContract,
        quantity: int,
    ) -> Optional[HedgePosition]:
        if long_put.strike <= short_put.strike:
            return None
        cost = (long_put.ask - short_put.bid) * 100 * quantity
        protection = (long_put.strike - short_put.strike) / long_put.strike
        pos = HedgePosition(
            symbol=symbol,
            hedge_type="put_spread",
            cost=cost,
            protection_level=protection,
            expiry=long_put.expiration,
            quantity=quantity,
        )
        self.positions.append(pos)
        return pos

    def build_tail_hedge(
        self,
        symbol: str,
        put_contract: OptionContract,
        quantity: int,
    ) -> HedgePosition:
        cost = put_contract.ask * 100 * quantity
        pos = HedgePosition(
            symbol=symbol,
            hedge_type="tail_hedge",
            cost=cost,
            protection_level=1.0,
            expiry=put_contract.expiration,
            quantity=quantity,
        )
        self.positions.append(pos)
        return pos

    def active_hedges(self) -> List[HedgePosition]:
        return [p for p in self.positions if p.status == "active"]

    def total_hedge_cost(self) -> float:
        return sum(p.cost for p in self.active_hedges())

    def recommend_hedges(self, symbols: List[str],
                         portfolio_value: Optional[float] = None) -> List[HedgePosition]:
        from options.common import OptionsChainFetcher
        pv = portfolio_value or 100_000.0
        fetcher = OptionsChainFetcher()
        results = []
        for sym in symbols:
            try:
                chains = fetcher.get_multi_expiry_chain(sym, dte_range=(30, 90))
                for exp, chain in chains.items():
                    spot = chain.underlying_price
                    put = self._find_otm_put(chain.puts, spot, 0.95)
                    if put is None:
                        continue
                    qty = self.size_hedge(pv, 1.0, spot)
                    pos = self.build_tail_hedge(sym, put, qty)
                    results.append(pos)
                    break
            except Exception:
                continue
        return results

    def stress_test(self, portfolio_positions: List[dict], spot: float) -> dict:
        from .scenario_engine import ScenarioEngine
        engine = ScenarioEngine()
        return {
            pct: engine.simulate_crash(portfolio_positions, spot, pct)
            for pct in [-0.10, -0.20, -0.30, -0.50]
        }

    def _find_otm_put(self, puts, spot: float, pct: float):
        target = spot * pct
        best = None
        best_dist = float("inf")
        for p in puts:
            if p.strike >= spot:
                continue
            dist = abs(p.strike - target)
            if dist < best_dist:
                best_dist = dist
                best = p
        return best
