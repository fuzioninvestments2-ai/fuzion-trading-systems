#!/usr/bin/env python
"""Script CLI para ejecutar backtests."""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml
from data.market_data import MarketData
from backtest.backtester import WalkForwardBacktester

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--equity", type=float, default=100_000)
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    print(f"[FUZION Backtest] {args.symbol} | {args.start} → {args.end}")
    md = MarketData({})
    bars = md.get_bars_range(args.symbol, args.start, args.end)
    print(f"Barras: {len(bars)}")

    bt = WalkForwardBacktester(config.get("backtest", {}))
    result = bt.run(bars, args.equity)
    p = result.performance

    print(f"\n{'='*50}")
    print(f"Total Return:   {p.total_return:.2%}")
    print(f"CAGR:           {p.cagr:.2%}")
    print(f"Sharpe:         {p.sharpe_ratio:.2f}  |  Max DD: {p.max_drawdown:.2%}")
    print(f"Win Rate:       {p.win_rate:.2%}")
    print(f"Profit Factor:  {p.profit_factor:.2f}")
    print(f"Total Trades:   {p.total_trades}")
    print(f"\nBenchmarks:")
    for k, v in result.benchmarks.items():
        print(f"  {k}: {v:.2%}")
    print(f"{'='*50}")
