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
import math
import os

import numpy as np
import pandas as pd

from bot.backtest_reversion_real import (_pip, _rutas, MAX_PIPS, FRAC_IS, BREAKEVEN)

REF_EXP_MIN = 3                              # vencimiento de referencia (minutos)
EXPIRIES_TABLA = (1, 2, 3, 5)               # tiempos para los que se calcula el borde
MIN_OPS = 400                               # mínimo de operaciones OOS (a 1m; escala por tiempo)


def _umbrales_tf(tf):
    """Umbrales de pico (pips) a probar en un tiempo de `tf` minutos. La volatilidad de
    los precios escala ~ raíz del tiempo (paseo aleatorio), así que los umbrales de un
    tiempo largo son mayores que los de 1m: se escalan por sqrt(tf). Así el pico que se
    exige en 5m es proporcional a lo que una vela de 5m se mueve de verdad."""
    base = (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20)
    r = math.sqrt(tf)
    return sorted({int(round(u * r)) for u in base if u * r >= 1})


RETARDO_ENTRADA = 1     # velas entre el pico y la ENTRADA (ver abajo). Debe igualar el vivo.


def tabla_par(c, par, tf_min=REF_EXP_MIN, retardo=RETARDO_ENTRADA):
    """Borde de reversión medido en velas de `tf_min` MINUTOS, CON el desfase de entrada
    real. Resamplea los cierres M1 a velas de ese tiempo, mide el pico de cada vela y si
    el precio se devuelve.

    CLAVE (corrección D1): el bot NO entra al cierre del pico, sino en la PRÓXIMA vela
    (te da una vela de margen para programar la orden). Por eso aquí la entrada es
    `cT[i+retardo]` y la salida `cT[i+retardo+1]` — con `retardo=1`, una vela después del
    pico, exactamente como se opera. Así el acierto medido es el que de verdad obtienes,
    no uno idealizado que entra imposible-de-rápido.

    Devuelve [(umbral_pips, win_rate_oos, n)] solo con tramos OOS con muestra y por encima
    del break-even."""
    tf = max(1, int(tf_min))
    ret_v = max(0, int(retardo))
    cT = c[tf - 1::tf] if tf > 1 else c       # cierre al final de cada bloque de tf minutos
    n = len(cT)
    if n < 200:
        return []
    pip = _pip(par)
    mov = (cT[1:] - cT[:-1]) / pip            # pips de cada vela de tf minutos
    sm = np.sign(mov)
    idx = np.arange(1, n)
    split = max(1, int(n * FRAC_IS))          # inicio del tramo OOS
    max_tf = MAX_PIPS * math.sqrt(tf)         # techo de anomalía, también escala con sqrt(tf)
    min_ops = max(50, MIN_OPS // tf)          # menos velas en tiempos largos -> menos exigencia
    out = []
    for u in _umbrales_tf(tf):
        base = (np.abs(mov) >= u) & (np.abs(mov) <= max_tf) & (sm != 0)
        # Entrada `retardo` velas después del pico; salida una vela más allá. Solo OOS.
        valido = base & (idx + ret_v + 1 <= n - 1) & (idx >= split)
        if not valido.any():
            continue
        i = idx[valido]
        ret = cT[i + ret_v + 1] - cT[i + ret_v]        # movimiento DESDE la entrada real
        res = ret != 0
        gana = (np.sign(ret) == -sm[i - 1]) & res      # se devolvió respecto al pico
        w = int((gana & res).sum())
        l = int((~gana & res).sum())
        if w + l >= min_ops:
            wr = round(w / (w + l) * 100.0, 2)
            if wr > BREAKEVEN:                # solo tramos que ganan
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
