"""
scripts/auditar_resolucion.py (fuzion_fx)
=========================================
AUDITA como se resolvieron (win/loss) las senales ya emitidas, cruzando la base
del bot (f*_memory.db) con las velas del colector (po_candles.db). Por cada senal
resuelta muestra:

  - entrada (hora y precio guardados),
  - vencimiento = ts_entrada + timeframe,
  - la vela que se USO de cierre (la que toma price_at: primera con ts >= venc.)
    y a cuantos segundos del vencimiento arranca esa vela (GAP),
  - la vela mas CERCANA al vencimiento (mejor estimacion del precio real ahi),
  - si el resultado CAMBIARIA usando esa vela cercana (win <-> loss).

PORQUE: si el cierre usado viene de una vela lejana/vieja (colector ralo: 22
pares rotando, ~1 vela cada ~3 min por par), el win/loss no refleja lo que paso
en la plataforma. Esta auditoria lo hace VISIBLE sobre datos reales, sin tocar
nada. Solo lectura.

Uso (en tu PC):
    python -m scripts.auditar_resolucion f4_m5
    python -m scripts.auditar_resolucion f1_m1 --n 50

Nucleo puro (auditar_senal) testeado sin red.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

_TF_SEG = {"1m": 60, "2m": 120, "3m": 180, "5m": 300}

# Vela = (ts_inicio, close, volume).
Vela = Tuple[int, float, float]


def vela_de_cierre(velas: Sequence[Vela], expiry: int) -> Optional[Vela]:
    """Replica price_at: PRIMERA vela con ts >= expiry (la que usa el bot hoy)."""
    for v in velas:                       # velas en orden cronologico ascendente
        if v[0] >= expiry:
            return v
    return None


def vela_mas_cercana(velas: Sequence[Vela], t: int) -> Optional[Vela]:
    """Vela cuyo ts esta MAS cerca de t (mejor estimacion del precio real en t)."""
    if not velas:
        return None
    return min(velas, key=lambda v: abs(v[0] - t))


def _resultado(direction: str, entry: float, exit_price: float) -> str:
    if exit_price == entry:
        return "tie"
    if direction == "CALL":
        return "win" if exit_price > entry else "loss"
    return "win" if exit_price < entry else "loss"


def auditar_senal(sig: Dict[str, Any], velas: Sequence[Vela],
                  tf_seg: int) -> Dict[str, Any]:
    """
    Audita UNA senal. `sig`: {ts, pair, direction, price, result}. `velas`: las
    del par+tf (cronologicas). Devuelve el detalle + si el resultado cambiaria con
    la vela mas cercana al vencimiento.
    """
    expiry = int(sig["ts"]) + tf_seg
    usada = vela_de_cierre(velas, expiry)
    cercana = vela_mas_cercana(velas, expiry)
    entry = float(sig["price"])

    d: Dict[str, Any] = {
        "ts": int(sig["ts"]), "pair": sig["pair"], "direction": sig["direction"],
        "entry": entry, "expiry": expiry, "result_guardado": sig.get("result"),
    }
    if usada is None:
        d.update({"close_usado": None, "gap_seg": None, "vol_usado": None})
    else:
        d.update({"close_usado": usada[1], "gap_seg": usada[0] - expiry,
                  "vol_usado": usada[2]})
    if cercana is None:
        d.update({"close_cercano": None, "gap_cercano_seg": None,
                  "result_recalculado": None, "cambia": None})
    else:
        rec = _resultado(sig["direction"], entry, cercana[1])
        d.update({"close_cercano": cercana[1],
                  "gap_cercano_seg": cercana[0] - expiry,
                  "result_recalculado": rec,
                  "cambia": (sig.get("result") in ("win", "loss")
                             and rec != sig.get("result"))})
    return d


# --------------------------------------------------------------- lectura de datos
def _leer_senales(db_path: str, n: int) -> List[Dict[str, Any]]:
    # Sin base aun (bot recien creado) -> sin senales, no es error.
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT ts, pair, timeframe, direction, price, result
               FROM signals WHERE resolved=1 AND result IN ('win','loss')
               ORDER BY ts DESC LIMIT ?""", (int(n),)).fetchall()
    except sqlite3.OperationalError:
        return []                          # tabla 'signals' inexistente todavia
    finally:
        conn.close()
    return [{"ts": r[0], "pair": r[1], "timeframe": r[2], "direction": r[3],
             "price": r[4], "result": r[5]} for r in rows]


def _leer_velas(candles_db: str, pair: str, tf_seg: int) -> List[Vela]:
    if not os.path.exists(candles_db):
        return []
    conn = sqlite3.connect(candles_db)
    try:
        rows = conn.execute(
            """SELECT ts, close, volume FROM candles
               WHERE pair=? AND tf=? ORDER BY ts ASC""",
            (pair, int(tf_seg))).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [(int(r[0]), float(r[1]), float(r[2] or 0.0)) for r in rows]


def _hhmm(ts: int) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def main(argv: Optional[List[str]] = None) -> int:
    from core.config import get_bot_config, ROOT

    ap = argparse.ArgumentParser(description="Audita la resolucion win/loss.")
    ap.add_argument("bot_id", help="f1_m1 | f2_m2 | f3_m3 | f4_m5")
    ap.add_argument("--n", type=int, default=30, help="ultimas N senales (default 30)")
    args = ap.parse_args(argv)

    cfg = get_bot_config(args.bot_id)
    tf_seg = int(cfg["timeframe_seconds"])
    candles_db = os.path.join(ROOT, "data", "db", "po_candles.db")
    senales = _leer_senales(cfg["db_path"], args.n)
    if not senales:
        print(f"{cfg['name']}: sin senales resueltas todavia.")
        return 0

    # Cache de velas por par (se leen una vez por par).
    velas_cache: Dict[str, List[Vela]] = {}
    filas = []
    for s in senales:
        p = s["pair"]
        if p not in velas_cache:
            velas_cache[p] = _leer_velas(candles_db, p, tf_seg)
        filas.append(auditar_senal(s, velas_cache[p], tf_seg))

    print(f"Auditoria {cfg['name']} (tf={tf_seg}s) · ultimas {len(filas)} resueltas")
    print(f"{'entrada':>7} {'par':<8} {'dir':<4} {'gap_cierre':>10} "
          f"{'result':>7} {'recalc':>7} {'cambia?':>8}")
    print("-" * 60)
    cambios = 0
    gaps = []
    for f in filas:
        gap = f["gap_seg"]
        gap_txt = "s/vela" if gap is None else f"{gap // 60}min"
        if gap is not None:
            gaps.append(gap)
        cambia = f["cambia"]
        if cambia:
            cambios += 1
        print(f"{_hhmm(f['ts']):>7} {f['pair']:<8} {f['direction']:<4} "
              f"{gap_txt:>10} {str(f['result_guardado']):>7} "
              f"{str(f['result_recalculado']):>7} {('SI' if cambia else ''):>8}")

    print("-" * 60)
    if gaps:
        gaps_ord = sorted(gaps)
        mediana = gaps_ord[len(gaps_ord) // 2]
        lejanas = sum(1 for g in gaps if g > tf_seg)
        print(f"GAP mediano vela-de-cierre vs vencimiento: {mediana // 60} min "
              f"({mediana}s). Idealmente ~0.")
        print(f"Resoluciones con vela de cierre a MAS de un timeframe del "
              f"vencimiento: {lejanas}/{len(gaps)}")
    print(f"Resultados que CAMBIARIAN usando la vela mas cercana al vencimiento: "
          f"{cambios}/{len(filas)}")
    if cambios:
        print("=> El win/loss guardado NO refleja el precio real al vencimiento. "
              "Hay que arreglar la resolucion antes de confiar en el win-rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
