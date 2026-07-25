"""
bot/backtest_reversion_real.py
==============================
Hipótesis DISTINTA al motor de confluencia: REVERSIÓN TRAS PICO. Si una vela de 1m se
mueve mucho (>= umbral pips) en un solo paso, apostar a que el precio se DEVUELVE
(dirección contraria) al cabo de e minutos. Es lo contrario a seguir la tendencia.

Por qué puede tener algo donde la confluencia no: un salto brusco suele ser
sobre-reacción o barrido de liquidez que corrige; el motor de alineación, en cambio,
entra a favor del movimiento ya hecho.

Rigor (mismo examen que las otras versiones):
  - Split TEMPORAL por par: primer 60% del tiempo = IS (aprender), último 40% = OOS
    (medir). El borde debe persistir en datos nuevos.
  - MAX_PIPS: se descartan picos absurdos (posibles errores de dato) que inflan el
    win-rate de los buckets grandes.
  - Barrido de umbrales (pips) x expiries (minutos). Se elige el mejor umbral en IS y
    se reporta su OOS — sin elegir sobre el test.
  - P&L por operación con payout 92% (win=+0.92, loss=-1): mide si GANA dinero, no
    solo si acierta > 50%. Break-even = 52.08%.

Corre sobre datasets/real (M1). Sin red. Test: bot/test_backtest_reversion_real.py.
"""
import glob
import math
import os

import numpy as np
import pandas as pd

PAYOUT = 0.92
BREAKEVEN = 100.0 / (1.0 + PAYOUT)         # 52.08%
UMBRALES = (1, 2, 3, 4, 5, 6, 8, 10)       # pips del pico a exigir
EXPIRIES_MIN = (1, 2, 3, 5, 10)            # minutos hasta el vencimiento (velas M1)
MAX_PIPS = 20                              # pico mayor = probable error de dato -> fuera
FRAC_IS = 0.6                              # primer 60% del tiempo para aprender


def _pip(par):
    """Tamaño del pip: los pares con JPY cotizan a 2 decimales, el resto a 4."""
    return 0.01 if par.upper().endswith("JPY") else 0.0001


def _acumular_par(c, par, acc):
    """Acumula wins/losses de reversión por (umbral, expiry, mitad) para un par.
    c: array de cierres M1 (cronológico). acc: dict que se actualiza en sitio."""
    n = len(c)
    if n < 300:
        return
    pip = _pip(par)
    mov = (c[1:] - c[:-1]) / pip               # mov[j] = pips de la vela cuyo cierre es c[j+1]
    signo_mov = np.sign(mov)
    idx = np.arange(1, n)                       # i = índice del cierre-pico (entrada = c[i])
    split = max(1, int(n * FRAC_IS))
    for u in UMBRALES:
        base = (np.abs(mov) >= u) & (np.abs(mov) <= MAX_PIPS) & (signo_mov != 0)
        if not base.any():
            continue
        for e in EXPIRIES_MIN:
            valido = base & (idx + e <= n - 1)  # que exista la vela de salida
            if not valido.any():
                continue
            i = idx[valido]
            ret = c[i + e] - c[i]              # movimiento desde la entrada hasta el vencimiento
            sm = signo_mov[i - 1]             # signo del pico (mov[i-1] corresponde al pico en c[i])
            resuelto = ret != 0
            gana = (np.sign(ret) == -sm) & resuelto      # reversión: va en contra del pico
            es_is = i < split
            for half, sel in (("is", es_is), ("oos", ~es_is)):
                m = sel & resuelto
                k = (u, e, half)
                w, l = acc.get(k, (0, 0))
                acc[k] = (w + int((gana & m).sum()),
                          l + int((~gana & m).sum()))


def _stats(w, l):
    """win-rate %, margen 95%, P&L por operación (payout 92%) y n. None si no hay ops."""
    n = w + l
    if not n:
        return None
    p = w / n
    margen = 1.96 * math.sqrt(p * (1 - p) / n) * 100
    pnl = (p * PAYOUT - (1 - p)) * 100         # % por operación
    return p * 100, margen, pnl, n


def _rutas(destino):
    """M1 de cada par en datasets/real (excluye cualquier _otc por si acaso)."""
    out = []
    for r in sorted(glob.glob(f"{destino}/*__M1.csv.gz")):
        if "_otc" in os.path.basename(r).lower():
            continue
        out.append(r)
    return out


def correr(destino="datasets/real", pares=None):
    rutas = _rutas(destino)
    if pares:
        rutas = [r for r in rutas if os.path.basename(r).split("__")[0] in pares]
    if not rutas:
        print(f"Sin M1 en {destino}.")
        return {}
    acc = {}
    for r in rutas:
        par = os.path.basename(r).split("__")[0]
        try:
            df = pd.read_csv(r).sort_values("timestamp")
        except Exception as e:
            print(f"  {par:8} ERROR {e}")
            continue
        _acumular_par(df["close"].astype(float).to_numpy(), par, acc)

    print(f"REVERSIÓN TRAS PICO sobre {destino}/  ·  payout 92% · break-even "
          f"{BREAKEVEN:.2f}%  ·  IS=primer {int(FRAC_IS*100)}% / OOS=resto")
    print(f"(pico entre umbral y {MAX_PIPS} pips; picos mayores = posibles errores, fuera)")
    print("=" * 78)
    print(f"{'umbral':>6}{'exp':>5}{'winIS':>8}{'winOOS':>9}{'margen':>8}"
          f"{'P&L/op':>9}{'nOOS':>8}  veredicto")
    resumen = {}
    for u in UMBRALES:
        for e in EXPIRIES_MIN:
            sis = _stats(*acc.get((u, e, "is"), (0, 0)))
            soos = _stats(*acc.get((u, e, "oos"), (0, 0)))
            if not sis or not soos:
                continue
            wr_oos, margen, pnl, n = soos
            resumen[(u, e)] = soos
            gana = (wr_oos - margen > BREAKEVEN and sis[0] > BREAKEVEN and pnl > 0)
            marca = "GANA" if gana else ("PIERDE" if wr_oos + margen < BREAKEVEN else "INCIERTO")
            print(f"{u:>5}p{e:>4}m{sis[0]:>7.1f}%{wr_oos:>8.1f}%{'±'+format(margen,'.1f'):>8}"
                  f"{pnl:>+8.2f}%{n:>8}  {marca}")
    print("=" * 78)
    print("GANA solo si winOOS supera 52.08% CON margen, el IS ya ganaba, y el P&L por")
    print("operación es positivo. Si nada da GANA, la reversión tampoco tiene borde aquí.")
    return resumen


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Backtest reversión tras pico (real).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = todos)")
    ap.add_argument("--destino", default="datasets/real")
    a = ap.parse_args()
    correr(a.destino, a.pares or None)
