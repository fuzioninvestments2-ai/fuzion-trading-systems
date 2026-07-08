"""
bot/dukascopy_loader.py
=======================
Descarga velas SUB-MINUTO reales de FX desde Dukascopy (fuente legítima y gratuita
de datos tick/segundo) y arma las temporalidades 5s, 10s, 15s, 30s que Yahoo NO da.

EL PORQUÉ: Yahoo no entrega nada por debajo de 1 minuto. Para 5s-30s hace falta
dato por segundo; Dukascopy lo publica. Se bajan velas de 1 segundo y se agrupan en
bloques de 5/10/15/30s (open=primero, close=último, high/low del bloque) — sin
inventar nada, es el mismo dato agregado.

⚠️ HONESTIDAD Y LÍMITES:
  - El dato por segundo es PESADO: se baja una ventana corta (por defecto 3 días).
  - Solo activos REALES (no OTC; los OTC son sintéticos de PO).
  - Requiere `pip install dukascopy-python` y conexión (no corre en el cloud, sí en tu PC).

Uso:
  python -m bot.dukascopy_loader EURUSD GBPUSD        # esos pares, 3 días
  python -m bot.dukascopy_loader                      # los 22 del perfil REAL
  python -m bot.dukascopy_loader --dias 5 EURUSD

SRP: solo descarga sub-minuto y guarda en datasets/real/. Testeable (mapeo y
resampleo) sin red.
"""
import gzip
import os

from bot.resamplear import resamplear

SEGUNDOS_OBJETIVO = [5, 10, 15, 30]      # velas que se construyen desde 1s
CLAVE = {5: "tf5", 10: "tf10", 15: "tf15", 30: "tf30"}
COLS = ["timestamp", "open", "high", "low", "close", "volume"]


def instrumento_de(par):
    """
    Traduce 'EURUSD' → constante de instrumento de dukascopy (INSTRUMENT_..._EUR_USD).
    Busca por sufijo para no hardcodear la categoría (MAJORS/CROSSES). None si no está.
    """
    from dukascopy_python import instruments as ins
    sufijo = f"{par[:3]}_{par[3:]}".upper()              # EURUSD → EUR_USD
    for nombre in dir(ins):
        if nombre.startswith("INSTRUMENT_") and nombre.endswith(sufijo):
            return getattr(ins, nombre)
    return None


def _a_formato(df):
    """Normaliza el DataFrame de dukascopy a timestamp(ms)+OHLC+volume ordenado."""
    import pandas as pd
    d = df.copy()
    d.columns = [str(c).lower() for c in d.columns]
    # El tiempo suele venir como índice datetime; lo pasamos a ms epoch. Se fuerza
    # resolución de ms explícita (pandas 3.0 puede usar ns o µs internamente; una
    # conversión ingenua daría segundos o µs por error).
    if "timestamp" not in d.columns:
        idx = pd.to_datetime(d.index, utc=True).tz_localize(None)
        d = d.reset_index(drop=True)
        d["timestamp"] = idx.values.astype("datetime64[ms]").astype("int64")
    for c in ("open", "high", "low", "close"):
        if c not in d.columns:
            raise ValueError(f"falta columna {c} en datos de Dukascopy")
    if "volume" not in d.columns:
        d["volume"] = 0.0
    return d.sort_values("timestamp")[COLS].reset_index(drop=True)


def _guardar(df, ruta):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with gzip.open(ruta, "wt", encoding="utf-8") as gz:
        df.to_csv(gz, index=False)


def bajar_par(par, dias=3, destino="datasets/real"):
    """Baja 1s de `par` los últimos `dias` y guarda 5s/10s/15s/30s. Devuelve resumen."""
    import datetime as dt

    import dukascopy_python as duka

    inst = instrumento_de(par)
    if inst is None:
        print(f"  {par}: sin instrumento en Dukascopy (¿nombre?)")
        return []
    fin = dt.datetime.now(dt.timezone.utc)
    ini = fin - dt.timedelta(days=dias)
    df = duka.fetch(inst, duka.INTERVAL_SEC_1, duka.OFFER_SIDE_BID, ini, fin)
    if df is None or len(df) == 0:
        print(f"  {par}: Dukascopy no devolvió datos (fin de semana / rango)")
        return []
    base = _a_formato(df)
    hechos = []
    for seg in SEGUNDOS_OBJETIVO:
        vela = resamplear(base, seg)                     # agrupa 1s → seg
        if len(vela) < 2:
            continue
        ruta = os.path.join(destino, f"{par}__{CLAVE[seg]}.csv.gz")
        _guardar(vela, ruta)
        hechos.append((CLAVE[seg], len(vela)))
    etqs = ", ".join(f"{c}({n})" for c, n in hechos) or "nada"
    print(f"  {par}: {len(base)} velas 1s → {etqs}")
    return hechos


def bajar_todos(pares=None, dias=3, destino="datasets/real"):
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    print(f"Descargando sub-minuto (5s-30s) de {len(pares)} pares, {dias} días, "
          f"desde Dukascopy → {destino}/")
    total = []
    for p in pares:
        try:
            total.extend(bajar_par(p, dias, destino))
        except Exception as e:
            print(f"  {p}: ERROR {repr(e)[:120]}")
    print(f"\nListo. {len(total)} archivos de segundos generados.")
    return total


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Baja velas 5s-30s de FX desde Dukascopy.")
    ap.add_argument("pares", nargs="*", help="EURUSD GBPUSD ... (vacío = los 22)")
    ap.add_argument("--dias", type=int, default=3, help="días hacia atrás (pesado)")
    a = ap.parse_args()
    bajar_todos(a.pares or None, a.dias)
