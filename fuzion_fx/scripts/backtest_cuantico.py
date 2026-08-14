"""
scripts/backtest_cuantico.py (fuzion_fx)
========================================
Backtest WALK-FORWARD del motor cuantico sobre historial REAL de FX, SIN mirar el
futuro: en cada barra la decision usa solo velas ya cerradas (timestamp <= t); el
resultado se mide contra la vela SIGUIENTE (que la decision no vio). Mide el
win-rate real y lo compara con el break-even del pago.

HONESTIDAD (regla del proyecto):
 - OTC es precio SINTETICO de PO: NO representa el mercado real. Este backtest es
   para FX REAL. No se usan datos OTC como proxy del real (dan ~0 de memoria; el
   FX real tiene -0.05/-0.11). Correr sobre OTC solo probaria la MECANICA, no el
   acierto real -> por eso el default es real y OTC exige --permitir-otc explicito.
 - Sin fuente de datos real, un timeframe se marca "sin datos" (no se inventan).

Formato de entrada (interno, el mismo que produce bot.ingest_tradingview):
    CSV/CSV.GZ con cabecera:  timestamp,open,high,low,close,volume
    timestamp en MILISEGUNDOS. Un archivo por (par, timeframe).

Rutas que busca por (par, tf), en orden:
    datasets/real/{PAR}__tf{TF}.csv.gz     (o __M1 para 60s)
    datos/raw/{PAR}_{LABEL}.csv            (ej. EURUSD_1m.csv, EURUSD_30m.csv)

Uso:
    python -m fuzion_fx.scripts.backtest_cuantico EURUSD --pago 85
    python fuzion_fx/scripts/backtest_cuantico.py EURUSD --tfs 60,120,180,300 --max 5000
"""

from __future__ import annotations

import argparse
import gzip
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import quantum_engine, indicator_set                 # noqa: E402

# Raiz del repo (un nivel arriba de fuzion_fx/) para alcanzar datasets/ y datos/.
_REPO = os.path.dirname(_RAIZ)

# tf en segundos -> etiqueta humana (para los CSV de TradingView).
_LABEL = {60: "1m", 120: "2m", 180: "3m", 300: "5m", 600: "10m",
          900: "15m", 1800: "30m", 3600: "1h"}

TFS_CUANTICO = [60, 120, 180, 300, 600, 900, 1800]


def _leer_csv(path: str) -> Optional[Dict[str, np.ndarray]]:
    """Lee un CSV/gz interno (timestamp ms, ohlcv) a arrays numpy. None si no existe
    o esta vacio."""
    if not os.path.exists(path):
        return None
    abrir = gzip.open if path.endswith(".gz") else open
    ts: List[int] = []
    o: List[float] = []
    h: List[float] = []
    lo: List[float] = []
    c: List[float] = []
    try:
        with abrir(path, "rt") as f:
            cab = f.readline()                        # descarta cabecera
            if not cab:
                return None
            for linea in f:
                p = linea.strip().split(",")
                if len(p) < 5:
                    continue
                # timestamp en ms -> segundos (grilla comun con el resto del bot).
                ts.append(int(float(p[0])) // 1000)
                o.append(float(p[1])); h.append(float(p[2]))
                lo.append(float(p[3])); c.append(float(p[4]))
    except (OSError, ValueError):
        return None
    if len(c) < 2:
        return None
    return {"ts": np.asarray(ts, dtype=np.int64),
            "open": np.asarray(o, float), "high": np.asarray(h, float),
            "low": np.asarray(lo, float), "close": np.asarray(c, float)}


def _ruta_tf(par: str, tf: int, permitir_otc: bool) -> List[str]:
    """Rutas candidatas para (par, tf), reales primero. Si permitir_otc, agrega el
    dataset OTC AL FINAL (solo para probar mecanica; nunca como medida real)."""
    par_u = par.upper().replace("/", "")
    tf_lbl = "M1" if tf == 60 else f"tf{tf}"
    cands = [
        os.path.join(_REPO, "datasets", "real", f"{par_u}__{tf_lbl}.csv.gz"),
        os.path.join(_REPO, "datasets", "real", f"{par_u}__{tf_lbl}.csv"),
        os.path.join(_REPO, "datos", "raw", f"{par_u}_{_LABEL.get(tf, tf)}.csv"),
    ]
    if permitir_otc:
        cands.append(os.path.join(_REPO, "datasets", f"{par_u}_otc__{tf_lbl}.csv.gz"))
    return cands


def pares_reales_disponibles() -> List[str]:
    """Lista los pares con base 1m real (datasets/real/*__M1.csv.gz o
    datos/raw/*_1m.csv), para orientar cuando el par pedido no esta."""
    import glob
    pares = set()
    for ruta in glob.glob(os.path.join(_REPO, "datasets", "real", "*__M1.csv.gz")):
        pares.add(os.path.basename(ruta).split("__", 1)[0])
    for ruta in glob.glob(os.path.join(_REPO, "datos", "raw", "*_1m.csv")):
        pares.add(os.path.basename(ruta).rsplit("_1m.csv", 1)[0])
    return sorted(pares)


def cargar(par: str, tfs: Sequence[int], permitir_otc: bool
           ) -> Dict[int, Dict[str, np.ndarray]]:
    """Carga los timeframes disponibles del par. Los que no tengan fuente real se
    OMITEN (no se inventan)."""
    datos: Dict[int, Dict[str, np.ndarray]] = {}
    for tf in tfs:
        serie = None
        for ruta in _ruta_tf(par, tf, permitir_otc):
            serie = _leer_csv(ruta)
            if serie is not None:
                break
        if serie is not None:
            datos[tf] = serie
    return datos


def _ventana(serie: Dict[str, np.ndarray], t: int, n: int
             ) -> Optional[Dict[str, list]]:
    """Devuelve las ultimas n velas de la serie con timestamp <= t (SIN futuro).
    None si no llega a MIN_VELAS."""
    # searchsorted 'right': primer indice con ts > t -> corte exclusivo del futuro.
    corte = int(np.searchsorted(serie["ts"], t, side="right"))
    if corte < indicator_set.MIN_VELAS:
        return None
    ini = max(0, corte - n)
    return {"open": list(serie["open"][ini:corte]),
            "high": list(serie["high"][ini:corte]),
            "low": list(serie["low"][ini:corte]),
            "close": list(serie["close"][ini:corte])}


def backtest(par: str, tfs: Sequence[int], pago: float = 85.0,
             permitir_otc: bool = False, max_barras: int = 4000,
             paso: int = 1, ventana: int = 150) -> Dict[str, Any]:
    """Corre el walk-forward. Devuelve el reporte (operaciones, win-rate, etc.)."""
    datos = cargar(par, tfs, permitir_otc)
    if 60 not in datos:
        pista = "" if permitir_otc else " (--permitir-otc prueba mecanica con OTC)."
        return {"error": f"sin base 1m real para {par} en datasets/real ni datos/raw.{pista}",
                "tfs_cargados": sorted(datos),
                "pares_disponibles": pares_reales_disponibles()}

    base = datos[60]
    n_base = len(base["close"])
    # Arranca cuando ya hay historia suficiente; recorre las ultimas max_barras.
    ini = max(indicator_set.MIN_VELAS, n_base - max_barras)
    ops = 0
    wins = 0
    ties = 0
    probas: List[float] = []
    por_veredicto: Dict[str, int] = {}
    # DIAGNOSTICO: para saber POR QUE hay pocas/ninguna operacion se tallan TODOS
    # los veredictos (no solo los operables) y la probabilidad de TODAS las barras.
    hist_veredicto: Dict[str, int] = {}
    prob_todas: List[float] = []
    tfs_por_barra: List[int] = []

    for i in range(ini, n_base - 1, max(1, paso)):
        t = int(base["ts"][i])
        velas: Dict[int, Dict[str, list]] = {}
        for tf, serie in datos.items():
            v = _ventana(serie, t, ventana)
            if v is not None:
                velas[tf] = v
        if not velas:
            continue
        qr = quantum_engine.analizar(velas)
        ver = qr["veredicto"]
        hist_veredicto[ver] = hist_veredicto.get(ver, 0) + 1
        prob_todas.append(qr["probabilidad"])
        tfs_por_barra.append(len(velas))
        # Umbral: OPERAR siempre; OPCIONAL cuenta como operacion (modo rapido).
        if ver not in ("OPERAR", "OPCIONAL"):
            continue
        d = qr["direccion"]
        entrada = float(base["close"][i])
        cierre = float(base["close"][i + 1])          # vela SIGUIENTE (no vista)
        por_veredicto[ver] = por_veredicto.get(ver, 0) + 1
        probas.append(qr["probabilidad"])
        if cierre == entrada:
            ties += 1
            continue
        subio = cierre > entrada
        gano = (d == indicator_set.CALL and subio) or (d == indicator_set.PUT and not subio)
        ops += 1
        if gano:
            wins += 1

    decididas = ops                                    # sin contar ties
    win_rate = (wins / decididas * 100.0) if decididas else 0.0
    # Break-even de binarias con pago p%: p_be = 1/(1+p/100).
    break_even = 100.0 / (1.0 + pago / 100.0)
    return {
        "par": par, "tfs_cargados": sorted(datos), "fuente_otc": permitir_otc,
        "operaciones": decididas, "ties": ties, "wins": wins,
        "win_rate": win_rate, "break_even": break_even,
        "borde": win_rate - break_even,                # >0 = borde sobre break-even
        "prob_media": float(np.mean(probas)) if probas else 0.0,
        "por_veredicto": por_veredicto,
        # diagnostico
        "barras_analizadas": len(prob_todas),
        "hist_veredicto": hist_veredicto,
        "prob_media_global": float(np.mean(prob_todas)) if prob_todas else 0.0,
        "prob_max_global": float(np.max(prob_todas)) if prob_todas else 0.0,
        "tfs_medios_por_barra": float(np.mean(tfs_por_barra)) if tfs_por_barra else 0.0,
    }


def _imprimir(rep: Dict[str, Any]) -> None:
    if "error" in rep:
        print(f"ERROR: {rep['error']}")
        print(f"       tfs cargados: {rep.get('tfs_cargados')}")
        disp = rep.get("pares_disponibles")
        if disp:
            print(f"       pares reales disponibles: {', '.join(disp)}")
        elif disp is not None:
            print("       no hay pares reales en datasets/real ni datos/raw "
                  "(baja historial con Dukascopy en tu PC).")
        return
    print("=" * 60)
    print(f"Backtest cuantico · {rep['par']}"
          + ("  [OTC - SOLO MECANICA, no vale como acierto real]"
             if rep["fuente_otc"] else "  [FX REAL]"))
    print("=" * 60)
    print(f"  Timeframes usados : {rep['tfs_cargados']}")
    print(f"  Operaciones       : {rep['operaciones']}  (ties: {rep['ties']})")
    print(f"  Aciertos          : {rep['wins']}")
    print(f"  WIN-RATE          : {rep['win_rate']:.2f}%")
    print(f"  Break-even (pago) : {rep['break_even']:.2f}%")
    borde = rep["borde"]
    signo = "BORDE +" if borde > 0 else "SIN BORDE "
    print(f"  {signo}{borde:+.2f} pts sobre break-even")
    print(f"  Probabilidad media: {rep['prob_media']:.0%}  (solo operaciones)")
    print(f"  Por veredicto     : {rep['por_veredicto']}")
    print("  --- diagnostico (por que dispara poco/nada) ---")
    print(f"  Barras analizadas : {rep.get('barras_analizadas', 0)}")
    print(f"  tf medios/barra   : {rep.get('tfs_medios_por_barra', 0):.1f} de 7")
    print(f"  Prob media GLOBAL : {rep.get('prob_media_global', 0):.1%}"
          f"   (max {rep.get('prob_max_global', 0):.1%})")
    print(f"  Veredictos (todos): {rep.get('hist_veredicto', {})}")
    if rep["fuente_otc"]:
        print("  NOTA: datos OTC sinteticos; este numero NO mide el mercado real.")
    print("=" * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest walk-forward del motor cuantico.")
    ap.add_argument("par", help="Par, ej. EURUSD")
    ap.add_argument("--tfs", default="",
                    help="tf en segundos separados por coma (default: los 7 cuanticos)")
    ap.add_argument("--pago", type=float, default=85.0, help="pago %% del activo")
    ap.add_argument("--max", type=int, default=4000, help="ultimas N barras 1m")
    ap.add_argument("--paso", type=int, default=1, help="submuestreo de barras")
    ap.add_argument("--permitir-otc", action="store_true",
                    help="usa datasets OTC (SOLO para probar mecanica, no medida real)")
    args = ap.parse_args()
    tfs = ([int(x) for x in args.tfs.split(",") if x.strip()]
           if args.tfs else TFS_CUANTICO)
    rep = backtest(args.par, tfs, pago=args.pago, permitir_otc=args.permitir_otc,
                   max_barras=args.max, paso=args.paso)
    _imprimir(rep)


if __name__ == "__main__":
    main()
