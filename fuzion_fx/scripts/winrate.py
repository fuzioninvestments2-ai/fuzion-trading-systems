"""
scripts/winrate.py (fuzion_fx)
==============================
ACIERTO REAL acumulado de los 4 bots, medido sobre las senales YA RESUELTAS que cada
bot guarda en su sqlite (data/db/f*_memory.db, tabla signals con result win/loss/tie).

No inventa nada: cuenta lo que de verdad paso en vivo. Muestra el win-rate global, por
timeframe y por setup (asi se ve si el motor cuantico, el hibrido |H| o algun setup
puntual gana), y lo compara con el break-even de varios pagos (un win-rate por debajo
del break-even NO da plata aunque supere 50%).

Uso:
    python fuzion_fx/scripts/winrate.py
    python fuzion_fx/scripts/winrate.py --min 10     # solo setups con >=10 resueltas
Test: fuzion_fx/tests/test_winrate.py (sin red).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any, Dict, List, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.config import ROOT                                    # noqa: E402

BOTS = [("f1_m1", "1m"), ("f2_m2", "2m"), ("f3_m3", "3m"), ("f4_m5", "5m")]


def _db_path(bot_id: str) -> str:
    return os.path.join(ROOT, "data", "db", f"{bot_id}_memory.db")


def leer_signals(path: str) -> List[Dict[str, Any]]:
    """Filas resueltas (result win/loss/tie) de una db. [] si no existe/vacia."""
    if not os.path.exists(path):
        return []
    try:
        conn = sqlite3.connect(path)
        cur = conn.execute(
            "SELECT timeframe, setup_id, result FROM signals "
            "WHERE resolved=1 AND result IN ('win','loss','tie')")
        filas = [{"timeframe": r[0], "setup_id": r[1], "result": r[2]}
                 for r in cur.fetchall()]
        conn.close()
        return filas
    except sqlite3.Error:
        return []


def _tasa(filas: List[Dict[str, Any]]) -> Tuple[int, int, int, float]:
    """(wins, losses, ties, win_pct) — win_pct sobre win+loss (ties no cuentan)."""
    wins = sum(1 for f in filas if f["result"] == "win")
    losses = sum(1 for f in filas if f["result"] == "loss")
    ties = sum(1 for f in filas if f["result"] == "tie")
    decididas = wins + losses
    return wins, losses, ties, (wins / decididas * 100.0 if decididas else 0.0)


def _agrupar(filas: List[Dict[str, Any]], clave: str
             ) -> Dict[str, List[Dict[str, Any]]]:
    g: Dict[str, List[Dict[str, Any]]] = {}
    for f in filas:
        g.setdefault(str(f.get(clave)), []).append(f)
    return g


def break_even(pago_pct: float) -> float:
    """Win-rate minimo para no perder con ese pago: 100/(1+pago/100)."""
    return 100.0 / (1.0 + pago_pct / 100.0)


def reporte(min_n: int = 5) -> Dict[str, Any]:
    todas: List[Dict[str, Any]] = []
    por_bot: Dict[str, Any] = {}
    for bot_id, tf in BOTS:
        filas = leer_signals(_db_path(bot_id))
        todas.extend(filas)
        w, l, t, pct = _tasa(filas)
        por_bot[tf] = {"n": w + l, "wins": w, "losses": l, "ties": t, "win_pct": pct}
    w, l, t, pct = _tasa(todas)
    por_setup = {}
    for sid, fs in _agrupar(todas, "setup_id").items():
        ww, ll, tt, pp = _tasa(fs)
        if ww + ll >= min_n:
            por_setup[sid] = {"n": ww + ll, "win_pct": pp}
    return {
        "global": {"n": w + l, "wins": w, "losses": l, "ties": t, "win_pct": pct},
        "por_bot": por_bot,
        "por_setup": dict(sorted(por_setup.items(),
                                 key=lambda kv: kv[1]["n"], reverse=True)),
        "min_n": min_n,
    }


def _imprimir(rep: Dict[str, Any]) -> None:
    g = rep["global"]
    print("=" * 60)
    print("ACIERTO REAL acumulado (senales resueltas en vivo)")
    print("=" * 60)
    print(f"  GLOBAL: {g['win_pct']:.1f}%  ({g['wins']}W / {g['losses']}L"
          f" / {g['ties']}tie · n={g['n']})")
    print("  Break-even: pago 80% -> 55.6% · 70% -> 58.8% · 60% -> 62.5%")
    print("  (win-rate por DEBAJO del break-even NO da plata aunque pase 50%)")
    print("-" * 60)
    print("  Por timeframe:")
    for tf, s in rep["por_bot"].items():
        print(f"    {tf:3}: {s['win_pct']:5.1f}%  ({s['wins']}W/{s['losses']}L · n={s['n']})")
    print("-" * 60)
    print(f"  Por setup (>= {rep['min_n']} resueltas):")
    if not rep["por_setup"]:
        print("    (aun sin setups con muestra suficiente — deja correr)")
    for sid, s in rep["por_setup"].items():
        print(f"    {s['win_pct']:5.1f}%  n={s['n']:4}  {sid}")
    print("=" * 60)
    if g["n"] < 30:
        print("  NOTA: muestra chica (<30). No concluir todavia; deja correr.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Win-rate real acumulado de los 4 bots.")
    ap.add_argument("--min", type=int, default=5, help="minimo de resueltas por setup")
    args = ap.parse_args()
    _imprimir(reporte(min_n=args.min))


if __name__ == "__main__":
    main()
