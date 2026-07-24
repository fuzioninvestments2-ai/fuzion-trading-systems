"""
bot/backtest_real.py
====================
BACKTEST HONESTO del bot REAL (FX) sobre `datasets/real/`.

Corre EL MISMO motor que el bot usa en vivo para el mercado real: `DeepAnalyzer`
(la "ecuación" multi-temporalidad de `bot/deep_analysis.py`), con los mismos
tiempos que arma `PocketService.analyze` para un activo no-OTC (>=60s) y el mismo
régimen (ADX) desde un tiempo medio. NO usa el motor cuántico OTC.

Por qué existe: hasta ahora ningún backtest medía el motor REAL. Este camina el
historial hacia adelante y, en cada punto, decide con SOLO la historia pasada
(anti look-ahead) igual que en vivo; luego mira si el precio se movió en la
dirección predicha al vencer la opción. El número que salga es el que hay.

HONESTIDAD (decisiones que evitan inflar el resultado):
  - Anti look-ahead: en el instante t solo entran velas YA CERRADAS (una vela de
    `tf` seg no está cerrada hasta `inicio_vela + tf`).
  - Sin ajuste sobre el test: `learned=None` (no se aprenden pesos por activo con
    los mismos datos que se evalúan) y `min_conf` FIJO (no se calibra el umbral
    sobre el propio historial que se mide). En vivo el bot calibra por activo, lo
    que puede mejorar o empeorar; aquí se deja el umbral base para no hacer trampa.
  - Solo cuenta el veredicto fuerte "OPERAR" (no "OPCIONAL"): mide la señal que el
    bot marcaría como accionable.
  - Los filtros de protección que dependen de datos EN VIVO (payout, spread,
    manipulación, noticias) no se aplican aquí: en vivo solo RESTAN señales, así
    que este backtest es, si acaso, un techo optimista del NÚMERO de señales.

Break-even: con payout 92%, hace falta > 52.08% de aciertos para ganar a la larga.

Sin red. Se prueba en `bot/test_backtest_real.py`.
"""
import glob
import math
import os

import numpy as np
import pandas as pd

from bot.deep_analysis import DeepAnalyzer
from bot.scoring_strategy import regime as _regime

# Tiempos que el bot REAL lee en vivo: la escalera >= 60s (ver pocket_service._FULL
# filtrado para no-OTC). Los que no tengan archivo se ignoran solos.
TFS_REAL = (60, 120, 180, 240, 300, 600, 900, 1800, 3600, 7200, 14400, 86400)

PAYOUT = 0.92
BREAKEVEN = 1.0 / (1.0 + PAYOUT) * 100          # 52.08%: umbral de rentabilidad
VENTANA = 80                                    # velas de contexto por tiempo
MIN_CONF = 0.18                                 # umbral base del bot en vivo (fallback)
# Horizontes de la opción que opera el trader: 1m, 2m, 3m, 5m, 10m.
EXPIRIES = (60, 120, 180, 300, 600)
EXP_REF = 180                                   # expiry de referencia para la tabla por par


def _clave(tf):
    """Nombre de archivo por tiempo: 60 -> 'M1', el resto 'tf<segundos>'."""
    return "M1" if tf == 60 else f"tf{tf}"


def _cargar_par(par, destino):
    """Carga los .csv.gz de cada tiempo del par. Devuelve {tf: (ts_np, df)} solo de
    los tiempos con archivo y datos suficientes."""
    datos = {}
    for tf in TFS_REAL:
        ruta = os.path.join(destino, f"{par}__{_clave(tf)}.csv.gz")
        if not os.path.exists(ruta):
            continue
        try:
            df = pd.read_csv(ruta)
        except Exception:                        # archivo corrupto: se ignora ese tiempo
            continue
        if df is None or len(df) < 20:
            continue
        df = df.sort_values("timestamp").reset_index(drop=True)
        datos[tf] = (df["timestamp"].to_numpy(dtype=np.int64), df)
    return datos


def _frames_en(datos, T, ventana):
    """Arma {tf: DataFrame} con SOLO las velas cerradas hasta el instante T (ms).
    Una vela de `tf` seg que empieza en `ts` cierra en `ts + tf*1000`; entra si su
    cierre <= T. Se toma la ventana final para que los indicadores lean local."""
    frames = {}
    for tf, (ts, df) in datos.items():
        cut = int(np.searchsorted(ts, T - tf * 1000, side="right"))   # nº velas cerradas
        if cut < 6:                              # mínimo de DeepAnalyzer para opinar
            continue
        ini = max(0, cut - ventana)
        frames[tf] = df.iloc[ini:cut]
    return frames


def _regimen_de(frames):
    """Régimen (slide/oscillate/mixto) desde un tiempo medio con >=20 velas, igual
    que pocket_service (prueba 60, 180, 300 en ese orden)."""
    for tfm in (60, 180, 300):
        fm = frames.get(tfm)
        if fm is not None and len(fm) >= 20:
            reg, _ = _regime(fm["high"], fm["low"], fm["close"])
            return reg
    return None


def _salida_idx(ts_m1, t_exit, tol_ms):
    """Índice del M1 cuya apertura es t_exit (ms). None si cae en un hueco (fin de
    semana/cierre) más grande que la tolerancia -> esa señal no se resuelve."""
    j = int(np.searchsorted(ts_m1, t_exit, side="left"))
    if j >= len(ts_m1):
        return None
    if abs(int(ts_m1[j]) - t_exit) > tol_ms:
        return None
    return j


def backtest_par(par, destino="datasets/real", min_conf=MIN_CONF,
                 max_decisiones=500, ventana=VENTANA, expiries=EXPIRIES):
    """Walk-forward de un par. Devuelve dict con señales y wins/losses/empates por
    expiry. None si no hay M1 o hay muy pocos datos."""
    datos = _cargar_par(par, destino)
    if 60 not in datos:                          # sin M1 no hay reloj ni resolución
        return None
    ts_m1, df_m1 = datos[60]
    close_m1 = df_m1["close"].to_numpy(dtype=float)
    if len(ts_m1) < 200:
        return None

    # Mismo motor que en vivo: los tiempos disponibles del par y el umbral base.
    analyzer = DeepAnalyzer(timeframes=tuple(sorted(datos.keys())), min_conf=min_conf)

    # Rejilla de decisiones: puntos M1 uniformemente espaciados, con warmup al inicio
    # (contexto para el tiempo más largo) y colchón al final (para resolver el expiry
    # más largo). Espaciar evita concentrar todo en un solo tramo del historial.
    tf_max = max(datos.keys())
    max_exp = max(expiries)
    t0 = int(ts_m1[0]) + tf_max * ventana * 1000
    t_fin = int(ts_m1[-1]) - max_exp * 1000
    ini = int(np.searchsorted(ts_m1, t0, side="left"))
    fin = int(np.searchsorted(ts_m1, t_fin, side="right"))
    if fin - ini < 10:
        return None
    idxs = np.unique(np.linspace(ini, fin - 1,
                                 min(max_decisiones, fin - ini)).astype(int))

    señales = 0
    res_exp = {e: [0, 0, 0] for e in expiries}   # e -> [wins, losses, empates]
    for i in idxs:
        T = int(ts_m1[i]) + 60_000               # instante del cierre de la vela M1 i
        try:
            frames = _frames_en(datos, T, ventana)
            if 60 not in frames:
                continue
            r = analyzer.analyze_frames(frames, regimen=_regimen_de(frames))
        except Exception:                        # una decisión mala no corta el par
            continue
        v = r.get("veredicto", "")
        if not (v.endswith("OPERAR") and "NO OPERAR" not in v):   # solo señal fuerte
            continue
        d = r.get("direccion", "")
        if "CALL" in d:
            lado = 1
        elif "PUT" in d:
            lado = -1
        else:
            continue
        señales += 1
        entrada = close_m1[i]
        for e in expiries:
            # Opción entrada al cierre de la vela i; vence e seg después -> M1 cuyo
            # inicio es ts_m1[i] + e. Tolerancia de ~2 velas para no cruzar huecos.
            j = _salida_idx(ts_m1, int(ts_m1[i]) + e * 1000, tol_ms=120_000)
            if j is None:
                continue
            dif = close_m1[j] - entrada
            if dif == 0:
                res_exp[e][2] += 1
            elif (dif > 0 and lado == 1) or (dif < 0 and lado == -1):
                res_exp[e][0] += 1
            else:
                res_exp[e][1] += 1
    return {"par": par, "decisiones": int(len(idxs)),
            "señales": señales, "exp": res_exp}


def _wr(wins, losses):
    """Win-rate % y margen 95% (±1.96*sqrt(p(1-p)/n)). None si no hay resueltas."""
    n = wins + losses
    if not n:
        return None, None, 0
    p = wins / n
    margen = 1.96 * math.sqrt(p * (1 - p) / n) * 100
    return p * 100, margen, n


def correr(destino="datasets/real", pares=None, min_conf=MIN_CONF,
           max_decisiones=500, expiries=EXPIRIES):
    """Corre el backtest sobre todos los pares y agrega el win-rate global por expiry."""
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)

    glob_exp = {e: [0, 0, 0] for e in expiries}  # acumulado global por expiry
    tot_señales = 0
    filas = 0
    print(f"BACKTEST REAL (motor DeepAnalyzer) sobre {destino}/  ·  "
          f"min_conf={min_conf}  ·  {max_decisiones} decisiones/par")
    print("=" * 66)
    for par in pares:
        try:
            res = backtest_par(par, destino, min_conf, max_decisiones,
                               expiries=expiries)
        except Exception as e:                   # robustez: un par malo no corta todo
            print(f"  {par:8} ERROR {e}")
            continue
        if not res:
            print(f"  {par:8} sin datos suficientes")
            continue
        filas += 1
        tot_señales += res["señales"]
        for e in expiries:
            for k in range(3):
                glob_exp[e][k] += res["exp"][e][k]
        w, l, _ = res["exp"].get(EXP_REF, res["exp"][expiries[0]])[:3]
        wr, margen, n = _wr(w, l)
        wr_txt = f"{wr:.1f}% ±{margen:.1f}" if wr is not None else "s/señales"
        print(f"  {par:8} señales={res['señales']:4}  "
              f"[{EXP_REF//60}m] W={w:4} L={l:4}  win-rate={wr_txt}")

    print("=" * 66)
    print(f"GLOBAL: {filas} pares · {tot_señales} señales OPERAR")
    print(f"Break-even payout 92%: {BREAKEVEN:.2f}%\n")
    print(f"{'expiry':>7} {'resueltas':>10} {'win-rate':>10} {'margen95':>10}  veredicto")
    resumen = {}
    for e in expiries:
        w, l, emp = glob_exp[e]
        wr, margen, n = _wr(w, l)
        resumen[e] = (wr, margen, n)
        if wr is None:
            print(f"{e//60:>5}m {n:>10} {'s/señales':>10}")
            continue
        gana = "GANA" if wr - margen > BREAKEVEN else (
               "PIERDE" if wr + margen < BREAKEVEN else "INCIERTO")
        print(f"{e//60:>5}m {n:>10} {wr:>9.2f}% {'±'+format(margen,'.2f'):>10}  {gana}")
    print("=" * 66)
    print("GANA = incluso el borde malo del margen supera el break-even. "
          "INCIERTO = el margen cruza el break-even (hacen falta más señales).")
    return resumen, tot_señales


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Backtest honesto del bot REAL (FX).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--min-conf", type=float, default=MIN_CONF)
    ap.add_argument("--decisiones", type=int, default=500,
                    help="decisiones por par (más = más lento, más preciso)")
    a = ap.parse_args()
    correr(a.destino, a.pares or None, a.min_conf, a.decisiones)
