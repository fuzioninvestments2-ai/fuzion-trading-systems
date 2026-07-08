"""
bot/ingest_tradingview.py
=========================
Convierte los CSV exportados de TradingView (carpeta `datos/raw/`) al formato que
lee el pipeline del bot: `datasets/PAR__CLAVE.csv.gz` con columnas
timestamp,open,high,low,close,volume. Así los comandos de estudio/backtest
encuentran los datos sin que tengas que renombrar nada a mano.

Nombre de archivo esperado: `PAR_TIMEFRAME.csv` (ej. `EURUSD_1m.csv`,
`EURUSD_5m.csv`, `GBPJPY_1h.csv`). El par puede llevar barra o guion; se limpia.
Etiquetas de tiempo aceptadas → clave interna:
  1m→M1 · 2m→tf120 · 3m→tf180 · 5m→tf300 · 15m→tf900 · 30m→tf1800 · 1h→tf3600 · 4h→tf14400

Reutiliza el parser ya probado `parse_tv_csv` (robusto a orden/mayúsculas de
columnas y a fechas UNIX o ISO). Sin red. Rechaza activos OTC (no tienen fuente real).
"""
import glob
import gzip
import os

import pandas as pd

from bot.tradingview_import import parse_tv_csv

# Etiqueta de timeframe → (clave de archivo, segundos).
LABEL_CLAVE = {
    "1m": ("M1", 60), "2m": ("tf120", 120), "3m": ("tf180", 180),
    "5m": ("tf300", 300), "15m": ("tf900", 900), "30m": ("tf1800", 1800),
    "1h": ("tf3600", 3600), "4h": ("tf14400", 14400),
}


def _par_y_label(nombre):
    """De 'EURUSD_5m.csv' → ('EURUSD', '5m'). None si no encaja el patrón."""
    base = os.path.basename(nombre)
    for ext in (".csv.gz", ".csv"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
            break
    if "_" not in base:
        return None, None
    par, label = base.rsplit("_", 1)
    par = par.replace("/", "").replace("-", "").upper().strip()
    return par, label.lower().strip()


def ingerir_archivo(ruta, destino="datasets"):
    """Convierte un CSV de TradingView al formato interno. Devuelve (clave, nº velas)."""
    par, label = _par_y_label(ruta)
    if par is None or label not in LABEL_CLAVE:
        return None, 0
    if par.endswith("_OTC") or par.endswith("OTC"):
        return None, 0                                   # OTC no tiene fuente real
    clave, _seg = LABEL_CLAVE[label]
    with open(ruta, "r", encoding="utf-8-sig") as f:
        velas = parse_tv_csv(f.read())
    if not velas:
        return clave, 0
    df = pd.DataFrame(velas).sort_values("timestamp").drop_duplicates("timestamp")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    os.makedirs(destino, exist_ok=True)
    salida = os.path.join(destino, f"{par}__{clave}.csv.gz")
    with gzip.open(salida, "wt", encoding="utf-8") as gz:
        df.to_csv(gz, index=False)
    return salida, len(df)


def ingerir_carpeta(carpeta="datos/raw", destino="datasets"):
    """Ingiere todos los CSV de una carpeta. Devuelve resumen por archivo."""
    rutas = sorted(glob.glob(os.path.join(carpeta, "*.csv"))) + \
        sorted(glob.glob(os.path.join(carpeta, "*.csv.gz")))
    resultados = []
    for r in rutas:
        salida, n = ingerir_archivo(r, destino)
        estado = "OK" if n else ("saltado" if salida is None else "vacío")
        resultados.append((os.path.basename(r), estado, n, salida))
        print(f"  {os.path.basename(r):28} {estado:8} {n:6} velas"
              + (f" → {os.path.basename(salida)}" if salida and n else ""))
    total = sum(n for _, _, n, _ in resultados)
    ok = sum(1 for _, e, n, _ in resultados if n)
    print(f"\nIngeridos {ok}/{len(rutas)} archivos · {total} velas → {destino}/")
    if ok == 0:
        print("Nada ingerido. Revisa: nombre PAR_TIMEFRAME.csv y timeframe válido "
              f"({', '.join(LABEL_CLAVE)}).")
    return resultados


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Ingesta CSV de TradingView → datasets/")
    p.add_argument("--carpeta", default="datos/raw", help="carpeta con los CSV crudos")
    p.add_argument("--destino", default="datasets", help="carpeta de salida")
    a = p.parse_args()
    ingerir_carpeta(a.carpeta, a.destino)
