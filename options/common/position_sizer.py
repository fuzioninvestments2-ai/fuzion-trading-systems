"""Position Sizer — Kelly Criterion adaptado para opciones."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from .chain_models import OptionContract


@dataclass
class PositionSize:
    contracts: int
    max_risk: float
    size_pct: float
    kelly_fraction: float


@dataclass
class OptionPosition:
    strategy_type: str
    contracts: int
    max_loss_per_contract: float


@dataclass
class PortfolioRisk:
    total_max_loss: float
    total_max_loss_pct: float
    positions: int


class OptionsPositionSizer:
    MAX_SINGLE_POSITION_PCT = 0.05

    def size_position(self, strategy_type: str, max_loss: float, account_size: float,
                      risk_per_trade: float = 0.02,
                      regime=None) -> PositionSize:
        if account_size <= 0 or max_loss <= 0:
            return PositionSize(contracts=0, max_risk=0.0, size_pct=0.0, kelly_fraction=0.0)

        # Regime multiplier
        regime_mult = 1.0
        if regime is not None:
            label = getattr(regime, "label", None)
            if label:
                lv = label.value if hasattr(label, "value") else str(label)
                regime_mult = {"crash": 0.0, "bear": 0.5, "neutral": 1.0,
                               "bull": 1.0, "euphoria": 0.7}.get(lv, 1.0)

        # Kelly (win_rate=0.55, win/loss=1.33 como baseline)
        win_rate = 0.55
        win_loss_ratio = 1.33
        kelly = win_rate - (1 - win_rate) / win_loss_ratio
        kelly = max(0.0, min(kelly * 0.5, 0.25))  # Half Kelly, cap 25%

        risk_budget = account_size * min(risk_per_trade, 0.02) * regime_mult
        max_by_risk = risk_budget / max_loss
        max_by_position = (account_size * self.MAX_SINGLE_POSITION_PCT) / max_loss
        max_by_kelly = (account_size * kelly) / max_loss

        contracts = max(1, int(min(max_by_risk, max_by_position, max_by_kelly)))
        actual_risk = contracts * max_loss
        size_pct = actual_risk / account_size

        return PositionSize(
            contracts=contracts,
            max_risk=round(actual_risk, 2),
            size_pct=round(size_pct, 4),
            kelly_fraction=round(kelly, 4),
        )

    def portfolio_risk(self, positions: List[OptionPosition]) -> PortfolioRisk:
        total = sum(p.contracts * p.max_loss_per_contract for p in positions)
        return PortfolioRisk(
            total_max_loss=round(total, 2),
            total_max_loss_pct=0.0,
            positions=len(positions),
        )
