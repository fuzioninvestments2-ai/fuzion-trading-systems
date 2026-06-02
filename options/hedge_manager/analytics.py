"""Analytics de coberturas."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from options.hedge_manager.hedge_engine import HedgePosition


@dataclass
class HedgeAnalytics:
    total_hedges: int
    active_hedges: int
    total_cost: float
    avg_protection: float
    hedge_types: dict


def compute_analytics(positions: List[HedgePosition]) -> HedgeAnalytics:
    active = [p for p in positions if p.status == "active"]
    types: dict = {}
    for p in active:
        types[p.hedge_type] = types.get(p.hedge_type, 0) + 1
    avg_prot = sum(p.protection_level for p in active) / max(len(active), 1)
    return HedgeAnalytics(
        total_hedges=len(positions),
        active_hedges=len(active),
        total_cost=sum(p.cost for p in active),
        avg_protection=avg_prot,
        hedge_types=types,
    )
