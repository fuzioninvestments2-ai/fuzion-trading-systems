"""
bot/dukascopy_deep.py
=====================
Descarga PROFUNDA (años) de FX real desde Dukascopy para los tiempos 1m→4h. Es la
base histórica del análisis: con 5+ años, el estudio y el bot tienen datos de sobra
en todos los tiempos operables y de contexto.

Tiempos que baja DIRECTO de Dukascopy: 1m, 5m, 10m, 15m, 30m, 1h, 4h.
Derivados (se generan del 1m, no se descargan): 2m, 3m.
Segundos (5s,10s,15s,30s): NO aquí — 5 años de velas de 1s serían cientos de GB.
Los segundos van por ventana reciente con `bot.dukascopy_loader`.

Se descarga por CHUNKS de tiempo (ventanas) para no agotar memoria ni tiempos de
espera, se concatena, se quitan duplicados por timestamp y se guarda en
`datasets/real/PAR__CLAVE.csv.gz`. Solo activos reales; corre en la PC (no en cloud).
"""
import gzip
import os

# Intervalo Dukascopy → (constante, clave de archivo interna).
INTERVALOS = [
    ("INTERVAL_MIN_1", "M1"), ("INTERVAL_MIN_5", "tf300"),
    ("INTERVAL_MIN_10", "tf600"), ("INTERVAL_MIN_15", "tf900"),
    ("INTERVAL_MIN_30", "tf1800"), ("INTERVAL_HOUR_1", "tf3600"),
    ("INTERVAL_HOUR_4", "tf14400"),
]
COLS = ["timestamp", "open", "high", "low", "close", "volume"]
VENTANA_DIAS = 180                # tamaño de cada chunk de descarga


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


def descargar_intervalo(par, interval_const, clave, anios, destino):
    """Descarga un intervalo por chunks de VENTANA_DIAS y guarda. Devuelve nº velas."""
    import datetime as dt

    import dukascopy_python as duka
    from bot.dukascopy_loader import instrumento_de, _a_formato

    inst = instrumento_de(par)
    if inst is None:
        return 0
    interval = getattr(duka, interval_const)
    fin = dt.datetime.now(dt.timezone.utc)
    inicio_total = fin - dt.timedelta(days=int(anios * 365))
    dfs = []
    cursor = inicio_total
    while cursor < fin:
        ventana_fin = min(cursor + dt.timedelta(days=VENTANA_DIAS), fin)
        try:
            df = duka.fetch(inst, interval, duka.OFFER_SIDE_BID, cursor, ventana_fin)
            if df is not None and len(df):
                dfs.append(_a_formato(df))
        except Exception as e:
            print(f"    ({clave} {cursor.date()}→{ventana_fin.date()} error: {repr(e)[:60]})")
        cursor = ventana_fin
    salida = os.path.join(destino, f"{par}__{clave}.csv.gz")
    return _fusionar_guardar(dfs, salida)


def descargar_par(par, anios=5, destino="datasets/real"):
    """Descarga 1m→4h de un par a `anios` años y deriva 2m/3m. Devuelve resumen."""
    from bot.resamplear import derivar_par

    print(f"  {par}: descargando {anios} años (1m→4h)…")
    total = {}
    for interval_const, clave in INTERVALOS:
        n = descargar_intervalo(par, interval_const, clave, anios, destino)
        total[clave] = n
        print(f"    {clave:8} {n:>8} velas")
    # Derivar 2m y 3m del 1m recién bajado.
    m1 = os.path.join(destino, f"{par}__M1.csv.gz")
    if os.path.exists(m1):
        hechos = derivar_par(m1, sobrescribir=True)
        print(f"    derivados: {', '.join(f'{c}({n})' for c, n in hechos) or 'nada'}")
    return total


def descargar_todos(pares=None, anios=5, destino="datasets/real"):
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    print(f"DESCARGA PROFUNDA · {len(pares)} pares · {anios} años · 1m→4h → {destino}/")
    print("(Puede tardar horas. Los segundos van aparte con dukascopy_loader.)\n")
    for p in pares:
        try:
            descargar_par(p, anios, destino)
        except Exception as e:
            print(f"  {p}: ERROR {repr(e)[:100]}")
    print("\nListo. Corre el estudio para ver la profundidad ganada.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Descarga profunda 1m→4h de Dukascopy.")
    ap.add_argument("pares", nargs="*", help="EURUSD GBPUSD ... (vacío = los 22)")
    ap.add_argument("--anios", type=float, default=5, help="años hacia atrás (def 5)")
    a = ap.parse_args()
    descargar_todos(a.pares or None, a.anios)
