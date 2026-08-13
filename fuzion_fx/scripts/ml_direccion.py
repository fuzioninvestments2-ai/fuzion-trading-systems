"""
scripts/ml_direccion.py (fuzion_fx)
===================================
INTELIGENCIA EXTERNA (machine learning) sobre TU historial real de velas
(candles_real de po_candles.db). En vez de indicadores con pesos fijos, un modelo
APRENDE de los datos a predecir la direccion de la vela siguiente.

HONESTIDAD (regla del proyecto, no negociable):
  - Split CRONOLOGICO: entrena con el PASADO (primer 70%) y mide en el FUTURO
    (ultimo 30%) que el modelo NUNCA vio. Nada de mezclar (shuffle) filas, que
    filtraria el futuro y daria un numero falso e inflado.
  - Sin mirar el futuro en las features: cada fila usa SOLO datos hasta la vela t.
  - Se compara contra el BREAK-EVEN de binarias (con payout 80% hay que acertar
    >55.6% para no perder). Un modelo al 50% NO sirve, aunque "sea IA".
  - Se reporta el acierto a distintos UMBRALES DE CONFIANZA con su COBERTURA: si
    el modelo solo acierta cuando esta MUY seguro, ahi puede haber borde real
    (operar poco y selectivo). Si ni asi cruza, el borde no existe en esta data.

Modelo: GradientBoosting de sklearn si esta instalado (mejor); si no, regresion
logistica propia en numpy (sin dependencias). Ambos miden IGUAL de honesto.

    python fuzion_fx/scripts/ml_direccion.py            # todos los pares (pool)
    python fuzion_fx/scripts/ml_direccion.py EUR/USD    # un par
    python fuzion_fx/scripts/ml_direccion.py --h 3      # horizonte 3 velas
"""

from __future__ import annotations

import os
import sqlite3
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.config import get_bot_config, ROOT                     # noqa: E402

DB = os.path.join(ROOT, "data", "db", "po_candles.db")
BASE_TF = 60
MIN_VELAS = 400                        # sin muestra grande, ML no mide nada
TRAIN_FRAC = 0.70                      # 70% pasado -> entrena, 30% futuro -> mide
PAYOUT = 0.80                          # break-even de binarias con pago 80%
BREAKEVEN = 1.0 / (1.0 + PAYOUT) * 100  # % de acierto para no perder (55.6%)


# --------------------------------------------------------------- indicadores
def _ema(x: np.ndarray, span: int) -> np.ndarray:
    """EMA vectorizada (mismo largo que x). alfa = 2/(span+1)."""
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    """Media movil simple; los primeros n-1 quedan con el promedio parcial."""
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = (c[n:] - c[:-n]) / n
    pad = np.array([x[: i + 1].mean() for i in range(n - 1)])
    return np.concatenate([pad, out])


def _rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    """RSI clasico (Wilder). Devuelve 0..100, mismo largo que close."""
    d = np.diff(close, prepend=close[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    au = _ema(up, n)
    ad = _ema(dn, n)
    rs = au / np.where(ad == 0, 1e-9, ad)
    return 100.0 - 100.0 / (1.0 + rs)


def _rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    """Desvio movil (volatilidad). Primeros n-1: desvio parcial."""
    out = np.empty_like(x, dtype=float)
    for i in range(len(x)):
        lo = max(0, i - n + 1)
        out[i] = x[lo : i + 1].std()
    return out


# --------------------------------------------------------------- features
def construir_features(o, h, l, c, ts, horizonte):
    """
    Matriz X (features hasta la vela t, SIN futuro) y label y (direccion de la vela
    t+horizonte). Devuelve X, y ya alineados y sin NaN. Cada fila = una vela con su
    'foto' hasta ese momento; el label es lo que paso DESPUES (no se usa como
    feature). Empate (mismo precio) se descarta (no cuenta win/loss).
    """
    o = np.asarray(o, float); h = np.asarray(h, float)
    l = np.asarray(l, float); c = np.asarray(c, float)
    ts = np.asarray(ts, float)
    n = len(c)

    ret = np.zeros(n)
    ret[1:] = c[1:] / c[:-1] - 1.0                 # retorno vela a vela
    body = (c - o) / np.where(o == 0, 1e-9, o)     # cuerpo relativo
    rng = (h - l) / np.where(o == 0, 1e-9, o)      # rango relativo
    up_wick = (h - np.maximum(o, c)) / np.where(o == 0, 1e-9, o)
    dn_wick = (np.minimum(o, c) - l) / np.where(o == 0, 1e-9, o)

    ema_f = _ema(c, 9); ema_s = _ema(c, 21)
    ema_spread = (ema_f - ema_s) / c
    rsi = _rsi(c, 14) / 100.0                       # a 0..1
    macd = _ema(c, 12) - _ema(c, 26)
    macd_hist = (macd - _ema(macd, 9)) / c
    sma20 = _sma(c, 20); std20 = _rolling_std(ret, 20)
    pctb = (c - sma20) / np.where(std20 * c == 0, 1e-9, 2.0 * std20 * c)
    mom10 = c / _sma(c, 10) - 1.0
    hora = (ts % 86400) / 86400.0                   # fraccion del dia
    hsin = np.sin(2 * np.pi * hora); hcos = np.cos(2 * np.pi * hora)

    cols = [ret, np.roll(ret, 1), np.roll(ret, 2), np.roll(ret, 3), np.roll(ret, 4),
            body, rng, up_wick, dn_wick, ema_spread, rsi, macd_hist, pctb,
            std20, mom10, hsin, hcos]
    X = np.column_stack(cols)

    # Label: direccion a `horizonte` velas. Ultimas `horizonte` filas no tienen
    # futuro conocido -> se recortan. Primeras 30 filas: indicadores aun calientan.
    fin = n - horizonte
    fut = c[horizonte:fin + horizonte]
    y = (fut > c[:fin]).astype(int)
    empate = fut == c[:fin]
    X = X[:fin]
    ini = 30
    mask = ~empate
    mask[:ini] = False
    return X[mask], y[mask]


# --------------------------------------------------------------- modelo
def _logistica_numpy(Xtr, ytr, Xte, iters=400, lr=0.1, l2=1e-3):
    """Regresion logistica con descenso de gradiente (sin dependencias).
    Estandariza con la media/desvio del TRAIN (no del test: seria mirar el futuro).
    Devuelve probabilidades del test."""
    mu = Xtr.mean(0); sd = Xtr.std(0); sd[sd == 0] = 1.0
    Xtr = (Xtr - mu) / sd
    Xte = (Xte - mu) / sd
    Xtr = np.column_stack([np.ones(len(Xtr)), Xtr])
    Xte = np.column_stack([np.ones(len(Xte)), Xte])
    w = np.zeros(Xtr.shape[1])
    m = len(Xtr)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-Xtr @ w))
        g = Xtr.T @ (p - ytr) / m + l2 * w
        w -= lr * g
    return 1.0 / (1.0 + np.exp(-Xte @ w))


def _modelo(Xtr, ytr, Xte):
    """GradientBoosting (sklearn) si esta; si no, logistica numpy. Devuelve las
    probabilidades del test y el nombre del modelo usado."""
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        clf = GradientBoostingClassifier(max_depth=3, n_estimators=150,
                                         learning_rate=0.05, subsample=0.8)
        clf.fit(Xtr, ytr)
        return clf.predict_proba(Xte)[:, 1], "GradientBoosting(sklearn)"
    except ImportError:
        return _logistica_numpy(Xtr, ytr, Xte), "LogisticaNumpy"


# --------------------------------------------------------------- evaluacion
def evaluar(prob, yte, margenes=(0.0, 0.05, 0.10, 0.15)):
    """Acierto fuera de muestra a distintos umbrales de confianza (|prob-0.5|>=m)
    con su cobertura. Predice 1 si prob>0.5. Devuelve lista de dicts."""
    pred = (prob > 0.5).astype(int)
    ok = (pred == yte)
    conf = np.abs(prob - 0.5)
    filas = []
    for m in margenes:
        sel = conf >= m
        n = int(sel.sum())
        acc = 100.0 * ok[sel].mean() if n else 0.0
        filas.append({"margen": m, "n": n, "acc": acc,
                      "cobertura": 100.0 * n / len(yte) if len(yte) else 0.0})
    return filas


def correr_par(conn, pair, horizonte):
    rows = conn.execute(
        """SELECT open, high, low, close, ts FROM candles_real
           WHERE pair=? AND tf=? ORDER BY ts ASC""", (pair, BASE_TF)).fetchall()
    if len(rows) < MIN_VELAS:
        return None
    o = [r[0] for r in rows]; h = [r[1] for r in rows]
    l = [r[2] for r in rows]; c = [r[3] for r in rows]; ts = [r[4] for r in rows]
    X, y = construir_features(o, h, l, c, ts, horizonte)
    if len(y) < MIN_VELAS // 2:
        return None
    corte = int(len(y) * TRAIN_FRAC)
    Xtr, ytr = X[:corte], y[:corte]
    Xte, yte = X[corte:], y[corte:]
    if len(np.unique(ytr)) < 2 or len(yte) < 50:
        return None
    prob, modelo = _modelo(Xtr, ytr, Xte)
    return {"pair": pair, "n_test": len(yte), "modelo": modelo,
            "eval": evaluar(prob, yte)}


def main() -> None:
    args = [a for a in sys.argv[1:]]
    horizonte = 1
    if "--h" in args:
        i = args.index("--h"); horizonte = int(args[i + 1]); del args[i:i + 2]
    pares = args if args else get_bot_config("f1_m1")["pairs"]

    if not os.path.exists(DB):
        print(f"No existe la base {DB}. Arranca el colector para juntar historial.")
        return
    conn = sqlite3.connect(DB)

    print("ML DIRECCION — inteligencia externa sobre tu historial real")
    print(f"Split cronologico 70/30 (entrena pasado, mide futuro) · horizonte "
          f"{horizonte} vela(s) · break-even {BREAKEVEN:.1f}% (payout 80%)")
    print("=" * 68)
    print(f"{'PAR':10} {'n_test':>7} {'acc':>7} {'acc>0.10':>9} {'cob':>6}  modelo")

    # Pool global: junta las features de todos los pares (mas muestra, un modelo).
    Xall_tr = []; yall_tr = []; Xall_te = []; yall_te = []
    for pair in pares:
        r = correr_par(conn, pair, horizonte)
        if r is None:
            print(f"{pair:10} {'-':>7}  (sin muestra suficiente)")
            continue
        base = r["eval"][0]; conf10 = r["eval"][2]
        print(f"{pair:10} {r['n_test']:>7} {base['acc']:>6.1f}% "
              f"{conf10['acc']:>8.1f}% {conf10['cobertura']:>5.0f}%  {r['modelo']}")

    # Modelo POOL (todos los pares juntos, split cronologico por par y concatenado).
    for pair in pares:
        rows = conn.execute(
            """SELECT open, high, low, close, ts FROM candles_real
               WHERE pair=? AND tf=? ORDER BY ts ASC""", (pair, BASE_TF)).fetchall()
        if len(rows) < MIN_VELAS:
            continue
        o = [r[0] for r in rows]; h = [r[1] for r in rows]
        l = [r[2] for r in rows]; c = [r[3] for r in rows]; ts = [r[4] for r in rows]
        X, y = construir_features(o, h, l, c, ts, horizonte)
        if len(y) < MIN_VELAS // 2:
            continue
        corte = int(len(y) * TRAIN_FRAC)
        Xall_tr.append(X[:corte]); yall_tr.append(y[:corte])
        Xall_te.append(X[corte:]); yall_te.append(y[corte:])

    print("=" * 68)
    if Xall_tr:
        Xtr = np.vstack(Xall_tr); ytr = np.concatenate(yall_tr)
        Xte = np.vstack(Xall_te); yte = np.concatenate(yall_te)
        prob, modelo = _modelo(Xtr, ytr, Xte)
        filas = evaluar(prob, yte)
        print(f"POOL (todos los pares) · {modelo} · {len(yte)} de prueba")
        for f in filas:
            marca = " <- cruza break-even" if f["acc"] >= BREAKEVEN and f["n"] else ""
            print(f"  confianza>= {f['margen']:.2f} : acierto {f['acc']:.1f}%  "
                  f"(cobertura {f['cobertura']:.0f}%, n={f['n']}){marca}")
        mejor = max(filas, key=lambda x: x["acc"] if x["n"] >= 50 else 0)
        print("-" * 68)
        if mejor["acc"] >= BREAKEVEN and mejor["n"] >= 50:
            print(f"HAY BORDE: al {mejor['acc']:.1f}% (confianza>={mejor['margen']:.2f}, "
                  f"cobertura {mejor['cobertura']:.0f}%) SUPERA el break-even "
                  f"{BREAKEVEN:.1f}%. Vale integrarlo como filtro.")
        else:
            print(f"NO hay borde: el mejor caso ({mejor['acc']:.1f}%) NO cruza el "
                  f"break-even {BREAKEVEN:.1f}%. El modelo aprende del pasado pero el "
                  f"futuro a este horizonte es ~50/50. Honesto: no integrar (seria "
                  f"vender una ventaja que no existe).")
    else:
        print("Sin muestra suficiente en ningun par. Deja correr el colector.")
    conn.close()


if __name__ == "__main__":
    main()
