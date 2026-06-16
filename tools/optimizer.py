"""
Optimizador de parámetros — busca configuraciones con mejor EXPECTATIVA y menor
DRAWDOWN (no mejor win rate) sobre el universo multi-activo.

Uso típico desde código:
    from tools.optimizer import Optimizer
    opt = Optimizer()
    report = opt.run(symbols=["NVDA", "BTC-USD"], asset_class="auto",
                     interval="1d", period="5y", n_samples=120)
    opt.save(report)

Para CLI ver scripts/run_optimizer.py.
"""
from __future__ import annotations

import itertools
import json
import os
import random
from dataclasses import replace
from datetime import datetime
from typing import Dict, List, Optional

import yaml

from tools.strategy_core import StrategyParams, backtest, BacktestResult


# Espacio de búsqueda por defecto (ajústalo a tu gusto)
DEFAULT_SPACE = {
    "ema_slow": [20, 50],
    "sma_trend": [100, 200],
    "adx_min": [20.0, 25.0, 30.0],
    "atr_sl_mult": [1.0, 1.5, 2.0, 2.5],
    "rr": [1.5, 2.0, 2.5, 3.0],
    "min_confidence": [50.0, 60.0, 70.0, 80.0],
    "breakeven_r": [0.8, 1.0, 1.5],
    "timeout_bars": [15, 25, 40],
}

# Presets de coste/volatilidad por clase (espejo de config/universe.yaml)
CLASS_PRESETS = {
    "stocks":   dict(commission=0.0002, slippage=0.0002, atr_min_pct=0.10),
    "indices":  dict(commission=0.0002, slippage=0.0002, atr_min_pct=0.08),
    "futures":  dict(commission=0.0001, slippage=0.0003, atr_min_pct=0.10),
    "forex":    dict(commission=0.00008, slippage=0.0001, atr_min_pct=0.05),
    "crypto":   dict(commission=0.00075, slippage=0.0005, atr_min_pct=0.15),
    "auto":     dict(),
}


class Optimizer:
    def __init__(self, universe_path: str = "config/universe.yaml",
                 results_dir: str = "results"):
        self.universe_path = universe_path
        self.results_dir = results_dir
        # Carga diferida de MarketData (yfinance solo al descargar datos)
        from data.market_data import MarketData
        self.md = MarketData({})
        self._universe = self._load_universe()

    # ------------------------------------------------------------------
    def _load_universe(self) -> dict:
        if os.path.exists(self.universe_path):
            with open(self.universe_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def class_for_symbol(self, symbol: str) -> str:
        for cls in ("stocks", "indices", "futures", "forex", "crypto"):
            if symbol in (self._universe.get(cls) or []):
                return cls
        return "auto"

    def symbols_for_class(self, asset_class: str) -> List[str]:
        if asset_class in ("all", "auto"):
            out: List[str] = []
            for cls in ("stocks", "indices", "futures", "forex", "crypto"):
                out += self._universe.get(cls) or []
            return out
        return self._universe.get(asset_class) or []

    # ------------------------------------------------------------------
    def _sample_params(self, space: dict, n_samples: int) -> List[dict]:
        keys = list(space.keys())
        grid_size = 1
        for k in keys:
            grid_size *= len(space[k])
        if grid_size <= n_samples:
            combos = list(itertools.product(*[space[k] for k in keys]))
            return [dict(zip(keys, c)) for c in combos]
        # muestreo aleatorio sin repetición
        seen, out = set(), []
        attempts = 0
        while len(out) < n_samples and attempts < n_samples * 20:
            attempts += 1
            c = tuple(random.choice(space[k]) for k in keys)
            if c not in seen:
                seen.add(c)
                out.append(dict(zip(keys, c)))
        return out

    def _base_params(self, asset_class: str) -> StrategyParams:
        preset = CLASS_PRESETS.get(asset_class, {})
        return StrategyParams(**preset)

    # ------------------------------------------------------------------
    def run(self, symbols: Optional[List[str]] = None, asset_class: str = "auto",
            interval: str = "1d", period: str = "5y", n_samples: int = 120,
            space: Optional[dict] = None, top: int = 15,
            min_trades_total: int = 20) -> dict:
        space = space or DEFAULT_SPACE
        symbols = symbols or self.symbols_for_class(asset_class)
        if not symbols:
            raise ValueError("No hay símbolos para optimizar.")

        # 1) Descarga datos una sola vez
        data: Dict[str, "pd.DataFrame"] = {}
        for sym in symbols:
            try:
                data[sym] = self.md.get_bars(sym, period=period, interval=interval)
            except Exception as e:
                print(f"[opt] skip {sym}: {e}")
        if not data:
            raise ValueError("No se pudo descargar ningún símbolo.")

        # 2) Genera combinaciones de parámetros
        param_sets = self._sample_params(space, n_samples)
        print(f"[opt] {len(data)} símbolos x {len(param_sets)} combinaciones "
              f"= {len(data) * len(param_sets)} backtests")

        # 3) Evalúa cada combinación sobre todos los símbolos
        results = []
        for idx, overrides in enumerate(param_sets):
            per_symbol = []
            for sym, df in data.items():
                base = self._base_params(self.class_for_symbol(sym)
                                         if asset_class in ("auto", "all") else asset_class)
                p = replace(base, **overrides)
                per_symbol.append(backtest(df, p, symbol=sym))
            agg = self._aggregate(overrides, per_symbol, min_trades_total)
            results.append(agg)
            if (idx + 1) % 25 == 0:
                print(f"[opt] {idx + 1}/{len(param_sets)} combinaciones evaluadas")

        results.sort(key=lambda r: r["avg_growth_score"], reverse=True)
        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "asset_class": asset_class,
            "interval": interval,
            "period": period,
            "symbols": list(data.keys()),
            "n_combinations": len(param_sets),
            "top": results[:top],
            "best": results[0] if results else None,
        }
        return report

    # ------------------------------------------------------------------
    def _aggregate(self, overrides: dict, per_symbol: List[BacktestResult],
                   min_trades_total: int) -> dict:
        scores = [r.growth_score for r in per_symbol]
        trades = sum(r.n_trades for r in per_symbol)
        wins = [r.win_rate for r in per_symbol if r.n_trades > 0]
        pfs = [r.profit_factor for r in per_symbol if r.n_trades > 0]
        dds = [r.max_drawdown for r in per_symbol if r.n_trades > 0]
        rets = [r.net_return for r in per_symbol if r.n_trades > 0]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        # Penaliza combinaciones con muy poca actividad agregada
        if trades < min_trades_total:
            avg_score *= 0.2
        return {
            "params": overrides,
            "avg_growth_score": round(avg_score, 4),
            "total_trades": trades,
            "avg_win_rate": round(sum(wins) / len(wins), 4) if wins else 0.0,
            "avg_profit_factor": round(sum(pfs) / len(pfs), 3) if pfs else 0.0,
            "avg_max_drawdown": round(sum(dds) / len(dds), 4) if dds else 0.0,
            "avg_net_return": round(sum(rets) / len(rets), 4) if rets else 0.0,
            "per_symbol": [r.to_dict() for r in per_symbol],
        }

    # ------------------------------------------------------------------
    def save(self, report: dict, name: Optional[str] = None) -> str:
        os.makedirs(self.results_dir, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        name = name or f"optimizer_{report.get('asset_class', 'run')}_{ts}.json"
        path = os.path.join(self.results_dir, name)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        return path
