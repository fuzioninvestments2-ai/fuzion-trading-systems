"""
bot/estudio_fx.py
=================
ESTUDIO HONESTO del Mercado Real (FX) timeframe por timeframe, con el mismo rigor
que se aplicó al OTC. La diferencia clave que buscamos: el FX real NO es sintético
—tiene oferta/demanda de bancos— así que PODRÍA tener memoria (autocorrelación ≠ 0)
y un predictor que supere el 50%. Si la tiene, aquí aparece; si no, también.

Para cada timeframe de un activo mide:
  - Autocorrelación de retornos (lag 1): 0 = azar; ≠0 = memoria explotable.
  - % de velas alcistas (sesgo direccional).
  - Mejor predictor direccional simple (momentum vs reversión), en-muestra.
  - Señal del motor (`calculate_timeframe_signal`): cuántas veces acierta la
    dirección de la vela siguiente (win-rate direccional del indicador combinado).
  - Validación OUT-OF-SAMPLE TEMPORAL: mide en la 1ª mitad del tiempo (IS) y
    verifica en la 2ª (OOS). Un borde real persiste en ambas.

Break-even opciones binarias payout 92% = 52.08%. En FX "spot" el break-even es el
spread, mucho menor; aquí reportamos win-rate direccional puro para comparar peras
con peras contra el OTC (~50%). Sin red. Reproducible.
"""
import glob
import os

import pandas as pd

from bot.cuantico import calculate_timeframe_signal

# Mapa clave-archivo → segundos del timeframe (para etiquetar).
TF_SEG = {"M1": 60, "tf5": 5, "tf10": 10, "tf15": 15, "tf30": 30, "tf120": 120,
          "tf180": 180, "tf300": 300, "tf600": 600, "tf900": 900, "tf1800": 1800,
          "tf3600": 3600, "tf14400": 14400, "tf86400": 86400}


def _etq(seg):
    if seg < 60:
        return f"{seg}s"
    if seg < 3600:
        return f"{seg // 60}m"
    return f"{seg // 3600}h"


def estudiar_frame(df, expiry=1):
    """
    Estadística de un timeframe. `expiry`: cuántas velas adelante se mide el
    resultado (1 = la vela siguiente). Devuelve dict con las métricas.
    """
    if len(df) < 100:
        return None
    o = df["open"].to_numpy(); c = df["close"].to_numpy()
    ret = pd.Series((c - o) / o)
    autocorr = float(ret.autocorr(lag=1)) if len(ret) > 2 else 0.0
    pct_up = float((c > o).mean() * 100)

    # Predictor direccional simple: ¿la vela t predice la t+expiry?
    sube = (c > o)
    n = len(df) - expiry
    if n <= 10:
        return None
    fut_sube = c[expiry:] > c[:-expiry]                      # precio subió tras expiry
    mom = float((sube[:n] == fut_sube[:n]).mean() * 100)     # momentum: seguir la vela
    rev = 100.0 - mom                                         # reversión: contra la vela
    mejor = max(mom, rev)

    # Motor combinado: en cada punto (con ≥20 velas) predice y se compara con el futuro.
    aciertos = tot = 0
    for i in range(20, n):
        d, _f, _p = calculate_timeframe_signal(df.iloc[:i + 1])
        if d == 0:
            continue
        gano = (d > 0) == bool(fut_sube[i])
        aciertos += int(gano); tot += 1
    wr_motor = (aciertos / tot * 100) if tot else None
    return {"autocorr": autocorr, "pct_up": pct_up, "mom": mom, "rev": rev,
            "mejor_pred": mejor, "wr_motor": wr_motor, "n_motor": tot, "velas": len(df)}


def estudiar_oos(df, expiry=1):
    """Divide el historial en dos mitades temporales y estudia cada una."""
    mitad = len(df) // 2
    is_ = estudiar_frame(df.iloc[:mitad].reset_index(drop=True), expiry)
    oos = estudiar_frame(df.iloc[mitad:].reset_index(drop=True), expiry)
    return is_, oos


# Etiqueta de tiempo (1m,5m,...) → segundos, para el filtro --timeframes de la CLI.
LABEL_SEG = {"5s": 5, "10s": 10, "15s": 15, "30s": 30, "1m": 60, "2m": 120,
             "3m": 180, "5m": 300, "10m": 600, "15m": 900, "30m": 1800,
             "1h": 3600, "4h": 14400}


def _segundos_de_labels(labels):
    """Convierte 'all' o '1m,5m,15m' en un set de segundos (None = todos)."""
    if not labels or labels.strip().lower() == "all":
        return None
    segs = set()
    for l in labels.split(","):
        s = LABEL_SEG.get(l.strip().lower())
        if s:
            segs.add(s)
    return segs or None


def estudiar_activo(activo, patron="datasets", solo_seg=None):
    """Estudia los timeframes de un activo real (no OTC). `solo_seg`: filtro opcional."""
    rutas = sorted(glob.glob(f"{patron}/{activo}__*.csv.gz"))
    print(f"\n{'='*72}\nACTIVO REAL: {activo}   ({len(rutas)} timeframes con datos)\n{'='*72}")
    print(f"{'TF':>5} | {'velas':>6} | {'autocorr':>9} | {'%up':>5} | "
          f"{'mejorPred':>9} | {'motorWR':>8} | OOS(IS→OOS motorWR)")
    for r in rutas:
        clave = os.path.basename(r).split("__")[1].replace(".csv.gz", "")
        seg = TF_SEG.get(clave)
        if seg is None:
            continue
        if solo_seg is not None and seg not in solo_seg:
            continue
        df = pd.read_csv(r).sort_values("timestamp").reset_index(drop=True)
        full = estudiar_frame(df)
        if not full:
            print(f"{_etq(seg):>5} | (datos insuficientes)")
            continue
        is_, oos = estudiar_oos(df)
        oos_txt = "—"
        if is_ and oos and is_["wr_motor"] is not None and oos["wr_motor"] is not None:
            oos_txt = f"{is_['wr_motor']:.1f}%→{oos['wr_motor']:.1f}%"
        wm = f"{full['wr_motor']:.1f}%" if full["wr_motor"] is not None else "s/señal"
        print(f"{_etq(seg):>5} | {full['velas']:>6} | {full['autocorr']:>9.4f} | "
              f"{full['pct_up']:>4.1f}% | {full['mejor_pred']:>8.1f}% | {wm:>8} | {oos_txt}")


def activos_reales(patron="datasets"):
    """Lista de activos NO-OTC con datos."""
    ac = set()
    for f in glob.glob(f"{patron}/*.csv.gz"):
        b = os.path.basename(f)
        if "_otc" in b:
            continue
        ac.add(b.split("__")[0])
    return sorted(ac)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Estudio FX por timeframe (autocorr, OOS).")
    p.add_argument("--pairs", default="all", help="'all' o lista: EURUSD,GBPUSD")
    p.add_argument("--timeframes", default="all", help="'all' o lista: 1m,5m,15m,30m,1h")
    a = p.parse_args()
    print("ESTUDIO FX (Mercado Real) — comparación honesta contra el azar OTC (~50%).")
    print("Referencia: autocorrelación 0 y predictor 50% = azar (como el OTC sintético).")
    solo_seg = _segundos_de_labels(a.timeframes)
    quiere = None if a.pairs.strip().lower() == "all" else \
        {x.strip().upper() for x in a.pairs.split(",")}
    disponibles = activos_reales()
    elegidos = [x for x in disponibles if quiere is None or x.upper() in quiere]
    if not elegidos:
        print(f"Sin datos para {a.pairs}. Disponibles: {', '.join(disponibles) or '(ninguno)'}")
    for ac in elegidos:
        estudiar_activo(ac, solo_seg=solo_seg)
