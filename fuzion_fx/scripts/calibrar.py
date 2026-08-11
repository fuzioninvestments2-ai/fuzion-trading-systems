"""
scripts/calibrar.py (fuzion_fx)
===============================
Calibra los umbrales del motor (RSI, Bollinger, confirmaciones) por BACKTEST
sobre el historial real (`po_candles.db`), no a ojo. Para un bot (timeframe),
barre una grilla de configuraciones, corre el backtester en los 22 pares y arma
la FRONTERA acierto-vs-frecuencia, para que vos elijas el punto.

PORQUE: subir la frecuencia afloja los filtros, y mas señales NO implica mas
aciertos. La unica forma honesta de elegir umbrales es medir el win-rate y las
señales/hora que cada config produce sobre los datos ya recolectados.

Uso (en tu PC, con el colector habiendo juntado historial):
    python -m scripts.calibrar f1_m1
    python -m scripts.calibrar f4_m5 --min-velas 300 --objetivo-sph 6 --min-winrate 55

No escribe la config: imprime la tabla y el snippet YAML para que lo pegues vos.
El nucleo (`evaluar_grilla`) es puro y se testea sin red.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.backtester import backtest_series, combinar   # noqa: E402

# Grilla por defecto. Bandas RSI de mas estricta (extremos) a mas suelta
# (cercana a la media); bb_std de normal a mas sensible; confirmaciones 3 y 2.
GRILLA_DEFAULT: Dict[str, List[Any]] = {
    "rsi_bands": [(30, 70), (40, 60), (45, 55)],
    "bb_std": [2.0, 1.5],
    "min_conf": [3, 2],
}


def _configs(grilla: Dict[str, List[Any]]):
    """Producto cartesiano de la grilla -> lista de configs de indicadores/senal."""
    for ov, ob in grilla["rsi_bands"]:
        for bb in grilla["bb_std"]:
            for mc in grilla["min_conf"]:
                yield {
                    "rsi_oversold": ov,
                    "rsi_overbought": ob,
                    "bb_std": bb,
                    "min_confirmations": mc,
                    "etiqueta": f"RSI{ov}/{ob} BB{bb} conf{mc}",
                }


def evaluar_config(series_por_par: Dict[str, Dict[str, Sequence[float]]],
                   base_ind: Dict[str, Any], timeframe_seconds: int,
                   cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Corre el backtester en cada par con una config y agrega el resultado.
    Agrega `sph_bot`: tasa cruda POR BOT = (tasa por par) * nro de pares (antes de
    anti-dup y del tope/hora, que la recortan aguas abajo)."""
    ind = {**base_ind, "rsi_oversold": cfg["rsi_oversold"],
           "rsi_overbought": cfg["rsi_overbought"], "bb_std": cfg["bb_std"]}
    sig = {"min_confirmations": cfg["min_confirmations"]}
    por_par = [backtest_series(s, ind, sig, timeframe_seconds)
               for s in series_por_par.values() if len(s.get("close", [])) > 3]
    agg = combinar(por_par)
    agg["etiqueta"] = cfg["etiqueta"]
    agg["cfg"] = cfg
    agg["sph_bot"] = round(agg["signals_per_hour"] * agg["pares"], 2)
    return agg


def evaluar_grilla(series_por_par: Dict[str, Dict[str, Sequence[float]]],
                   base_ind: Dict[str, Any], timeframe_seconds: int,
                   grilla: Optional[Dict[str, List[Any]]] = None) -> List[Dict[str, Any]]:
    """Evalua toda la grilla. Devuelve filas ordenadas por win-rate desc (None al
    final), y a igual win-rate, por frecuencia desc."""
    grilla = grilla or GRILLA_DEFAULT
    filas = [evaluar_config(series_por_par, base_ind, timeframe_seconds, c)
             for c in _configs(grilla)]
    filas.sort(key=lambda r: (r["win_pct"] is not None, r["win_pct"] or 0.0,
                              r["sph_bot"]), reverse=True)
    return filas


def recomendar(filas: List[Dict[str, Any]], objetivo_sph: float,
               min_winrate: float, min_muestra: int) -> Optional[Dict[str, Any]]:
    """
    Elige la config con MAYOR win-rate que ademas cumpla:
      - muestra suficiente (wins+losses >= min_muestra), para que el % sea creible,
      - win-rate >= min_winrate (no aflojar por debajo de lo util),
      - frecuencia por bot >= objetivo_sph (que efectivamente de mas señales).
    None si ninguna cumple (mejor no cambiar que degradar a ciegas).
    """
    candidatas = [r for r in filas
                  if r["win_pct"] is not None
                  and (r["wins"] + r["losses"]) >= min_muestra
                  and r["win_pct"] >= min_winrate
                  and r["sph_bot"] >= objetivo_sph]
    if not candidatas:
        return None
    # Mayor win-rate; a empate, la de mas frecuencia.
    candidatas.sort(key=lambda r: (r["win_pct"], r["sph_bot"]), reverse=True)
    return candidatas[0]


# --------------------------------------------------------------- lectura de datos
def leer_series(db_path: str, pairs: List[str], timeframe_seconds: int,
                max_velas: int) -> Dict[str, Dict[str, Sequence[float]]]:
    """Lee del po_candles.db las ultimas `max_velas` de cada par al timeframe dado."""
    from collector.candle_store import CandleStore
    store = CandleStore(db_path)
    series: Dict[str, Dict[str, Sequence[float]]] = {}
    try:
        for p in pairs:
            velas = store.get_candles(p, timeframe_seconds, max_velas)
            if velas and len(velas.get("close", [])) > 3:
                series[p] = velas
    finally:
        store.close()
    return series


def _fmt(v: Any) -> str:
    return "  s/m" if v is None else f"{v:>5.1f}"


def main(argv: Optional[List[str]] = None) -> int:
    from core.config import get_bot_config, ROOT

    ap = argparse.ArgumentParser(description="Calibra umbrales del motor por backtest.")
    ap.add_argument("bot_id", help="f1_m1 | f2_m2 | f3_m3 | f4_m5")
    ap.add_argument("--min-velas", type=int, default=200,
                    help="minimo de velas por par para incluirlo (default 200)")
    ap.add_argument("--max-velas", type=int, default=5000,
                    help="velas a leer por par (default 5000)")
    ap.add_argument("--objetivo-sph", type=float, default=6.0,
                    help="señales/hora por bot objetivo (~1 cada 10 min, default 6)")
    ap.add_argument("--min-winrate", type=float, default=55.0,
                    help="win-rate minimo aceptable para recomendar (default 55)")
    ap.add_argument("--min-muestra", type=int, default=30,
                    help="resueltos minimos para creer el win-rate (default 30)")
    args = ap.parse_args(argv)

    cfg = get_bot_config(args.bot_id)
    db_path = os.path.join(ROOT, "data", "db", "po_candles.db")
    tf = int(cfg["timeframe_seconds"])
    print(f"Calibrando {cfg['name']} (tf={tf}s) sobre {db_path}")

    series = leer_series(db_path, cfg["pairs"], tf, args.max_velas)
    series = {p: s for p, s in series.items()
              if len(s.get("close", [])) >= args.min_velas}
    if not series:
        print(f"Sin historial suficiente (>= {args.min_velas} velas/par). "
              f"Deja correr el colector mas tiempo y reintenta.")
        return 1
    total_velas = sum(len(s["close"]) for s in series.values())
    print(f"Pares con datos: {len(series)}  ·  velas totales: {total_velas}\n")

    filas = evaluar_grilla(series, cfg["indicators"], tf)

    print(f"{'config':<24} {'winrate':>8} {'resueltos':>10} {'sph/bot':>9} {'sph/par':>8}")
    print("-" * 63)
    for r in filas:
        resueltos = r["wins"] + r["losses"]
        print(f"{r['etiqueta']:<24} {_fmt(r['win_pct'])}%  {resueltos:>9} "
              f"{r['sph_bot']:>9.1f} {r['signals_per_hour']:>8.2f}")

    print()
    rec = recomendar(filas, args.objetivo_sph, args.min_winrate, args.min_muestra)
    actual = cfg["indicators"]
    ov_act = actual.get("rsi_oversold", 30)
    ob_act = actual.get("rsi_overbought", 70)
    bb_act = actual.get("bb_std", 2.0)
    mc_act = cfg["signal"].get("min_confirmations", 3)
    print(f"Config actual: RSI{ov_act}/{ob_act} BB{bb_act} conf{mc_act}")
    if rec is None:
        print(f"NO hay config que cumpla win-rate>={args.min_winrate}% y "
              f"sph/bot>={args.objetivo_sph} con muestra>={args.min_muestra}.")
        print("Recomendacion: NO aflojar (junta mas historial o baja el objetivo).")
        return 0

    c = rec["cfg"]
    print(f"RECOMENDADA: {rec['etiqueta']}  ->  win-rate {rec['win_pct']}%  ·  "
          f"~{rec['sph_bot']:.0f} señales/hora/bot (crudo)")
    print("\nPara aplicar SOLO a este bot, en config/bots.yaml (indicators y signal):")
    print(f"    indicators: {{... rsi_oversold: {c['rsi_oversold']}, "
          f"rsi_overbought: {c['rsi_overbought']}, bb_std: {c['bb_std']} ...}}")
    print(f"    signal: {{min_confirmations: {c['min_confirmations']}, ...}}")
    print("\nRevisa el win-rate antes de fijarlo. No toca M1/M2 salvo que corras "
          "la calibracion para ellos y decidas cambiarlos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
