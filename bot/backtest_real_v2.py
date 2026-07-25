"""
bot/backtest_real_v2.py
=======================
BACKTEST REAL v2 — el mismo motor (DeepAnalyzer) que `backtest_real`, pero añadiendo
las tres cosas que en vivo SÍ actúan y que en v1 dejé fuera a propósito. Ahora bien
hechas, sin mirar el futuro:

  1) CALIBRACIÓN con separación train/test: por cada par, busco el umbral `min_conf`
     que mejor habría funcionado SOLO en la primera parte del historial (train, hasta
     `--corte`), y lo aplico en la segunda parte (test), que el ajuste NUNCA vio. Así
     la calibración no puede hacer trampa (no aprende sobre lo que se mide).

  2) FILTROS de protección calculables de las velas (los que en vivo restan señales
     malas): mercado plano, manipulación (ManipulationGuard) y doji/indecisión. Los
     que necesitan datos EN VIVO (payout, spread, noticias, vacío de ticks) no se
     pueden aplicar sobre historial y se omiten (se dice, no se esconde).

  3) ESTRATIFICACIÓN por alineación: además del global, parto las señales del test por
     fuerza de alineación (cuántos tiempos coinciden) para ver si el subconjunto MÁS
     alineado tiene borde, aunque el promedio no lo tenga.

El win-rate que cuenta es el del TEST. Break-even payout 92% = 52.08%. Sin red salvo
la lectura de los .csv.gz. Se prueba en `bot/test_backtest_real_v2.py`.
"""
import math
import os

import numpy as np

from bot.backtest_real import (TFS_REAL, BREAKEVEN, VENTANA, EXPIRIES, EXP_REF,
                               _cargar_par, _frames_en, _regimen_de, _salida_idx, _wr)
from bot.deep_analysis import DeepAnalyzer
from bot.scoring_strategy import regime as _regime
from bot.manipulation import ManipulationGuard
from bot.candle_patterns import detect_patterns

# Corte train/test por defecto: ~13 años para aprender, ~10 para medir fuera de muestra.
CORTE = "2016-01-01"
GRID_CONF = (0.15, 0.18, 0.22, 0.28, 0.35)      # umbrales candidatos de calibración
MIN_SENALES_TRAIN = 20                           # nº mínimo para fiarse de un umbral
PLANO_UMBRAL = 0.0004                            # rango < 0.04% en 1m -> mercado plano


def _fecha_ms(fecha):
    """Convierte 'YYYY-MM-DD' a epoch ms (UTC) sin depender de zona horaria del equipo."""
    y, m, d = (int(x) for x in fecha.split("-"))
    # Días desde 1970 por aritmética de calendario proléptico (evita tz local).
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    dias = jdn - 2440588                          # JDN de 1970-01-01
    return dias * 86400 * 1000


def _vetar(frames):
    """Filtros de protección calculables de las velas. True = NO operar (veta la señal)."""
    f60 = frames.get(60)
    if f60 is None or len(f60) < 20:
        return False
    close = f60["close"]
    ref = float(close.iloc[-1]) or 1.0
    # Mercado plano: sin recorrido, la opción es una moneda al aire -> fuera.
    if (float(f60["high"].max()) - float(f60["low"].min())) / ref < PLANO_UMBRAL:
        return True
    # Manipulación: spike que rebota, congelado, estallido o errático -> fuera.
    if ManipulationGuard().check(close.to_numpy(dtype=float)).get("suspicious"):
        return True
    # Doji/indecisión en la última vela cerrada -> el mercado no decide, no entramos.
    if detect_patterns(f60).get("indecision"):
        return True
    return False


def _rejilla(ts_m1, lo_ms, hi_ms, n, tf_max, ventana, max_exp):
    """Índices M1 uniformes dentro de [lo_ms, hi_ms), con warmup y colchón de expiry."""
    t0 = max(int(lo_ms), int(ts_m1[0]) + tf_max * ventana * 1000)
    t_fin = min(int(hi_ms), int(ts_m1[-1]) - max_exp * 1000)
    ini = int(np.searchsorted(ts_m1, t0, side="left"))
    fin = int(np.searchsorted(ts_m1, t_fin, side="right"))
    if fin - ini < 5:
        return np.array([], dtype=int)
    return np.unique(np.linspace(ini, fin - 1, min(n, fin - ini)).astype(int))


def _senales(datos, analyzer, ts_m1, close_m1, idxs, ventana, expiries, filtros):
    """Recorre `idxs` y devuelve las señales OPERAR con su metadata y resultado por
    expiry. Cada señal: {lado, fuerza, fractal, exp:{e:'W'|'L'|'E'|None}}."""
    out = []
    for i in idxs:
        T = int(ts_m1[i]) + 60_000
        try:
            frames = _frames_en(datos, T, ventana)
            if 60 not in frames:
                continue
            r = analyzer.analyze_frames(frames, regimen=_regimen_de(frames))
        except Exception:
            continue
        v = r.get("veredicto", "")
        if not (v.endswith("OPERAR") and "NO OPERAR" not in v):
            continue
        d = r.get("direccion", "")
        lado = 1 if "CALL" in d else (-1 if "PUT" in d else 0)
        if lado == 0:
            continue
        if filtros and _vetar(frames):
            continue
        entrada = close_m1[i]
        res = {}
        for e in expiries:
            j = _salida_idx(ts_m1, int(ts_m1[i]) + e * 1000, tol_ms=120_000)
            if j is None:
                res[e] = None
                continue
            dif = close_m1[j] - entrada
            res[e] = "E" if dif == 0 else ("W" if (dif > 0) == (lado == 1) else "L")
        out.append({"lado": lado, "fuerza": float(r.get("fuerza", 0.0)),
                    "fractal": float(r.get("alineacion_fractal", 0.0)), "exp": res})
    return out


def _wr_de(senales, exp):
    """Win-rate % de una lista de señales a un expiry dado (W/L; E e incompletas fuera)."""
    w = sum(1 for s in senales if s["exp"].get(exp) == "W")
    l = sum(1 for s in senales if s["exp"].get(exp) == "L")
    return _wr(w, l)


def _calibrar(datos, ts_m1, close_m1, train_idxs, ventana, expiries, ref_exp):
    """Elige el min_conf con mejor win-rate en TRAIN (con filtros). Devuelve (min_conf,
    wr_train, n_train). Si ningún umbral junta señales suficientes, cae a 0.18."""
    an = DeepAnalyzer(timeframes=tuple(sorted(datos.keys())))
    mejor = (0.18, None, 0)
    for mc in GRID_CONF:
        an.min_conf = mc
        sig = _senales(datos, an, ts_m1, close_m1, train_idxs, ventana, expiries, True)
        wr, _, n = _wr_de(sig, ref_exp)
        if n >= MIN_SENALES_TRAIN and wr is not None and (mejor[1] is None or wr > mejor[1]):
            mejor = (mc, wr, n)
    return mejor


def backtest_par_v2(par, destino="datasets/real", corte=CORTE, ventana=VENTANA,
                    train_n=200, test_n=350, expiries=EXPIRIES, ref_exp=EXP_REF):
    """Calibra en train, mide en test. Devuelve dict con min_conf elegido y las señales
    de TEST (para estratificar fuera). None si no hay datos."""
    datos = _cargar_par(par, destino)
    if 60 not in datos:
        return None
    ts_m1, df_m1 = datos[60]
    close_m1 = df_m1["close"].to_numpy(dtype=float)
    if len(ts_m1) < 500:
        return None
    tf_max = max(datos.keys())
    max_exp = max(expiries)
    corte_ms = _fecha_ms(corte)

    train_idx = _rejilla(ts_m1, ts_m1[0], corte_ms, train_n, tf_max, ventana, max_exp)
    test_idx = _rejilla(ts_m1, corte_ms, ts_m1[-1], test_n, tf_max, ventana, max_exp)
    if len(train_idx) < 10 or len(test_idx) < 10:
        return None

    mc, wr_tr, n_tr = _calibrar(datos, ts_m1, close_m1, train_idx, ventana,
                                expiries, ref_exp)
    an = DeepAnalyzer(timeframes=tuple(sorted(datos.keys())), min_conf=mc)
    sig_test = _senales(datos, an, ts_m1, close_m1, test_idx, ventana, expiries, True)
    return {"par": par, "min_conf": mc, "wr_train": wr_tr, "n_train": n_tr,
            "senales": sig_test}


def _tabla_estratos(senales, ref_exp):
    """Parte las señales del test por fuerza de alineación y muestra win-rate por banda.
    Sirve para ver si las señales MÁS alineadas ganan aunque el promedio no."""
    bandas = [("alineacion 0.60-0.75", 0.60, 0.75),
              ("alineacion 0.75-0.90", 0.75, 0.90),
              ("alineacion 0.90-1.00", 0.90, 1.01)]
    print(f"\nEstratos por fuerza de alineacion (expiry {ref_exp//60}m):")
    print(f"{'banda':<24}{'senales':>9}{'win-rate':>12}{'veredicto':>12}")
    for nombre, lo, hi in bandas:
        sub = [s for s in senales if lo <= s["fuerza"] < hi]
        wr, margen, n = _wr_de(sub, ref_exp)
        if wr is None:
            print(f"{nombre:<24}{n:>9}{'s/senales':>12}")
            continue
        gana = "GANA" if wr - margen > BREAKEVEN else (
               "PIERDE" if wr + margen < BREAKEVEN else "INCIERTO")
        print(f"{nombre:<24}{n:>9}{wr:>11.1f}%{gana:>12}")


def correr(destino="datasets/real", pares=None, corte=CORTE, train_n=200,
           test_n=350, expiries=EXPIRIES, ref_exp=EXP_REF):
    """Corre la v2 sobre todos los pares y agrega el win-rate de TEST (fuera de muestra)."""
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)

    todas = []                                   # señales de test de todos los pares
    print(f"BACKTEST REAL v2 (calibrado train/test + filtros) sobre {destino}/")
    print(f"train hasta {corte} (~{train_n}/par)  ·  test desde {corte} (~{test_n}/par)")
    print("=" * 72)
    for par in pares:
        try:
            res = backtest_par_v2(par, destino, corte, VENTANA, train_n, test_n,
                                  expiries, ref_exp)
        except Exception as e:
            print(f"  {par:8} ERROR {e}")
            continue
        if not res:
            print(f"  {par:8} sin datos suficientes")
            continue
        todas.extend(res["senales"])
        wr, margen, n = _wr_de(res["senales"], ref_exp)
        wr_txt = f"{wr:.1f}% ±{margen:.1f}" if wr is not None else "s/señales"
        tr = f"{res['wr_train']:.0f}%" if res["wr_train"] is not None else "n/d"
        print(f"  {par:8} min_conf={res['min_conf']:.2f} (train {tr})  "
              f"test[{ref_exp//60}m]={wr_txt}  ({n} señales)")

    print("=" * 72)
    print(f"GLOBAL TEST (fuera de muestra): {len(todas)} señales OPERAR")
    print(f"Break-even payout 92%: {BREAKEVEN:.2f}%\n")
    print(f"{'expiry':>7}{'resueltas':>11}{'win-rate':>11}{'margen95':>11}  veredicto")
    resumen = {}
    for e in expiries:
        wr, margen, n = _wr_de(todas, e)
        resumen[e] = (wr, margen, n)
        if wr is None:
            print(f"{e//60:>5}m{n:>11}{'s/señales':>11}")
            continue
        gana = "GANA" if wr - margen > BREAKEVEN else (
               "PIERDE" if wr + margen < BREAKEVEN else "INCIERTO")
        print(f"{e//60:>5}m{n:>11}{wr:>10.2f}%{'±'+format(margen,'.2f'):>11}  {gana}")
    _tabla_estratos(todas, ref_exp)
    print("=" * 72)
    print("Todo es win-rate de TEST: datos que la calibración NUNCA vio. "
          "GANA solo si el borde malo del margen supera el break-even.")
    return resumen, todas


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Backtest REAL v2 (calibrado + filtros).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--corte", default=CORTE, help="fecha train/test YYYY-MM-DD")
    ap.add_argument("--train", type=int, default=200, help="decisiones de train por par")
    ap.add_argument("--test", type=int, default=350, help="decisiones de test por par")
    a = ap.parse_args()
    correr(a.destino, a.pares or None, a.corte, a.train, a.test)
