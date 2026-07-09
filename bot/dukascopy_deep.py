"""
bot/dukascopy_deep.py
=====================
Descarga MASIVA/PROFUNDA de FX real desde Dukascopy — LOS 13 TIEMPOS, 5+ años, con
estado/resume y verificación.

Tiempos y cómo se obtienen (todos desde `--desde`, por defecto 2003):
  - 1m,5m,10m,15m,30m,1h,4h → Dukascopy DIRECTO (velas ya agregadas).
  - 5s,10s,15s,30s          → se piden velas de 1 SEGUNDO por trozos y se RESAMPLEAN
    al vuelo a 5/10/15/30s; el 1s crudo se descarta (memoria acotada). El 5s final
    de 5 años pesa pocos GB — es viable; el costo es TIEMPO de descarga.
  - 2m,3m                   → derivados del 1m.

Descarga por CHUNKS (ventanas de tiempo), concatena, deduplica por timestamp y
guarda en `datasets/real/PAR__CLAVE.csv.gz`. Estado en `download_status.json`:
re-lanzar SALTA lo ya bajado (resume). Solo activos reales; corre en la PC.
"""
import datetime as dt
import gzip
import json
import os

# 1m→4h: Dukascopy directo.
INTERVALOS = [
    ("INTERVAL_MIN_1", "M1"), ("INTERVAL_MIN_5", "tf300"),
    ("INTERVAL_MIN_10", "tf600"), ("INTERVAL_MIN_15", "tf900"),
    ("INTERVAL_MIN_30", "tf1800"), ("INTERVAL_HOUR_1", "tf3600"),
    ("INTERVAL_HOUR_4", "tf14400"),
]
# Segundos: se arman desde velas de 1s resampleadas.
SEGUNDOS_OBJ = [(5, "tf5"), (10, "tf10"), (15, "tf15"), (30, "tf30")]
COLS = ["timestamp", "open", "high", "low", "close", "volume"]
VENTANA_DIAS = 180                # chunk para 1m→4h
VENTANA_SEG_DIAS = 20             # chunk para 1s (más chico: 1s es denso)
DESDE_DEFECTO = "2003-01-01"


def _status_path(destino):
    return os.path.join(destino, "download_status.json")


def _cargar_status(destino):
    p = _status_path(destino)
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"completos": {}}


def _guardar_status(destino, status):
    os.makedirs(destino, exist_ok=True)
    with open(_status_path(destino), "w") as f:
        json.dump(status, f, indent=2)


def _fusionar_guardar(dfs, salida):
    import pandas as pd
    if not dfs:
        return 0
    df = pd.concat(dfs, ignore_index=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp")[COLS]
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with gzip.open(salida, "wt", encoding="utf-8") as gz:
        df.to_csv(gz, index=False)
    return len(df)


def _rango(desde):
    fin = dt.datetime.now(dt.timezone.utc)
    ini = dt.datetime.fromisoformat(desde).replace(tzinfo=dt.timezone.utc)
    return ini, fin


def descargar_intervalo(par, interval_const, clave, desde, destino):
    """1m→4h: velas directas por chunks. Devuelve nº velas guardadas."""
    import dukascopy_python as duka
    from bot.dukascopy_loader import instrumento_de, _a_formato

    inst = instrumento_de(par)
    if inst is None:
        return 0
    interval = getattr(duka, interval_const)
    cursor, fin = _rango(desde)
    dfs = []
    while cursor < fin:
        vfin = min(cursor + dt.timedelta(days=VENTANA_DIAS), fin)
        try:
            df = duka.fetch(inst, interval, duka.OFFER_SIDE_BID, cursor, vfin)
            if df is not None and len(df):
                dfs.append(_a_formato(df))
        except Exception as e:
            print(f"    ({clave} {cursor.date()}→{vfin.date()} error: {repr(e)[:45]})")
        cursor = vfin
    return _fusionar_guardar(dfs, os.path.join(destino, f"{par}__{clave}.csv.gz"))


def descargar_segundos(par, desde, destino):
    """
    5s/10s/15s/30s: pide velas de 1s por trozos y las resamplea al vuelo (descarta el
    1s crudo → memoria acotada). Devuelve {clave: nº velas}.
    """
    import dukascopy_python as duka
    from bot.dukascopy_loader import instrumento_de, _a_formato
    from bot.resamplear import resamplear

    inst = instrumento_de(par)
    if inst is None:
        return {}
    cursor, fin = _rango(desde)
    acc = {clave: [] for _, clave in SEGUNDOS_OBJ}
    while cursor < fin:
        vfin = min(cursor + dt.timedelta(days=VENTANA_SEG_DIAS), fin)
        try:
            df = duka.fetch(inst, duka.INTERVAL_SEC_1, duka.OFFER_SIDE_BID, cursor, vfin)
            if df is not None and len(df):
                base = _a_formato(df)                      # 1s del trozo
                for seg, clave in SEGUNDOS_OBJ:
                    acc[clave].append(resamplear(base, seg))   # resamplea y guarda solo eso
        except Exception as e:
            print(f"    (segundos {cursor.date()}→{vfin.date()} error: {repr(e)[:40]})")
        cursor = vfin
    out = {}
    for _, clave in SEGUNDOS_OBJ:
        out[clave] = _fusionar_guardar(acc[clave],
                                       os.path.join(destino, f"{par}__{clave}.csv.gz"))
    return out


def descargar_par(par, desde=DESDE_DEFECTO, desde_segundos=None,
                  destino="datasets/real", status=None, rehacer=False):
    """Descarga los 13 tiempos de un par (1m→4h directo, segundos por resampleo, 2m/3m derivados)."""
    from bot.resamplear import derivar_par

    desde_segundos = desde_segundos or desde
    status = status if status is not None else _cargar_status(destino)
    hechos = status["completos"].setdefault(par, {})

    print(f"  {par}: 1m→4h desde {desde}")
    for interval_const, clave in INTERVALOS:
        salida = os.path.join(destino, f"{par}__{clave}.csv.gz")
        if not rehacer and clave in hechos and os.path.exists(salida):
            print(f"    {clave:8} ya ({hechos[clave]} velas) — salto")
            continue
        n = descargar_intervalo(par, interval_const, clave, desde, destino)
        hechos[clave] = n
        _guardar_status(destino, status)
        print(f"    {clave:8} {n:>9} velas")

    # 2m/3m derivados del 1m. OJO: solo 2m/3m — 10m y 4h vienen DIRECTOS (más
    # profundos que derivarlos del 1m), no se tocan.
    m1 = os.path.join(destino, f"{par}__M1.csv.gz")
    if os.path.exists(m1):
        d = derivar_par(m1, sobrescribir=True, claves=("tf120", "tf180"))
        print(f"    derivados: {', '.join(f'{c}({x})' for c, x in d) or 'nada'}")

    # Segundos (5s-30s) desde `desde_segundos` por resampleo de 1s.
    faltan_seg = rehacer or any(cl not in hechos for _, cl in SEGUNDOS_OBJ)
    if faltan_seg:
        print(f"    segundos (5s-30s) desde {desde_segundos} — resampleo de 1s (lento)")
        seg = descargar_segundos(par, desde_segundos, destino)
        for cl, n in seg.items():
            hechos[cl] = n
            print(f"    {cl:8} {n:>9} velas")
        _guardar_status(destino, status)
    return status


def descargar_todos(pares=None, desde=DESDE_DEFECTO, desde_segundos=None,
                    destino="datasets/real", rehacer=False):
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    print(f"DESCARGA MASIVA · {len(pares)} pares · 13 tiempos · desde {desde}")
    print("Resume activo (salta lo ya bajado). Los segundos por resampleo de 1s son")
    print("lo más lento; puedes cortar y retomar cuando quieras.\n")
    status = _cargar_status(destino)
    for i, p in enumerate(pares, 1):
        print(f"[{i}/{len(pares)}] {p}")
        try:
            descargar_par(p, desde, desde_segundos, destino, status, rehacer)
        except Exception as e:
            print(f"  {p}: ERROR {repr(e)[:100]}")
    print("\nListo. Verifica con:  python -m bot.dukascopy_deep --verificar")


def verificar(destino="datasets/real"):
    """Reporta velas por par/timeframe y tamaño total."""
    import glob
    claves = ["tf5", "tf10", "tf15", "tf30", "M1", "tf120", "tf180", "tf300",
              "tf600", "tf900", "tf1800", "tf3600", "tf14400"]
    print(f"VERIFICACIÓN de {destino}/\n")
    pares = sorted({os.path.basename(f).split("__")[0]
                    for f in glob.glob(f"{destino}/*__*.csv.gz")})
    total_bytes = tot = 0
    for par in pares:
        pres = []
        for cl in claves:
            f = os.path.join(destino, f"{par}__{cl}.csv.gz")
            if os.path.exists(f):
                n = sum(1 for _ in gzip.open(f, "rt")) - 1
                total_bytes += os.path.getsize(f); tot += max(0, n)
                pres.append(cl)
        print(f"  {par:8} {len(pres):>2}/13  ({', '.join(pres)})")
    print(f"\nTotal: {len(pares)} pares · {tot:,} velas · {total_bytes/1024**3:.2f} GB")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Descarga masiva Dukascopy · 13 tiempos.")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--desde", default=DESDE_DEFECTO, help="inicio (YYYY-MM-DD)")
    ap.add_argument("--desde-segundos", default=None,
                    help="inicio para 5s-30s (def = --desde). Acórtalo si quieres menos.")
    ap.add_argument("--rehacer", action="store_true", help="ignora estado y re-descarga")
    ap.add_argument("--verificar", action="store_true", help="solo verificar")
    a = ap.parse_args()
    if a.verificar:
        verificar()
    else:
        descargar_todos(a.pares or None, a.desde, a.desde_segundos, rehacer=a.rehacer)
