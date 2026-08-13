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


# --------------------------------------------------------------- walk-forward
FOLDS = 5                              # ventanas de validacion (no un solo corte)
MARGENES = (0.0, 0.05, 0.10, 0.15)


def walkforward_par(o, h, l, c, ts, horizonte, payout_frac, folds=FOLDS):
    """
    Validacion WALK-FORWARD: en vez de un corte 70/30, hace `folds` ventanas. En
    cada una entrena con TODO lo anterior y predice el bloque siguiente (que nunca
    vio). Devuelve una lista de (prob, y, payout_frac, fold) juntando todas las
    predicciones fuera de muestra. Esto es mas robusto: un solo corte puede caer en
    un tramo suertudo; 5 ventanas muestran si el borde se sostiene o fue una.
    """
    X, y = construir_features(o, h, l, c, ts, horizonte)
    n = len(y)
    if n < MIN_VELAS // 2:
        return []
    bordes = np.linspace(0, n, folds + 2, dtype=int)   # folds+1 tramos
    out = []
    for f in range(folds):
        tr_end = bordes[f + 1]; te_end = bordes[f + 2]
        Xtr, ytr = X[:tr_end], y[:tr_end]
        Xte, yte = X[tr_end:te_end], y[tr_end:te_end]
        if len(np.unique(ytr)) < 2 or len(yte) < 20:
            continue
        prob, _ = _modelo(Xtr, ytr, Xte)
        for p, yy in zip(prob, yte):
            out.append((float(p), int(yy), float(payout_frac), f))
    return out


def evaluar_roi(reg):
    """
    Sobre las predicciones fuera de muestra (reg = lista de (prob,y,payout,fold)),
    calcula por umbral de confianza:
      - acierto,
      - ROI POR OPERACION (gana payout si acierta, pierde 1 si falla): la metrica
        HONESTA de si da plata con TU pago real, no un acierto contra un break-even
        fijo,
      - estabilidad: en cuantas de las `folds` ventanas el ROI fue positivo.
    Un borde de verdad tiene ROI>0 y es positivo en la MAYORIA de las ventanas
    (no cargado por una sola).
    """
    if not reg:
        return []
    prob = np.array([r[0] for r in reg]); y = np.array([r[1] for r in reg])
    pay = np.array([r[2] for r in reg]); fold = np.array([r[3] for r in reg])
    pred = (prob > 0.5).astype(int); win = (pred == y)
    conf = np.abs(prob - 0.5)
    filas = []
    for m in MARGENES:
        sel = conf >= m
        n = int(sel.sum())
        if n == 0:
            continue
        roi = float(np.where(win[sel], pay[sel], -1.0).mean())      # ROI/operacion
        acc = 100.0 * float(win[sel].mean())
        pos = tot = 0
        for ff in np.unique(fold):
            fs = sel & (fold == ff)
            if fs.sum() >= 20:
                tot += 1
                if np.where(win[fs], pay[fs], -1.0).mean() > 0:
                    pos += 1
        filas.append({"margen": m, "n": n, "acc": acc, "roi": roi,
                      "cob": 100.0 * n / len(y), "folds_pos": pos, "folds": tot})
    return filas


def _serie(conn, pair):
    rows = conn.execute(
        """SELECT open, high, low, close, ts FROM candles_real
           WHERE pair=? AND tf=? ORDER BY ts ASC""", (pair, BASE_TF)).fetchall()
    if len(rows) < MIN_VELAS:
        return None
    return ([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows],
            [r[3] for r in rows], [r[4] for r in rows])


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
    # Payout REAL por par (el break-even depende de esto): para un par que paga 70%
    # hay que acertar >58.8%, no 55.6%. Se usa el pago que guardo el colector.
    from collector.candle_store import CandleStore
    store = CandleStore(DB)

    print("ML DIRECCION v2 — validacion DURA (walk-forward + ROI con tu pago real)")
    print(f"{FOLDS} ventanas (entrena pasado, mide el bloque siguiente) · horizonte "
          f"{horizonte} vela(s)")
    print("Metrica: ROI por operacion (gana pago si acierta, pierde 1 si falla). "
          "ROI>0 = da plata.")
    print("=" * 72)

    reg_pool = []
    print(f"{'PAR':10} {'pago':>5} {'be%':>6} {'acc(c>=.10)':>12} {'ROI/op':>8}")
    for pair in pares:
        s = _serie(conn, pair)
        pago = store.get_payout(pair)
        if s is None or pago is None:
            print(f"{pair:10} {'-':>5}  (sin muestra o sin pago)")
            continue
        pf = float(pago) / 100.0
        be = 100.0 / (1.0 + pf)                     # break-even real de ESE pago
        reg = walkforward_par(*s, horizonte, pf)
        reg_pool.extend(reg)
        ev = evaluar_roi(reg)
        c10 = next((x for x in ev if x["margen"] == 0.10), None)
        if c10:
            print(f"{pair:10} {int(pago):>4}% {be:>5.1f}% {c10['acc']:>11.1f}% "
                  f"{c10['roi']:>+7.3f}")

    print("=" * 72)
    ev = evaluar_roi(reg_pool)
    if not ev:
        print("Sin muestra suficiente. Deja correr el colector mas tiempo.")
        conn.close(); return

    modelo = "GradientBoosting(sklearn)"
    try:
        import sklearn  # noqa: F401
    except ImportError:
        modelo = "LogisticaNumpy (instala scikit-learn para el modelo fuerte)"
    print(f"POOL (todos los pares) · {modelo} · {len(reg_pool)} operaciones")
    for x in ev:
        estab = f"{x['folds_pos']}/{x['folds']} ventanas+" if x["folds"] else "s/ventanas"
        marca = "  <- da plata" if x["roi"] > 0 else ""
        print(f"  confianza>= {x['margen']:.2f} : acierto {x['acc']:.1f}%  "
              f"ROI {x['roi']:+.3f}/op  (n={x['n']}, {estab}){marca}")

    # VEREDICTO honesto: borde REAL = ROI>0 con muestra decente (n>=200) Y positivo
    # en la MAYORIA de las ventanas (>=ceil(folds*0.6)). Un ROI>0 cargado por una
    # sola ventana NO cuenta (es suerte de tramo, no un borde que se sostenga).
    print("-" * 72)
    candidatos = [x for x in ev if x["roi"] > 0 and x["n"] >= 200
                  and x["folds"] and x["folds_pos"] >= max(3, int(np.ceil(x["folds"] * 0.6)))]
    if candidatos:
        b = max(candidatos, key=lambda x: x["roi"])
        print(f"BORDE ROBUSTO: confianza>={b['margen']:.2f} da ROI {b['roi']:+.3f} por "
              f"operacion (acierto {b['acc']:.1f}%, n={b['n']}, positivo en "
              f"{b['folds_pos']}/{b['folds']} ventanas). Se SOSTIENE. Vale integrarlo "
              f"como filtro y confirmar en papel antes de arriesgar.")
    else:
        mejor = max(ev, key=lambda x: x["roi"])
        print(f"NO se sostiene: el mejor ROI ({mejor['roi']:+.3f}/op, "
              f"confianza>={mejor['margen']:.2f}) no cumple ROI>0 estable en la "
              f"mayoria de ventanas con muestra suficiente. El susurro de borde no "
              f"aguanta la validacion dura. Honesto: NO integrar todavia; junta mas "
              f"historial (dias) y volve a correr.")
    conn.close()


if __name__ == "__main__":
    main()
