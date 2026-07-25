"""
bot/aprendizaje_cuantico.py
===========================
LA MÁQUINA: la fórmula cuántica que APRENDE de la historia. En vez de pesos fijos,
aprende del historial profundo (todos los tiempos) qué COMBINACIÓN de eventos hace
que una señal gane, y produce una PROBABILIDAD. El bot opera solo cuando esa
probabilidad es alta.

Integra el tiempo Y los eventos en ese tiempo (la visión):
  - Alineación multi-temporalidad (fuerza, fractal, nº de tiempos que confirman).
  - Régimen del mercado (tendencia / rango).
  - Sesión horaria (Asia / Europa / EEUU).
  - Eventos: manipulación (spike/congelado/errático), indecisión (doji), ir contra la
    tendencia mayor, consenso extremo, recorrido de la vela.

Cómo aprende, sin trampa: construye (features -> ganó/perdió) sobre el TRAIN
(2003→corte) y ajusta una regresión logística (la "fórmula": suma ponderada de
eventos -> probabilidad). Luego mide en el TEST (corte→hoy, que nunca vio) el
win-rate al subir el umbral de probabilidad. Si al exigir más probabilidad el acierto
sube por encima del break-even (52.08%), la máquina aprendió algo real.

Guarda la fórmula aprendida en `formula_cuantica.json` para que el bot la use en vivo.
Sin red salvo lectura de .csv.gz. Test: bot/test_aprendizaje_cuantico.py.
"""
import json
import math
import os

import numpy as np

from bot.backtest_real import (BREAKEVEN, VENTANA, EXPIRIES, EXP_REF,
                               _cargar_par, _frames_en, _regimen_de, _salida_idx)
from bot.backtest_real_v2 import _fecha_ms, _rejilla, CORTE, GRID_CONF, MIN_SENALES_TRAIN
from bot.backtest_real_v3 import _sesion, _n_conf, _wr_de
from bot.deep_analysis import DeepAnalyzer
from bot.manipulation import ManipulationGuard
from bot.candle_patterns import detect_patterns

PAYOUT = 0.92
# Nombres de los eventos que entran a la fórmula (en orden de columna).
FEATURES = ("fuerza", "fractal", "n_conf", "slide", "oscillate",
            "asia", "europa", "eeuu", "manip", "doji", "contra", "consenso", "rango")
UMBRALES_PROB = (0.50, 0.55, 0.60, 0.65, 0.70)   # umbrales de probabilidad a evaluar


def _contexto(frames):
    """Eventos calculables de la vela de 1m: manipulación, doji, recorrido relativo."""
    f60 = frames.get(60)
    if f60 is None or len(f60) < 20:
        return 0, 0, 0.0
    close = f60["close"]
    ref = float(close.iloc[-1]) or 1.0
    rango = (float(f60["high"].max()) - float(f60["low"].min())) / ref
    manip = 1 if ManipulationGuard().check(close.to_numpy(dtype=float)).get("suspicious") else 0
    doji = 1 if detect_patterns(f60).get("indecision") else 0
    return manip, doji, rango


def _fila(r, reg, sesion, ctx):
    """Vector de eventos (features) de UNA señal, en el orden de FEATURES."""
    manip, doji, rango = ctx
    return [
        float(r.get("fuerza", 0.0)),
        float(r.get("alineacion_fractal", 0.0)),
        _n_conf(r.get("coinciden", "")) / 8.0,
        1.0 if reg == "slide" else 0.0,
        1.0 if reg == "oscillate" else 0.0,
        1.0 if sesion == "asia" else 0.0,
        1.0 if sesion == "europa" else 0.0,
        1.0 if sesion == "eeuu" else 0.0,
        float(manip),
        float(doji),
        1.0 if r.get("contra_tendencia") else 0.0,
        1.0 if r.get("consenso_extremo") else 0.0,
        min(rango, 0.02) * 50.0,                 # recorrido normalizado (~0..1)
    ]


def _recolectar(datos, analyzer, ts_m1, close_m1, idxs, ventana, ref_exp):
    """Devuelve (X, y): eventos y etiqueta ganó(1)/perdió(0) al expiry de referencia,
    para cada señal accionable (OPERAR u OPCIONAL con dirección)."""
    X, y = [], []
    for i in idxs:
        T = int(ts_m1[i]) + 60_000
        try:
            frames = _frames_en(datos, T, ventana)
            if 60 not in frames:
                continue
            reg = _regimen_de(frames)
            r = analyzer.analyze_frames(frames, regimen=reg)
        except Exception:
            continue
        v = r.get("veredicto", "")
        if "OPERAR" not in v and "OPCIONAL" not in v:      # necesita dirección clara
            continue
        if "NO OPERAR" in v:
            continue
        d = r.get("direccion", "")
        lado = 1 if "CALL" in d else (-1 if "PUT" in d else 0)
        if lado == 0:
            continue
        j = _salida_idx(ts_m1, int(ts_m1[i]) + ref_exp * 1000, tol_ms=120_000)
        if j is None:
            continue
        dif = close_m1[j] - close_m1[i]
        if dif == 0:
            continue
        gano = 1 if (dif > 0) == (lado == 1) else 0
        hora = int((int(ts_m1[i]) // 3_600_000) % 24)
        X.append(_fila(r, reg, _sesion(hora), _contexto(frames)))
        y.append(gano)
    return np.array(X, dtype=float), np.array(y, dtype=float)


def _entrenar(X, y, iters=600, lr=0.3, l2=1e-3):
    """Regresión logística por descenso de gradiente (la fórmula: pesos por evento).
    Devuelve (w, b). X ya estandarizado."""
    n, d = X.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(iters):
        z = X @ w + b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        err = p - y
        w -= lr * (X.T @ err / n + l2 * w)
        b -= lr * float(err.mean())
    return w, b


def _prob(X, w, b):
    return 1.0 / (1.0 + np.exp(-np.clip(X @ w + b, -30, 30)))


def _pnl(wr_pct):
    """P&L por operación (%) con payout 92% dado un win-rate en %."""
    p = wr_pct / 100.0
    return (p * PAYOUT - (1 - p)) * 100.0


def aprender(destino="datasets/real", pares=None, corte=CORTE, train_n=300,
             test_n=400, ventana=VENTANA, ref_exp=EXP_REF):
    """Entrena la fórmula en train, la mide en test y la guarda. Devuelve dict con el
    resultado OOS por umbral de probabilidad."""
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    corte_ms = _fecha_ms(corte)
    Xtr_l, ytr_l, Xte_l, yte_l = [], [], [], []
    print(f"APRENDIZAJE CUÁNTICO sobre {destino}/  ·  train hasta {corte} / test después")
    print("=" * 74)
    for par in pares:
        datos = _cargar_par(par, destino)
        if 60 not in datos:
            print(f"  {par:8} sin datos")
            continue
        ts_m1, df_m1 = datos[60]
        close_m1 = df_m1["close"].to_numpy(dtype=float)
        tf_max, max_exp = max(datos.keys()), max(EXPIRIES)
        tr = _rejilla(ts_m1, ts_m1[0], corte_ms, train_n, tf_max, ventana, max_exp)
        te = _rejilla(ts_m1, corte_ms, ts_m1[-1], test_n, tf_max, ventana, max_exp)
        if len(tr) < 10 or len(te) < 10:
            print(f"  {par:8} muestra corta")
            continue
        an = DeepAnalyzer(timeframes=tuple(sorted(datos.keys())), min_conf=0.18)
        Xa, ya = _recolectar(datos, an, ts_m1, close_m1, tr, ventana, ref_exp)
        Xb, yb = _recolectar(datos, an, ts_m1, close_m1, te, ventana, ref_exp)
        if len(ya):
            Xtr_l.append(Xa); ytr_l.append(ya)
        if len(yb):
            Xte_l.append(Xb); yte_l.append(yb)
        print(f"  {par:8} train={len(ya):4}  test={len(yb):4}")

    if not Xtr_l or not Xte_l:
        print("Sin muestras suficientes.")
        return {}
    Xtr = np.vstack(Xtr_l); ytr = np.concatenate(ytr_l)
    Xte = np.vstack(Xte_l); yte = np.concatenate(yte_l)

    # Estandarizar con estadística de TRAIN (el test usa la misma, no se recalibra).
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    w, b = _entrenar((Xtr - mu) / sd, ytr)
    pte = _prob((Xte - mu) / sd, w, b)

    base_wr = float(yte.mean()) * 100.0
    print("=" * 74)
    print(f"TEST (fuera de muestra): {len(yte)} señales  ·  break-even {BREAKEVEN:.2f}%")
    print(f"Base (operar TODAS): win-rate {base_wr:.2f}%  ·  P&L/op {_pnl(base_wr):+.2f}%\n")
    print(f"{'prob>=':>7}{'senales':>9}{'win-rate':>11}{'margen':>8}{'P&L/op':>9}  veredicto")
    salida = {"base_win_rate": round(base_wr, 2), "umbrales": {}}
    for thr in UMBRALES_PROB:
        sel = pte >= thr
        n = int(sel.sum())
        if n < 30:
            print(f"{thr:>7.2f}{n:>9}{'pocas':>11}")
            continue
        wr = float(yte[sel].mean()) * 100.0
        margen = 1.96 * math.sqrt((wr/100)*(1-wr/100)/n) * 100
        gana = "GANA" if wr - margen > BREAKEVEN else (
               "PIERDE" if wr + margen < BREAKEVEN else "INCIERTO")
        print(f"{thr:>7.2f}{n:>9}{wr:>10.2f}%{'±'+format(margen,'.1f'):>8}"
              f"{_pnl(wr):>+8.2f}%  {gana}")
        salida["umbrales"][f"{thr:.2f}"] = {"n": n, "win_rate": round(wr, 2),
                                            "pnl": round(_pnl(wr), 2)}

    # Guardar la fórmula aprendida para que el bot la use en vivo.
    ruta = os.path.join(destino, "formula_cuantica.json")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"features": list(FEATURES), "mean": mu.tolist(),
                       "std": sd.tolist(), "w": w.tolist(), "b": float(b),
                       "ref_exp": ref_exp, "payout": PAYOUT}, f, indent=2)
        print(f"\nFórmula guardada en {ruta}")
    except OSError as e:
        print(f"\nNo se pudo guardar la fórmula: {e}")
    print("=" * 74)
    print("Si al exigir más probabilidad el win-rate sube sobre 52.08% con margen y "
          "P&L positivo, la máquina aprendió a elegir. Ese umbral es el del bot.")
    return salida


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Aprendizaje cuántico (fórmula que aprende).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--corte", default=CORTE)
    ap.add_argument("--train", type=int, default=300)
    ap.add_argument("--test", type=int, default=400)
    a = ap.parse_args()
    aprender(a.destino, a.pares or None, a.corte, a.train, a.test)
