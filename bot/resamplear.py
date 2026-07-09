"""
bot/resamplear.py
=================
Fabrica las temporalidades DERIVADAS (2m, 3m, 10m, 4h) a partir de las velas de
1m (M1) que ya se descargaron. Una vela de 2m = dos velas de 1m fusionadas
(open de la primera, close de la última, high/low del bloque, volumen sumado).

Por qué: Yahoo entrega 1m, 5m, 15m, 30m directo, pero NO 2m, 3m, 10m, 4h. Como
esos son múltiplos exactos de 1m, se reconstruyen sin inventar nada: es la misma
información agrupada en bloques más grandes. Las sub-minuto (5s-30s) NO se pueden
derivar del 1m (no se puede ir más fino que el dato) → esas necesitan Dukascopy.

Alineación por bloque temporal: bloque = floor(timestamp / (tf*1000)) * (tf*1000),
igual que en el resto del bot (coherente con el análisis en vivo).

SRP: solo agrega velas y guarda. Sin red. Testeable con asserts.
"""
import glob
import gzip
import os

import pandas as pd

# Derivados (segundos) que se generan desde M1 (60s). Todos múltiplos de 60.
DERIVADOS = {"tf120": 120, "tf180": 180, "tf600": 600, "tf14400": 14400}
COLS = ["timestamp", "open", "high", "low", "close", "volume"]


def resamplear(df1m, tf_seg):
    """Agrega velas de 1m a velas de `tf_seg` segundos (bloques alineados)."""
    bloque = (df1m["timestamp"] // (tf_seg * 1000)) * (tf_seg * 1000)
    agg = df1m.groupby(bloque).agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
    )
    agg.index.name = "timestamp"
    return agg.reset_index()[COLS]


def _guardar(df, ruta):
    with gzip.open(ruta, "wt", encoding="utf-8") as gz:
        df.to_csv(gz, index=False)


def derivar_par(ruta_m1, sobrescribir=False, claves=None):
    """
    Desde el archivo M1 de un par, genera los derivados que falten en la misma
    carpeta. `claves`: subconjunto a derivar (None = todos los DERIVADOS). Se usa
    para NO sobreescribir tiempos que ya vienen DIRECTOS de la fuente (10m/4h de
    Dukascopy son más profundos que derivarlos del 1m). Devuelve (clave, nº velas).
    """
    carpeta = os.path.dirname(ruta_m1)
    base = os.path.basename(ruta_m1).split("__")[0]     # 'EURUSD'
    df1m = pd.read_csv(ruta_m1).sort_values("timestamp").reset_index(drop=True)
    if len(df1m) < 40:
        return []
    objetivo = {k: DERIVADOS[k] for k in (claves or DERIVADOS) if k in DERIVADOS}
    hechos = []
    for clave, seg in objetivo.items():
        salida = os.path.join(carpeta, f"{base}__{clave}.csv.gz")
        if os.path.exists(salida) and not sobrescribir:
            continue                                     # ya existe (p.ej. de Yahoo)
        df = resamplear(df1m, seg)
        if len(df) < 2:
            continue
        _guardar(df, salida)
        hechos.append((clave, len(df)))
    return hechos


def _archivos_m1(patron="datasets"):
    """Todos los M1 reales (no OTC), recursivo (datasets/ y datasets/real/)."""
    todas = glob.glob(f"{patron}/**/*__M1.csv.gz", recursive=True)
    return sorted(r for r in todas
                  if "_otc" not in os.path.basename(r).lower()
                  and "/otc/" not in r.replace(os.sep, "/").lower())


def derivar_todos(patron="datasets", sobrescribir=False):
    """Genera los derivados para todos los pares con M1. Devuelve resumen."""
    m1s = _archivos_m1(patron)
    if not m1s:
        print("No hay archivos M1. Primero descarga (historical_loader) y exporta "
              "(dataset_export export REAL).")
        return []
    total = []
    for r in m1s:
        par = os.path.basename(r).split("__")[0]
        hechos = derivar_par(r, sobrescribir)
        etqs = ", ".join(f"{c}({n})" for c, n in hechos) or "nada nuevo"
        print(f"  {par:12} → {etqs}")
        total.extend(hechos)
    print(f"\nGenerados {len(total)} archivos derivados (2m,3m,10m,4h) desde 1m.")
    return total


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Fabrica 2m,3m,10m,4h desde el 1m.")
    p.add_argument("--sobrescribir", action="store_true",
                   help="regenera aunque ya exista el archivo")
    a = p.parse_args()
    derivar_todos(sobrescribir=a.sobrescribir)
