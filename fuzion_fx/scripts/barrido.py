"""
scripts/barrido.py (fuzion_fx)
==============================
BARRIDO de configuraciones del backtest de la foto completa sobre TU historial
real (candles_real de po_candles.db), SIN mirar el futuro. Antes de concluir "no
hay borde", AGOTA lo medible: prueba varios HORIZONTES (1m..5m) y UMBRALES de
convergencia, agrega los 22 pares y reporta el acierto GLOBAL y FUERTES de cada
combinacion.

PORQUE: a 1m el ruido puede tapar la señal; y un umbral mas exigente emite menos
pero quiza mejor. El barrido dice con NUMERO si alguna config cruza el break-even
de binarias, en vez de suponerlo.

Break-even (necesitas ganar mas que esto para no perder, segun payout):
    payout 92% -> 52.1% | 85% -> 54.1% | 82% -> 54.9% | 80% -> 55.6%.
Marca ★ si GLOBAL o FUERTES supera 53% (zona util con payout alto).

    python fuzion_fx/scripts/barrido.py            # todos los pares
    python fuzion_fx/scripts/barrido.py EUR/USD    # un par
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
BASE_TF = 60
MIN_VELAS_BT = 120

# Combinaciones a barrer: (horizonte en velas base, umbral de convergencia).
HORIZONTES = [1, 2, 3, 5]              # 1m, 2m, 3m, 5m (base 60s)
UMBRALES = [0.35, 0.50, 0.65]         # laxo, medio, exigente
UTIL = 53.0                           # zona util con payout alto (marca ★)


def _serie(conn, pair: str, tf: int):
    rows = conn.execute(
        """SELECT open, high, low, close FROM candles_real
           WHERE pair=? AND tf=? ORDER BY ts ASC""", (pair, tf)).fetchall()
    if len(rows) < MIN_VELAS_BT:
        return None
    return {"open": [r[0] for r in rows], "high": [r[1] for r in rows],
            "low": [r[2] for r in rows], "close": [r[3] for r in rows]}


def _agrega(conn, pares, horizonte, umbral):
    """Corre el backtest de cada par con esa config y suma los conteos globales."""
    w = l = fw = fl = 0
    for pair in pares:
        base = _serie(conn, pair, BASE_TF)
        if base is None:
            continue
        r = backtest_convergencia(base, BASE_TF, _CFG["indicators"], _CFG["signal"],
                                  umbral=umbral, min_tf=3, min_fuerza=0.0,
                                  horizonte=horizonte)
        w += r["wins"]; l += r["losses"]
        ff = r["by_fuerza"]["fuertes"]
        fw += ff["wins"]; fl += ff["trades"] - ff["wins"]
    return w, l, fw, fl


def _pct(w, l):
    t = w + l
    return (round(100.0 * w / t, 1), t) if t else (None, 0)


def main() -> None:
    global _CFG
    if not os.path.exists(DB):
        print("No hay po_candles.db todavia. Deja el colector juntando historial.")
        return
    _CFG = get_bot_config("f1_m1")
    pares = [sys.argv[1]] if len(sys.argv) > 1 else _CFG["pairs"]
    conn = sqlite3.connect(DB)

    print("BARRIDO foto completa · agrega todos los pares · sin mirar futuro")
    print(f"Break-even payout 82% = 54.9% · 92% = 52.1% · zona util (★) > {UTIL}%\n")
    print(f"{'horizonte':>9} {'umbral':>7} {'GLOBAL':>14} {'FUERTES':>14}")
    mejor = None
    for h in HORIZONTES:
        for u in UMBRALES:
            w, l, fw, fl = _agrega(conn, pares, h, u)
            gp, gt = _pct(w, l)
            fp, ft = _pct(fw, fl)
            g_txt = f"{gp}% ({gt})" if gp is not None else "sin muestra"
            f_txt = f"{fp}% ({ft})" if fp is not None else "—"
            star = " ★" if (gp and gp > UTIL) or (fp and fp > UTIL) else ""
            print(f"{str(h)+'m':>9} {u:>7} {g_txt:>14} {f_txt:>14}{star}")
            if gp is not None and (mejor is None or gp > mejor[0]):
                mejor = (gp, gt, h, u)
    conn.close()

    print("\n" + "=" * 56)
    if mejor:
        gp, gt, h, u = mejor
        print(f"MEJOR GLOBAL: {gp}% ({gt}) con horizonte {h}m, umbral {u}")
        if gp > UTIL:
            print("Cruza la zona util: hay una config con borde medible. Vale calibrar ahi.")
        else:
            print("Ninguna config cruza el break-even. El borde direccional NO aparece"
                  " en esta data — la conclusion honesta se sostiene.")
    else:
        print("Sin muestra suficiente. Deja el colector juntando mas velas.")


if __name__ == "__main__":
    main()
