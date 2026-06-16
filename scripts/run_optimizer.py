#!/usr/bin/env python3
"""
CLI del optimizador de parámetros.

Ejemplos:
    # Optimiza todas las cripto (datos diarios, 5 años)
    python scripts/run_optimizer.py --class crypto

    # Optimiza símbolos concretos
    python scripts/run_optimizer.py --symbols NVDA TSLA AAPL --period 5y

    # Todo el universo, intradía 5m (yfinance limita a ~60 días en 5m)
    python scripts/run_optimizer.py --class all --interval 5m --period 60d

    # Más combinaciones probadas
    python scripts/run_optimizer.py --class forex --samples 200
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.optimizer import Optimizer


def main():
    ap = argparse.ArgumentParser(description="QUANT BOT v5 — Optimizador")
    ap.add_argument("--symbols", nargs="+", help="Símbolos concretos (yfinance)")
    ap.add_argument("--class", dest="asset_class", default="all",
                    choices=["all", "stocks", "indices", "futures", "forex", "crypto", "auto"],
                    help="Clase de activo del universo")
    ap.add_argument("--interval", default="1d", help="1d, 1h, 15m, 5m...")
    ap.add_argument("--period", default="5y", help="5y, 2y, 60d...")
    ap.add_argument("--samples", type=int, default=120, help="Combinaciones a probar")
    ap.add_argument("--top", type=int, default=15, help="Mejores a mostrar/guardar")
    ap.add_argument("--no-save", action="store_true", help="No guardar JSON")
    args = ap.parse_args()

    opt = Optimizer()
    report = opt.run(symbols=args.symbols, asset_class=args.asset_class,
                     interval=args.interval, period=args.period,
                     n_samples=args.samples, top=args.top)

    print("\n" + "=" * 78)
    print(f"  MEJORES CONFIGURACIONES — clase={args.asset_class} "
          f"interval={args.interval} period={args.period}")
    print(f"  Símbolos: {', '.join(report['symbols'])}")
    print("=" * 78)
    header = f"{'#':>2}  {'score':>7}  {'PF':>5}  {'win%':>5}  {'maxDD':>6}  {'ret%':>7}  {'trades':>6}  params"
    print(header)
    print("-" * 78)
    for i, r in enumerate(report["top"], 1):
        p = r["params"]
        ps = f"sl{p.get('atr_sl_mult')} rr{p.get('rr')} conf{p.get('min_confidence')} adx{p.get('adx_min')}"
        print(f"{i:>2}  {r['avg_growth_score']:>7.3f}  {r['avg_profit_factor']:>5.2f}  "
              f"{r['avg_win_rate']*100:>5.1f}  {r['avg_max_drawdown']*100:>6.2f}  "
              f"{r['avg_net_return']*100:>7.2f}  {r['total_trades']:>6}  {ps}")
    print("-" * 78)
    print("  growth_score = expectativa x muestra / (1 + drawdown). NO premia win rate.")

    if not args.no_save:
        path = opt.save(report)
        print(f"\n  Guardado: {path}")


if __name__ == "__main__":
    main()
