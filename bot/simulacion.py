"""
bot/simulacion.py
=================
FORWARD-TEST INTERNO: corre el pipeline EN VIVO (la misma decisión que el robot) sobre el
historial y mide el acierto REAL de la señal —no del backtest de la tabla— contando la
operación que de verdad se hace: entra en el borde m+2 (una vela después del pico, con la
vela de margen) y vence una vela más allá, igual que la tarjeta.

Aplica TODOS los filtros del robot: adyacencia temporal (no picos por hueco), pico en
[piso, techo] con la tabla, EV con el pago, tendencia y zona de golpes. Resamplea por
TIEMPO REAL (agrupando por marca de tiempo), no por índice, así los huecos no fabrican
picos falsos.

Honesto: mide sobre datos que el borde NO vio (split train/test), así el número es el que
esperarías en vivo, no uno inflado por mirar los mismos datos.

Sin red. Test: bot/test_simulacion.py.
"""
import numpy as np

from bot.senal_reversion import senal, PISO_PIPS, _pip
from bot.tendencia import permite_reversion
from bot.evaluacion_riesgo import en_golpes


def _ev(borde, pago):
    p = borde / 100.0
    return p * (pago / 100.0) - (1.0 - p)


def resamplear(ts_ms, closes, tf_min):
    """Resamplea M1 a velas de `tf_min` por TIEMPO REAL: agrupa por bloque de tiempo y
    toma el último cierre de cada bloque. Devuelve (inicios_ms, cierres) en orden.
    Vectorizado (numpy): asume `ts_ms` ordenado ascendente (así viene del historial)."""
    ts = np.asarray(ts_ms, dtype=np.int64)
    cl = np.asarray(closes, dtype=float)
    if ts.size == 0:
        return [], []
    seg_ms = tf_min * 60_000
    buckets = (ts // seg_ms) * seg_ms
    cambio = np.empty(buckets.size, dtype=bool)        # último tick de cada bloque
    cambio[:-1] = buckets[1:] != buckets[:-1]
    cambio[-1] = True
    idx = np.where(cambio)[0]
    return buckets[idx].tolist(), cl[idx].tolist()


def _piso(tabla, par, exp):
    t = tabla.get(par) if tabla else None
    b = t.get(str(exp)) if isinstance(t, dict) else (t if isinstance(t, list) else None)
    if b:
        try:
            return min(u for u, _ in b)
        except (TypeError, ValueError):
            pass
    return PISO_PIPS


def simular_ops(ts_ms, closes, par, exp, tabla, payout=85.0, margen_ev=0.03,
                tend_n=20, tend_umbral=0.35, riesgo_n=15, max_golpes=4,
                con_tendencia=True, con_riesgo=True):
    """Corre el pipeline en vivo y devuelve la LISTA de operaciones reales, cada una con su
    metadata para poder cortar por condición (sesión horaria, tamaño de pico) después:
    [{hora, pico, direccion, gana}, ...]. `hora` es la hora UTC de ENTRADA (vela i+1)."""
    seg_ms = exp * 60_000
    bts, bc = resamplear(ts_ms, closes, exp)
    n = len(bc)
    piso = _piso(tabla, par, exp)
    warm = max(tend_n, riesgo_n) + 2
    ops = []
    # RÁPIDO: los picos son raros; se detectan de golpe con numpy y solo en esos se corre
    # el análisis (evita llamar a `senal` en millones de velas planas). El pico de la vela
    # i es |bc[i]-bc[i-1]|; candidato si >= piso.
    arr = np.asarray(bc, dtype=float)
    pip = _pip(par)
    mov = np.abs(np.diff(arr)) / pip
    cand = np.where(mov >= piso)[0] + 1                # i = índice de la vela-pico
    cand = cand[(cand >= warm) & (cand <= n - 3)]
    for i in cand:
        i = int(i)
        # ADYACENCIA: el pico (i vs i-1) y la operación (i+1, i+2) deben ser consecutivos.
        if bts[i] - bts[i - 1] != seg_ms:
            continue
        if bts[i + 1] - bts[i] != seg_ms or bts[i + 2] - bts[i + 1] != seg_ms:
            continue
        win = bc[i - 40 if i >= 40 else 0:i + 1]       # solo la cola necesaria (rápido)
        s = senal(win, par, exp, tabla)
        if not s.get("operar"):
            continue
        if _ev(s["probabilidad"], payout) < margen_ev:
            continue
        if con_tendencia and not permite_reversion(win, s["direccion"], tend_n, tend_umbral):
            continue
        if con_riesgo and en_golpes(win, par, piso, riesgo_n, max_golpes):
            continue
        # OPERACIÓN REAL: entra en el borde m+2 (cierre de la vela i+1), vence en i+2.
        entrada, salida = bc[i + 1], bc[i + 2]
        if salida == entrada:
            continue
        gana = (salida < entrada) if s["direccion"] == "PUT" else (salida > entrada)
        # hora UTC de la ENTRADA (bts está en ms) para poder cortar por sesión de mercado.
        hora = int((bts[i + 1] // 3_600_000) % 24)
        ops.append({"hora": hora, "pico": abs(mov[i - 1]), "direccion": s["direccion"],
                    "gana": bool(gana)})
    return ops


def _resumen(ops, payout):
    """Agrega una lista de ops en {señales, wins, losses, win_rate, pnl_por_op, equilibrio}."""
    wins = sum(1 for o in ops if o["gana"])
    losses = len(ops) - wins
    dec = wins + losses
    pnl = wins * (payout / 100.0) - losses
    return {"señales": len(ops), "wins": wins, "losses": losses,
            "win_rate": (round(wins / dec * 100, 1) if dec else None),
            "pnl_por_op": (round(pnl / dec * 100, 2) if dec else None),
            "equilibrio": round(100.0 / (1.0 + payout / 100.0), 1)}


def simular(ts_ms, closes, par, exp, tabla, payout=85.0, margen_ev=0.03,
            tend_n=20, tend_umbral=0.35, riesgo_n=15, max_golpes=4,
            con_tendencia=True, con_riesgo=True):
    """Corre el pipeline en vivo sobre la serie M1 (ts_ms, closes) para un tiempo `exp` y
    devuelve {señales, wins, losses, win_rate, pnl_por_op, equilibrio}."""
    ops = simular_ops(ts_ms, closes, par, exp, tabla, payout, margen_ev, tend_n,
                      tend_umbral, riesgo_n, max_golpes, con_tendencia, con_riesgo)
    return _resumen(ops, payout)


def correr_par(df, par, tabla_train, tiempos=(1, 2, 3, 5), payout=85.0, frac_test=0.4):
    """Simula un par sobre el tramo FINAL (test, `frac_test`) de su M1, con la tabla ya
    construida SOLO con el tramo de entrenamiento. Devuelve {exp: stats}."""
    df = df.sort_values("timestamp")
    ts = df["timestamp"].astype("int64").tolist()
    cl = df["close"].astype(float).tolist()
    corte = int(len(cl) * (1 - frac_test))
    ts_test, cl_test = ts[corte:], cl[corte:]
    return {e: simular(ts_test, cl_test, par, e, tabla_train, payout=payout)
            for e in tiempos}


if __name__ == "__main__":
    import argparse
    import glob
    import os
    import pandas as pd
    from bot.tabla_reversion import tabla_par

    ap = argparse.ArgumentParser(description="Forward-test interno del pipeline en vivo.")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = todos los reales)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--pago", type=float, default=85.0)
    a = ap.parse_args()

    rutas = [r for r in sorted(glob.glob(f"{a.destino}/*__M1.csv.gz"))
             if "_otc" not in os.path.basename(r).lower()]
    if a.pares:
        rutas = [r for r in rutas if os.path.basename(r).split("__")[0] in a.pares]
    TIEMPOS = (1, 2, 3, 5)
    equi = 100.0 / (1.0 + a.pago / 100.0)
    print(f"FORWARD-TEST INTERNO sobre {a.destino}/  ·  pago {a.pago:.0f}%  ·  "
          f"equilibrio {equi:.1f}%  ·  OOS (tabla=train 60% / prueba=test 40%)")
    print("El acierto es el REAL de la señal: entra en el borde (una vela tras el pico) "
          "y vence una vela después, con TODOS los filtros. (n) = nº de señales.")
    print("=" * 76)
    gw = gl = gs = 0
    for r in rutas:
        par = os.path.basename(r).split("__")[0]
        try:
            df = pd.read_csv(r).sort_values("timestamp")
        except Exception as e:
            print(f"  {par:8} ERROR {e}")
            continue
        cl = df["close"].astype(float).to_numpy()
        train = cl[:int(len(cl) * 0.6)]
        tabla = {par: {}}
        for e in TIEMPOS:
            tr = tabla_par(train, par, e)
            if tr:
                tabla[par][str(e)] = [[u, wr] for u, wr, _ in tr]
        res = correr_par(df, par, tabla, TIEMPOS, a.pago)
        linea = []
        for e in TIEMPOS:
            x = res[e]
            wr = f"{x['win_rate']:.0f}%" if x["win_rate"] is not None else "-"
            linea.append(f"{e}m:{wr}({x['señales']})")
            if x["win_rate"] is not None:
                gw += x["wins"]; gl += x["losses"]; gs += x["señales"]
        print(f"  {par:8} " + "  ".join(f"{c:>12}" for c in linea), flush=True)
    print("=" * 76)
    dec = gw + gl
    if dec:
        pnl = (gw * a.pago / 100.0 - gl) / dec * 100
        print(f"TOTAL: {gs} señales · acierto REAL {gw / dec * 100:.1f}% ({gw}W/{gl}L) · "
              f"P&L por operación {pnl:+.1f}%  (equilibrio {equi:.1f}%)")
        print("GANA si el acierto supera el equilibrio y el P&L/op es positivo.")
    else:
        print("Sin señales decididas: o la muestra es chica, o los filtros lo dejan todo "
              "fuera. Baja --pago o revisa el borde.")
