"""
bot/tabla_reversion.py
======================
Afila la máquina: calcula el borde de reversión POR PAR (no un promedio) sobre el
historial real, midiendo SOLO en la parte fuera de muestra (último 40% del tiempo), y
lo guarda en `reversion_tabla.json`. Así cada señal usa la probabilidad de SU par.

Para cada par y cada tamaño de pico, el win-rate OOS de revertir a 3 minutos. Solo se
guardan los tramos con acierto por encima del break-even (52.08%) y con muestra
suficiente — los demás no se operan.

Corre sobre datasets/real (M1). Sin red. Test: bot/test_tabla_reversion.py.
"""
import json
import os

import numpy as np
import pandas as pd

from bot.backtest_reversion_real import (_pip, _rutas, MAX_PIPS, FRAC_IS, UMBRALES,
                                         BREAKEVEN)

REF_EXP_MIN = 3                              # vencimiento de referencia (minutos)
EXPIRIES_TABLA = (1, 2, 3, 5)               # tiempos para los que se calcula el borde
MIN_OPS = 400                               # mínimo de operaciones OOS para fiarse del tramo


def tabla_par(c, par, ref=REF_EXP_MIN):
    """Devuelve [(umbral_pips, win_rate_oos, n)] del par, solo tramos OOS con >=MIN_OPS
    operaciones y win-rate por encima del break-even."""
    n = len(c)
    if n < 300:
        return []
    pip = _pip(par)
    mov = (c[1:] - c[:-1]) / pip
    sm = np.sign(mov)
    idx = np.arange(1, n)
    split = max(1, int(n * FRAC_IS))         # inicio del tramo OOS
    out = []
    for u in UMBRALES:
        base = (np.abs(mov) >= u) & (np.abs(mov) <= MAX_PIPS) & (sm != 0)
        valido = base & (idx + ref <= n - 1) & (idx >= split)   # solo OOS
        if not valido.any():
            continue
        i = idx[valido]
        ret = c[i + ref] - c[i]
        res = ret != 0
        gana = (np.sign(ret) == -sm[i - 1]) & res
        w = int((gana & res).sum())
        l = int((~gana & res).sum())
        if w + l >= MIN_OPS:
            wr = round(w / (w + l) * 100.0, 2)
            if wr > BREAKEVEN:               # solo tramos que ganan
                out.append((u, wr, w + l))
    return out


def construir(destino="datasets/real", pares=None):
    """Calcula el borde por par Y por tiempo (1/2/3/5m) y lo guarda en
    reversion_tabla.json con formato {par: {'1':[[u,wr]], '2':..., '3':..., '5':...}}.
    Devuelve el dict."""
    rutas = _rutas(destino)
    if pares:
        rutas = [r for r in rutas if os.path.basename(r).split("__")[0] in pares]
    tabla = {}
    print(f"TABLA DE REVERSIÓN POR PAR Y TIEMPO sobre {destino}/  "
          f"(OOS, tiempos {EXPIRIES_TABLA})")
    print("=" * 66)
    for r in rutas:
        par = os.path.basename(r).split("__")[0]
        try:
            c = pd.read_csv(r).sort_values("timestamp")["close"].astype(float).to_numpy()
        except Exception as e:
            print(f"  {par:8} ERROR {e}")
            continue
        por_tiempo = {}
        resumen = []
        for exp in EXPIRIES_TABLA:
            tr = tabla_par(c, par, exp)
            if tr:
                por_tiempo[str(exp)] = [[u, wr] for u, wr, _ in tr]
                mejor = max(tr, key=lambda x: x[1])
                resumen.append(f"{exp}m:{mejor[1]:.0f}%")
            else:
                resumen.append(f"{exp}m:-")
        if por_tiempo:
            tabla[par] = por_tiempo
            print(f"  {par:8} " + "  ".join(resumen))
        else:
            print(f"  {par:8} sin borde por encima del break-even")
    ruta = os.path.join(destino, "reversion_tabla.json")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(tabla, f, indent=2)
        print("=" * 60)
        print(f"Guardada: {ruta}  ({len(tabla)} pares con borde)")
    except OSError as e:
        print(f"No se pudo guardar: {e}")
    return tabla


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Tabla de reversión por par (real).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = todos)")
    ap.add_argument("--destino", default="datasets/real")
    a = ap.parse_args()
    construir(a.destino, a.pares or None)
