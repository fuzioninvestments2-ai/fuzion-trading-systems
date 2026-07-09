"""
bot/dukascopy_deep.py
=====================
Descarga MASIVA/PROFUNDA de FX real desde Dukascopy, con estado/resume y verificación.

Tiempos y su fuente honesta:
  - 1m,5m,10m,15m,30m,1h,4h  → Dukascopy DIRECTO, desde 2003 (o lo más antiguo). ✅
  - 2m,3m                     → DERIVADOS del 1m (mismo dato, se generan). ✅
  - 5s,10s,15s,30s            → Dukascopy, VENTANA RECIENTE (configurable). Los
    segundos desde 2003 son inviables (~miles de millones de velas / decenas de GB
    / ban). Se bajan los últimos `dias_segundos` días.

Descarga por CHUNKS (ventanas de tiempo), concatena, deduplica por timestamp y
guarda en `datasets/real/PAR__CLAVE.csv.gz` (lo que lee el análisis). Lleva estado
en `datasets/real/download_status.json`: al re-lanzar, SALTA lo ya descargado
(resume). Solo activos reales; corre en la PC (no en cloud).
"""
import datetime as dt
import gzip
import json
import os

# Intervalo Dukascopy → clave interna (tiempos que se bajan directo, profundos).
INTERVALOS = [
    ("INTERVAL_MIN_1", "M1"), ("INTERVAL_MIN_5", "tf300"),
    ("INTERVAL_MIN_10", "tf600"), ("INTERVAL_MIN_15", "tf900"),
    ("INTERVAL_MIN_30", "tf1800"), ("INTERVAL_HOUR_1", "tf3600"),
    ("INTERVAL_HOUR_4", "tf14400"),
]
COLS = ["timestamp", "open", "high", "low", "close", "volume"]
VENTANA_DIAS = 180                    # tamaño de cada chunk de descarga
DESDE_DEFECTO = "2003-01-01"
DIAS_SEGUNDOS = 30                    # ventana reciente para 5s-30s


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
    return {"completos": {}}          # {par: {clave: n_velas}}


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


def descargar_intervalo(par, interval_const, clave, desde, destino):
    """Descarga un intervalo por chunks de VENTANA_DIAS desde `desde`. Devuelve nº velas."""
    import dukascopy_python as duka
    from bot.dukascopy_loader import instrumento_de, _a_formato

    inst = instrumento_de(par)
    if inst is None:
        return 0
    interval = getattr(duka, interval_const)
    fin = dt.datetime.now(dt.timezone.utc)
    cursor = dt.datetime.fromisoformat(desde).replace(tzinfo=dt.timezone.utc)
    dfs = []
    while cursor < fin:
        ventana_fin = min(cursor + dt.timedelta(days=VENTANA_DIAS), fin)
        try:
            df = duka.fetch(inst, interval, duka.OFFER_SIDE_BID, cursor, ventana_fin)
            if df is not None and len(df):
                dfs.append(_a_formato(df))
        except Exception as e:
            print(f"    ({clave} {cursor.date()}→{ventana_fin.date()} error: {repr(e)[:50]})")
        cursor = ventana_fin
    return _fusionar_guardar(dfs, os.path.join(destino, f"{par}__{clave}.csv.gz"))


def descargar_par(par, desde=DESDE_DEFECTO, destino="datasets/real",
                  dias_segundos=DIAS_SEGUNDOS, status=None, rehacer=False):
    """Descarga 1m→4h profundo + 2m/3m derivados + segundos recientes de un par."""
    from bot.resamplear import derivar_par

    status = status if status is not None else _cargar_status(destino)
    hechos = status["completos"].setdefault(par, {})
    print(f"  {par}: 1m→4h desde {desde}")
    for interval_const, clave in INTERVALOS:
        salida = os.path.join(destino, f"{par}__{clave}.csv.gz")
        if not rehacer and clave in hechos and os.path.exists(salida):
            print(f"    {clave:8} ya descargado ({hechos[clave]} velas) — salto")
            continue
        n = descargar_intervalo(par, interval_const, clave, desde, destino)
        hechos[clave] = n
        _guardar_status(destino, status)          # guardar tras cada intervalo (resume)
        print(f"    {clave:8} {n:>9} velas")
    # Derivar 2m/3m del 1m.
    m1 = os.path.join(destino, f"{par}__M1.csv.gz")
    if os.path.exists(m1):
        d = derivar_par(m1, sobrescribir=True)
        print(f"    derivados: {', '.join(f'{c}({x})' for c, x in d) or 'nada'}")
    # Segundos recientes (ventana corta, no 2003).
    if dias_segundos > 0:
        try:
            from bot.dukascopy_loader import bajar_par
            bajar_par(par, dias=dias_segundos, destino=destino)
        except Exception as e:
            print(f"    segundos: error {repr(e)[:50]}")
    return status


def descargar_todos(pares=None, desde=DESDE_DEFECTO, destino="datasets/real",
                    dias_segundos=DIAS_SEGUNDOS, rehacer=False):
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    print(f"DESCARGA MASIVA · {len(pares)} pares · desde {desde} · 1m→4h + segundos({dias_segundos}d)")
    print("Resume activo: re-lanzar salta lo ya bajado. (Tarda horas; se puede cortar.)\n")
    status = _cargar_status(destino)
    for i, p in enumerate(pares, 1):
        print(f"[{i}/{len(pares)}] {p}")
        try:
            descargar_par(p, desde, destino, dias_segundos, status, rehacer)
        except Exception as e:
            print(f"  {p}: ERROR {repr(e)[:100]}")
    print("\nListo. Verifica con:  python -m bot.dukascopy_deep --verificar")


def verificar(destino="datasets/real"):
    """Reporta velas por par/timeframe y tamaño total de lo descargado."""
    import glob
    import pandas as pd
    claves = ["tf5", "tf10", "tf15", "tf30", "M1", "tf120", "tf180", "tf300",
              "tf600", "tf900", "tf1800", "tf3600", "tf14400"]
    print(f"VERIFICACIÓN de {destino}/\n")
    pares = sorted({os.path.basename(f).split("__")[0]
                    for f in glob.glob(f"{destino}/*__*.csv.gz")})
    total_bytes = tot_velas = 0
    for par in pares:
        presentes = []
        for cl in claves:
            f = os.path.join(destino, f"{par}__{cl}.csv.gz")
            if os.path.exists(f):
                n = sum(1 for _ in gzip.open(f, "rt")) - 1
                total_bytes += os.path.getsize(f); tot_velas += max(0, n)
                presentes.append(cl)
        print(f"  {par:8} {len(presentes):>2}/13 tiempos  ({', '.join(presentes)})")
    print(f"\nTotal: {len(pares)} pares · {tot_velas:,} velas · {total_bytes/1024**3:.2f} GB")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Descarga masiva Dukascopy 1m→4h + segundos.")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--desde", default=DESDE_DEFECTO, help="fecha inicio 1m→4h (YYYY-MM-DD)")
    ap.add_argument("--dias-segundos", type=int, default=DIAS_SEGUNDOS,
                    help="ventana reciente para 5s-30s (0 = no bajar segundos)")
    ap.add_argument("--rehacer", action="store_true", help="ignora el estado y re-descarga")
    ap.add_argument("--verificar", action="store_true", help="solo verificar lo descargado")
    a = ap.parse_args()
    if a.verificar:
        verificar()
    else:
        descargar_todos(a.pares or None, a.desde, dias_segundos=a.dias_segundos,
                        rehacer=a.rehacer)
