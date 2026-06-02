"""Stress testing — Monte Carlo + crash injection + gap simulation."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import numpy as np
import pandas as pd


@dataclass
class MonteCarloResult:
    median_return: float
    percentile_5: float
    percentile_95: float
    prob_ruin: float
    simulations: int
    equity_paths: List[List[float]] = field(default_factory=list)


@dataclass
class CrashResult:
    scenario: str
    original_return: float
    stressed_return: float
    max_drawdown_stressed: float
    recovery_bars: int


@dataclass
class GapResult:
    gap_pct: float
    positions_affected: int
    total_loss: float
    total_loss_pct: float


CRASH_SCENARIOS = {
    "covid_2020": {"drop_pct": -0.34, "duration_bars": 23, "name": "COVID March 2020"},
    "flash_crash_2010": {"drop_pct": -0.092, "duration_bars": 1, "name": "Flash Crash 2010"},
    "gfc_2008": {"drop_pct": -0.57, "duration_bars": 340, "name": "GFC 2008"},
    "vix_explosion_2018": {"drop_pct": -0.12, "duration_bars": 2, "name": "VIX Explosion Feb 2018"},
}


class StressTester:

    def monte_carlo(self, trades: List[dict], n_simulations: int = 10_000,
                    initial_equity: float = 100_000) -> MonteCarloResult:
        if not trades:
            return MonteCarloResult(0, 0, 0, 1.0, n_simulations)

        pnl_pcts = np.array([t.get("pnl_pct", 0) for t in trades])
        n_trades = len(trades)
        final_equities = []
        sample_paths = []

        rng = np.random.default_rng(42)
        for _ in range(n_simulations):
            sampled = rng.choice(pnl_pcts, size=n_trades, replace=True)
            equity = initial_equity
            path = [equity]
            for r in sampled:
                equity *= (1 + r)
                path.append(equity)
            final_equities.append(equity)
            if len(sample_paths) < 100:
                sample_paths.append(path)

        arr = np.array(final_equities)
        prob_ruin = float((arr < initial_equity * 0.5).mean())

        return MonteCarloResult(
            median_return=round(float(np.median(arr) / initial_equity - 1), 4),
            percentile_5=round(float(np.percentile(arr, 5) / initial_equity - 1), 4),
            percentile_95=round(float(np.percentile(arr, 95) / initial_equity - 1), 4),
            prob_ruin=round(prob_ruin, 4),
            simulations=n_simulations,
            equity_paths=sample_paths[:10],
        )

    def crash_injection(self, equity_curve: pd.Series,
                         crash_scenarios: List[str] = None) -> List[CrashResult]:
        scenarios = crash_scenarios or list(CRASH_SCENARIOS.keys())
        results = []
        original_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)

        for scenario_key in scenarios:
            scenario = CRASH_SCENARIOS.get(scenario_key)
            if not scenario:
                continue

            stressed = equity_curve.copy()
            # Inyectar crash en el punto medio
            mid = len(stressed) // 2
            drop = scenario["drop_pct"]
            duration = min(scenario["duration_bars"], len(stressed) - mid)
            for i in range(duration):
                idx = mid + i
                daily_drop = drop / duration
                stressed.iloc[idx:] *= (1 + daily_drop)

            stressed_return = float(stressed.iloc[-1] / stressed.iloc[0] - 1)
            roll_max = stressed.cummax()
            drawdown = float((stressed / roll_max - 1).min())

            # Recovery
            in_dd = (stressed < stressed.iloc[:mid].max())
            recovery = int(in_dd.iloc[mid:].sum())

            results.append(CrashResult(
                scenario=scenario["name"],
                original_return=round(original_return, 4),
                stressed_return=round(stressed_return, 4),
                max_drawdown_stressed=round(drawdown, 4),
                recovery_bars=recovery,
            ))
        return results

    def gap_simulation(self, positions: List[dict], gap_sizes: List[float]) -> List[GapResult]:
        results = []
        for gap_pct in gap_sizes:
            total_loss = 0.0
            affected = 0
            for pos in positions:
                direction = pos.get("direction", "LONG")
                equity = pos.get("equity", 10_000)
                size_pct = pos.get("size_pct", 0.05)
                stop_loss = pos.get("stop_loss", 0.02)
                position_value = equity * size_pct

                if direction == "LONG" and gap_pct < 0:
                    loss = position_value * abs(gap_pct)
                    total_loss += loss
                    affected += 1
                elif direction == "SHORT" and gap_pct > 0:
                    loss = position_value * abs(gap_pct)
                    total_loss += loss
                    affected += 1

            total_equity = sum(p.get("equity", 10_000) for p in positions) or 1
            results.append(GapResult(
                gap_pct=gap_pct,
                positions_affected=affected,
                total_loss=round(total_loss, 2),
                total_loss_pct=round(total_loss / total_equity, 4),
            ))
        return results
