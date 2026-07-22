"""
bot/reparar_4h.py
=================
Repara el 4h (tf14400) de los pares ya descargados.

Por qué: un proceso viejo (anterior al fix de `derivar_par`) sobreescribía el 4h
DIRECTO de Dukascopy con uno derivado del 1m. El 1m real empieza ~2012, pero el 4h
directo llega a 2003 → derivarlo del 1m pierde 2003–2011 (p.ej. 38397 → 24835 velas).

Qué hace: re-baja SOLO el 4h DIRECTO y actualiza el estado. NO deriva nada, así que
no puede volver a pisarlo. Idempotente: relanzarlo deja el mismo resultado. Corre en
la PC (usa red). El resto de los tiempos no se tocan.
"""
import gzip
import os
import zlib

from bot.dukascopy_deep import (descargar_intervalo, _cargar_status,
                                _guardar_status)


def _velas(ruta):
    """Cuenta velas de un .csv.gz (filas menos la cabecera). 0 si no existe o está corrupto."""
    if not os.path.exists(ruta):
        return 0
    try:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)
    except (OSError, EOFError, zlib.error):
        return 0                       # corrupto: cuenta como 0, se re-baja igual


def reparar(pares=None, desde="2003-01-01", destino="datasets/real"):
    """Re-baja el 4h directo de cada par. Devuelve {par: (antes, despues)}."""
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    status = _cargar_status(destino)
    resultado = {}
    for i, par in enumerate(pares, 1):
        ruta = os.path.join(destino, f"{par}__tf14400.csv.gz")
        antes = _velas(ruta)
        # descargar_intervalo baja el 4h DIRECTO y reescribe el archivo (sin derivar).
        n = descargar_intervalo(par, "INTERVAL_HOUR_4", "tf14400", desde, destino)
        if n:
            status["completos"].setdefault(par, {})["tf14400"] = n
            _guardar_status(destino, status)
        resultado[par] = (antes, n)
        flecha = "OK" if n >= antes else "REVISAR"
        print(f"[{i}/{len(pares)}] {par:8} 4h: {antes} -> {n} velas  {flecha}")
    print("\nListo. El 4h ahora es el DIRECTO (más profundo, desde 2003). "
          "El resto de tiempos no se tocó.")
    return resultado


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Repara el 4h (tf14400) directo.")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--desde", default="2003-01-01", help="inicio (YYYY-MM-DD)")
    a = ap.parse_args()
    reparar(a.pares or None, a.desde)
