"""
scratchpad/reporte_otc.py — llena el REPORTE DE ANÁLISIS OTC con datos REALES de
los datasets (velas OHLC M1). Honesto: lo que los datos NO contienen (stream de
payout, bid/ask spread, latencia de ticks) se marca [SIN DATOS], no se inventa.

Medible desde velas OHLC:
  - Análisis 1: tabla payout→win-rate de equilibrio (matemática pura, universal).
  - Análisis 2 (proxy): rango (high-low), huecos de tiempo, velas anómalas (>3σ).
    NO es spread real; es lo que la vela permite. Se etiqueta como proxy.
  - Análisis 4: ventaja del broker (EV por operación) + predictibilidad direccional
    (momentum/reversión) medida sobre los datos → ¿hay borde explotable?
"""
import glob
import math
import os

import pandas as pd

PAYOUT_TRADER = 92.0


def wr_equilibrio(payout):
    """Win-rate de equilibrio: p*payout = (1-p)*100 → p = 100/(100+payout)."""
    return 100.0 / (100.0 + payout) * 100.0


def tabla_payout():
    filas = []
    for pa in [75, 80, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95]:
        we = wr_equilibrio(pa)
        filas.append((pa, we, we + 2.0))     # +2% de margen práctico
    return filas


def stats_activo(ruta):
    """Estadísticas reales de un activo desde sus velas M1."""
    a = os.path.basename(ruta).split("__")[0]
    df = pd.read_csv(ruta)
    if len(df) < 100:
        return None
    o = df["open"].to_numpy(); c = df["close"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    ts = df["timestamp"].to_numpy()

    # Retorno y rango por vela en puntos básicos (bps) — comparable entre activos.
    ret_bps = (c - o) / o * 10000.0
    rango_bps = (h - l) / o * 10000.0
    med_rango = float(pd.Series(rango_bps).median())
    std_rango = float(pd.Series(rango_bps).std())
    umbral = med_rango + 3 * std_rango
    anomalas = int((rango_bps > umbral).sum())

    # Huecos de tiempo: M1 = 60s. Contar saltos > 90s (falta ≥1 vela).
    dt = (ts[1:] - ts[:-1]) / 1000.0
    huecos = int((dt > 90).sum())
    gap_max = float(dt.max()) if len(dt) else 0.0
    dt_prom = float(dt.mean()) if len(dt) else 0.0

    # % velas alcistas, autocorrelación de retornos (memoria), predictibilidad.
    pct_up = float((c > o).mean() * 100)
    s = pd.Series(ret_bps)
    autocorr = float(s.autocorr(lag=1)) if len(s) > 2 else 0.0
    # Predictor direccional: momentum (repetir signo) y reversión (invertir).
    sig = (c > o)
    if len(sig) > 1:
        mom = float((sig[:-1] == sig[1:]).mean() * 100)     # sube→sube
        rev = 100.0 - mom
    else:
        mom = rev = 50.0
    mejor_pred = max(mom, rev)

    # Ventaja del broker (EV por operación) a win-rate 50% y payout 92%.
    ev50 = (0.50 * PAYOUT_TRADER / 100 - 0.50) * 100
    return {
        "activo": a, "velas": len(df),
        "med_rango": med_rango, "std_rango": std_rango,
        "min_rango": float(rango_bps.min()), "max_rango": float(rango_bps.max()),
        "anomalas": anomalas, "pct_anom": anomalas / len(df) * 100,
        "huecos": huecos, "gap_max": gap_max, "dt_prom": dt_prom,
        "pct_up": pct_up, "autocorr": autocorr,
        "mom": mom, "rev": rev, "mejor_pred": mejor_pred, "ev50": ev50,
    }


def ev_por_wr(wr, payout=PAYOUT_TRADER):
    """Esperanza por operación (%) a un win-rate dado."""
    p = wr / 100
    return (p * payout / 100 - (1 - p)) * 100


rutas = sorted(glob.glob("datasets/*__M1.csv.gz"))
todos = []
for r in rutas:
    try:
        s = stats_activo(r)
        if s:
            todos.append(s)
    except Exception as e:
        print(f"ERR {os.path.basename(r)}: {e}")

# Agregados globales.
n = len(todos)
med_pred = sum(x["mejor_pred"] for x in todos) / n
med_autoc = sum(x["autocorr"] for x in todos) / n
med_up = sum(x["pct_up"] for x in todos) / n
med_rango_g = sum(x["med_rango"] for x in todos) / n

print(f"ACTIVOS={n}")
print(f"WR_EQ_92={wr_equilibrio(92):.2f}")
print(f"MED_PRED={med_pred:.2f}  MED_AUTOCORR={med_autoc:.4f}  MED_UP={med_up:.2f}  MED_RANGO_bps={med_rango_g:.2f}")
print(f"EV50_92={(0.5*0.92-0.5)*100:.2f}")
print("EV_WR:", {w: round(ev_por_wr(w), 2) for w in (50, 52.08, 55, 60, 65)})
print("\nTABLA_PAYOUT:")
for pa, we, wm in tabla_payout():
    print(f"  {pa}\t{we:.2f}\t{wm:.2f}")

# Representativos por clase (si existen).
repr_ids = ["#AAPL_otc", "EURUSD_otc", "BTCUSD_otc", "AUS200_otc"]
print("\nREPRESENTATIVOS:")
for x in todos:
    if x["activo"] in repr_ids:
        print(f"  {x['activo']:12} velas={x['velas']} rango_med={x['med_rango']:.1f}bps "
              f"std={x['std_rango']:.1f} anom={x['anomalas']}({x['pct_anom']:.2f}%) "
              f"huecos={x['huecos']} gapmax={x['gap_max']:.0f}s up={x['pct_up']:.1f}% "
              f"autoc={x['autocorr']:.4f} mejor_pred={x['mejor_pred']:.1f}%")

# Ranking por menor predictibilidad-desviación (todos ~50 = azar). Mostrar extremos.
top = sorted(todos, key=lambda x: -x["mejor_pred"])[:5]
print("\nTOP5_MEJOR_PRED (más lejos de 50% = más 'predecible' en-muestra):")
for x in top:
    print(f"  {x['activo']:12} mejor_pred={x['mejor_pred']:.2f}%  (mom={x['mom']:.1f} rev={x['rev']:.1f})")
# Guardar CSV para la tabla comparativa completa.
pd.DataFrame(todos).to_csv("scratchpad/reporte_otc_datos.csv", index=False)
print("\nCSV -> scratchpad/reporte_otc_datos.csv")
