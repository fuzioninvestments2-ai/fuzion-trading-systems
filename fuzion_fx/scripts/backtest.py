"""
scripts/backtest.py (fuzion_fx)
===============================
Corre el BACKTEST de la foto completa (convergencia multi-temporalidad + patrones
+ fuerza) sobre TU historial real de velas (candles_real de po_candles.db), SIN
mirar el futuro, y reporta el acierto GLOBAL y por FUERZA (fuertes vs debiles).
Asi el NUMERO dice si el borde es real, no el optimismo.

Usa la serie MAS FINA disponible por par (1m si hay) como base y resamplea a los
tiempos largos. Necesita historial acumulado (dejar el colector un rato). Sin red.

    python fuzion_fx/scripts/backtest.py            # todos los pares, tf base 60s
    python fuzion_fx/scripts/backtest.py EUR/USD    # un par
"""

from __future__ import annotations

import os
import sqlite3
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.config import get_bot_config, ROOT                     # noqa: E402
from core.backtester import backtest_convergencia                # noqa: E402

DB = os.path.join(ROOT, "data", "db", "po_candles.db")
BASE_TF = 60                          # serie base = 1m (la mas fina util para BT)
MIN_VELAS_BT = 120                    # minimo de velas base para que valga la pena


def _serie(conn, pair: str, tf: int):
    rows = conn.execute(
        """SELECT open, high, low, close FROM candles_real
           WHERE pair=? AND tf=? ORDER BY ts ASC""", (pair, tf)).fetchall()
    if len(rows) < MIN_VELAS_BT:
        return None
    return {"open": [r[0] for r in rows], "high": [r[1] for r in rows],
            "low": [r[2] for r in rows], "close": [r[3] for r in rows]}


def main() -> None:
    if not os.path.exists(DB):
        print("No hay po_candles.db todavia. Deja el colector juntando historial.")
        return
    cfg = get_bot_config("f1_m1")
    pares = [sys.argv[1]] if len(sys.argv) > 1 else cfg["pairs"]
    conn = sqlite3.connect(DB)

    print(f"BACKTEST foto completa (base {BASE_TF}s) · min_fuerza=0 (mide todo)\n")
    print(f"{'PAR':<10} {'velas':>6} {'señales':>8} {'ACIERTO':>8}   "
          f"{'FUERTES':>16}  {'DEBILES':>16}")
    tot_w = tot_l = 0
    fu_w = fu_l = de_w = de_l = 0
    for pair in pares:
        base = _serie(conn, pair, BASE_TF)
        if base is None:
            continue
        r = backtest_convergencia(base, BASE_TF, cfg["indicators"], cfg["signal"],
                                  umbral=0.35, min_tf=3, min_fuerza=0.0)
        fpct = r["win_pct"]
        ff = r["by_fuerza"]["fuertes"]; dd = r["by_fuerza"]["debiles"]
        f_txt = f"{ff['win_pct']}% ({ff['trades']})" if ff["trades"] else "—"
        d_txt = f"{dd['win_pct']}% ({dd['trades']})" if dd["trades"] else "—"
        print(f"{pair:<10} {len(base['close']):>6} {r['emissions']:>8} "
              f"{(str(fpct)+'%') if fpct is not None else '—':>8}   "
              f"{f_txt:>16}  {d_txt:>16}")
        tot_w += r["wins"]; tot_l += r["losses"]
        fu_w += ff["wins"]; fu_l += ff["trades"] - ff["wins"]
        de_w += dd["wins"]; de_l += dd["trades"] - dd["wins"]
    conn.close()

    def _p(w, l):
        t = w + l
        return f"{round(100.0*w/t,1)}% ({t})" if t else "sin muestra"
    print("\n" + "=" * 60)
    print(f"GLOBAL:   {_p(tot_w, tot_l)}")
    print(f"FUERTES:  {_p(fu_w, fu_l)}   <- confluencia alta")
    print(f"DEBILES:  {_p(de_w, de_l)}   <- confluencia baja")
    print("Si FUERTES > DEBILES, el borde de la confluencia es real.")


if __name__ == "__main__":
    main()
