"""
scripts/comparar_historial.py (fuzion_fx) — PASO 1
==================================================
Herramienta de SOLO LECTURA: baja el historial OHLC REAL de Pocket Option para un
par y lo confronta con lo que el colector guardo en po_candles.db para los mismos
timestamps. Cuantifica la divergencia (diferencia en pips por vela, % de velas con
gap > umbral) por timeframe. NO modifica el colector ni los bots: solo lee y
reporta.

PORQUE: el colector arma velas desde ticks ralos (22 pares rotando, ~1 vela cada
~3 min por par). Si esas velas divergen del precio real de PO, el win/loss y el
backtest se calculan sobre datos viciados y el win-rate sale inflado. Esta
herramienta lo mide con NUMEROS, sobre datos reales, antes de tocar nada.

IMPORTANTE (operacion): corre con el COLECTOR APAGADO. Pocket Option permite UNA
sola conexion por SSID; si el colector esta vivo, este script no podra conectar.

Uso (en tu PC, colector apagado):
    python -m scripts.comparar_historial EUR/USD
    python -m scripts.comparar_historial EUR/USD --umbral 1.0 --espera 6

Nucleo puro (comparar_velas) testeado sin red.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)
_REPO_ROOT = os.path.dirname(_RAIZ)
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)                 # para reutilizar bot/pocket_client.py

from collector.po_history import parse_history   # noqa: E402
from indicators.pips import pip_size             # noqa: E402

TIMEFRAMES = [60, 120, 180, 300]                 # M1, M2, M3, M5


# --------------------------------------------------------------- nucleo puro
def comparar_velas(velas_po: Sequence[Tuple[int, float]],
                   velas_col: Sequence[Tuple[int, float]],
                   pip: float, umbral_pips: float = 1.0) -> Dict[str, Any]:
    """
    Confronta dos series de velas por su timestamp (cierre vs cierre). Cada serie
    es [(ts, close), ...]. Devuelve metricas de divergencia en pips sobre los ts
    COMUNES (donde ambas tienen vela). `umbral_pips`: a partir de cuantos pips se
    considera "gap" relevante.
    """
    po = {int(ts): float(c) for ts, c in velas_po}
    col = {int(ts): float(c) for ts, c in velas_col}
    comunes = sorted(set(po) & set(col))

    diffs = [abs(po[ts] - col[ts]) / pip for ts in comunes] if pip else []
    con_gap = sum(1 for d in diffs if d > umbral_pips)
    n = len(diffs)
    ordenados = sorted(diffs)
    return {
        "n_po": len(po),
        "n_col": len(col),
        "n_comunes": n,
        "solo_po": len(set(po) - set(col)),
        "solo_col": len(set(col) - set(po)),
        "umbral_pips": umbral_pips,
        "con_gap": con_gap,
        "pct_con_gap": round(100.0 * con_gap / n, 1) if n else 0.0,
        "gap_medio_pips": round(sum(diffs) / n, 2) if n else 0.0,
        "gap_mediano_pips": round(ordenados[n // 2], 2) if n else 0.0,
        "gap_max_pips": round(max(diffs), 2) if diffs else 0.0,
    }


def _velas_close(parsed: Optional[Dict[str, Any]]) -> List[Tuple[int, float]]:
    """De la salida de parse_history a [(ts, close)] (indice 0=ts, 4=close)."""
    if not parsed:
        return []
    return [(v[0], v[4]) for v in parsed["velas"]]


def _col_close(candles: Optional[Dict[str, List[float]]]) -> List[Tuple[int, float]]:
    """De CandleStore.get_candles ({ts:[...], close:[...]}) a [(ts, close)]."""
    if not candles or not candles.get("ts"):
        return []
    return list(zip((int(t) for t in candles["ts"]), candles["close"]))


def _po_code(pair: str) -> str:
    return pair.replace("/", "").upper()


# --------------------------------------------------------------- captura en vivo
async def _bajar_historial_real(ssid: str, pair: str, espera: float
                                ) -> Dict[int, Dict[str, Any]]:
    """
    Conecta a PO, se suscribe al par en cada timeframe y captura el historial real
    (updateHistoryNewFast). Devuelve {period: parse_history(payload)}. Defensivo:
    si un periodo no responde, queda ausente y se reporta como "sin dato".
    """
    from bot.pocket_client import PocketOptionClient

    capturado: Dict[int, Dict[str, Any]] = {}

    def on_history(payload: Any) -> None:
        parsed = parse_history(payload)
        if parsed and parsed["velas"]:
            capturado[int(parsed["period"] or 0)] = parsed

    client = PocketOptionClient(ssid, on_history=on_history, demo=True,
                                logger=logging.getLogger("pocket_client"))
    code = _po_code(pair)
    tarea = asyncio.ensure_future(client.run(asset=code, period=60))
    try:
        if not await client.wait_connected(timeout=30):
            raise SystemExit("No se pudo conectar a Pocket Option (revisa SSID / "
                             "que el colector este APAGADO).")
        for period in TIMEFRAMES:
            await client.set_asset(code, period=period)
            await asyncio.sleep(espera)          # dar tiempo a que llegue el binario
    finally:
        client.stop()
        tarea.cancel()
    return capturado


def _leer_colector(db_path: str, pair: str, tf: int, count: int
                   ) -> List[Tuple[int, float]]:
    if not os.path.exists(db_path):
        return []
    from collector.candle_store import CandleStore
    store = CandleStore(db_path)
    try:
        return _col_close(store.get_candles(pair, tf, count))
    finally:
        store.close()


def _cargar_ssid() -> str:
    from bot.pocket_probe import _load_ssid
    ssid = _load_ssid("REAL")
    if not ssid:
        raise SystemExit("Falta el SSID de Pocket Option (POCKET_OPTION_SSID en "
                         ".env o ssid_real.txt).")
    return ssid


def main(argv: Optional[List[str]] = None) -> int:
    from core.config import ROOT

    ap = argparse.ArgumentParser(description="Compara historial real de PO vs "
                                             "po_candles.db (solo lectura).")
    ap.add_argument("pair", help="Par FX, ej: EUR/USD")
    ap.add_argument("--umbral", type=float, default=1.0,
                    help="Pips a partir de los cuales cuenta como gap (default 1.0)")
    ap.add_argument("--espera", type=float, default=6.0,
                    help="Segundos de espera por timeframe (default 6)")
    ap.add_argument("--count", type=int, default=500,
                    help="Velas del colector a leer por tf (default 500)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    pip = pip_size(args.pair)
    db_path = os.path.join(ROOT, "data", "db", "po_candles.db")

    real = asyncio.run(_bajar_historial_real(_cargar_ssid(), args.pair, args.espera))

    print(f"Comparacion historial REAL de PO vs colector · {args.pair} "
          f"(pip={pip}, umbral={args.umbral} pips)")
    print(f"{'tf':>5} {'velas_PO':>9} {'velas_col':>10} {'comunes':>8} "
          f"{'gap_med':>8} {'gap_max':>8} {'%>umbral':>9}")
    print("-" * 66)
    algun_gap = False
    for tf in TIMEFRAMES:
        parsed = real.get(tf)
        velas_po = _velas_close(parsed)
        velas_col = _leer_colector(db_path, args.pair, tf, args.count)
        rep = comparar_velas(velas_po, velas_col, pip, args.umbral)
        etiqueta = f"{tf}s"
        if not velas_po:
            print(f"{etiqueta:>5} {'sin dato':>9} {rep['n_col']:>10} "
                  f"{'-':>8} {'-':>8} {'-':>8} {'-':>9}")
            continue
        if rep["pct_con_gap"] > 0:
            algun_gap = True
        print(f"{etiqueta:>5} {rep['n_po']:>9} {rep['n_col']:>10} "
              f"{rep['n_comunes']:>8} {rep['gap_medio_pips']:>8} "
              f"{rep['gap_max_pips']:>8} {rep['pct_con_gap']:>8}%")
    print("-" * 66)
    if algun_gap:
        print("=> Hay divergencia entre el precio real de PO y el del colector. "
              "El win/loss calculado sobre el colector NO es confiable: hay que "
              "guardar el OHLC real (Paso 2) y resolver contra el (Paso 3).")
    else:
        print("=> Sin gaps sobre el umbral en los ts comunes. Revisa n_comunes: "
              "si es bajo, el colector cubre pocos de los timestamps reales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
