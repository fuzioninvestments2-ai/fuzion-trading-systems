"""
bot/backtest_reversion_spike.py
===============================
Backtest LIMPIO de la única señal prometedora: REVERSIÓN TRAS UN PICO. Si una vela
se mueve ≥ `umbral` pips en un solo paso, apostar a que la siguiente corrige
(dirección contraria). La verificación mostró que el win-rate crece con el tamaño
del pico — aquí lo medimos como estrategia OPERADA en secuencia, out-of-sample.

Rigor / trampas que se controlan:
  - MAX_PIPS: descarta picos absurdos (posibles errores de dato / bad ticks) que
    inflan el win-rate en los buckets grandes.
  - Split TEMPORAL (1ª mitad tiempo = IS, 2ª = OOS): el borde debe persistir.
  - P&L simulado con payout 92%: win = +0.92, loss = −1. Así se ve si GANA dinero,
    no solo si acierta > 50%.
  - Barre varios umbrales: más alto = más win-rate pero menos operaciones.

Esto NO prueba que funcione en Pocket Option (usa feed Yahoo/Dukascopy). Es el paso
previo al forward-test en demo. Sin red. Reproducible.
"""
import glob
import os

import numpy as np
import pandas as pd

PAYOUT = 0.92
BREAKEVEN = 100.0 / (1.0 + PAYOUT)      # 52.08%
UMBRALES = [1, 2, 3, 4, 5]              # pips del pico a exigir
MAX_PIPS = 20                          # picos mayores: probable error de dato → fuera


def _pip(par):
    return 0.01 if par.endswith("JPY") else 0.0001


def señales_par(df, par):
    """Movimiento de cada vela (pips, con signo) y el resultado de revertir a 1 vela."""
    c = df["close"].astype(float).to_numpy()
    if len(c) < 100:
        return None
    pip = _pip(par)
    mov = np.diff(c) / pip                       # mov[k] = (c[k+1]-c[k]) en pips
    fut = (c[2:] - c[1:-1]) / pip                # fut[k] = (c[k+2]-c[k+1]) en pips
    n = min(len(mov) - 1, len(fut))
    return pd.DataFrame({"mov": mov[:n], "fut": fut[:n]})


def _rutas(patron, claves=("M1",)):
    out = []
    for r in glob.glob(f"{patron}/**/*__*.csv.gz", recursive=True):
        b = os.path.basename(r)
        if "_otc" in b.lower() or "/otc/" in r.replace(os.sep, "/").lower():
            continue
        if b.split("__")[1].replace(".csv.gz", "") in claves:
            out.append(r)
    return sorted(out)


def correr(patron="datasets", claves=("M1",)):
    partes = []
    for r in _rutas(patron, claves):
        par = os.path.basename(r).split("__")[0]
        df = pd.read_csv(r).sort_values("timestamp").reset_index(drop=True)
        s = señales_par(df, par)
        if s is None:
            continue
        s["mitad"] = ["is" if i < len(s) // 2 else "oos" for i in range(len(s))]
        partes.append(s)
    if not partes:
        print("Sin datos M1 reales.")
        return
    s = pd.concat(partes, ignore_index=True)

    print(f"Señales base: {len(s)}   ·   break-even 92%: {BREAKEVEN:.2f}%")
    print(f"(pico entre umbral y {MAX_PIPS} pips; se descartan picos mayores = posibles errores)\n")
    print(f"{'umbral':>6} | {'operaciones':>11} | {'winIS':>6} | {'winOOS':>7} | "
          f"{'P&L/op OOS':>10} | {'veredicto':>10}")
    for u in UMBRALES:
        # Señal: |mov| en [u, MAX_PIPS]. Reversión acierta si fut tiene signo contrario a mov.
        val = s[(s["mov"].abs() >= u) & (s["mov"].abs() <= MAX_PIPS) & (s["fut"] != 0)]
        if len(val) < 100:
            continue
        gano = np.sign(val["fut"]) != np.sign(val["mov"])       # reversión
        wis = gano[val["mitad"] == "is"].mean() * 100
        woos = gano[val["mitad"] == "oos"].mean() * 100
        n_oos = int((val["mitad"] == "oos").sum())
        # P&L por operación en OOS con payout 92%.
        g_oos = gano[val["mitad"] == "oos"]
        pnl = (g_oos.mean() * PAYOUT - (1 - g_oos.mean())) * 100 if len(g_oos) else 0
        ok = "GANA" if (woos > BREAKEVEN and wis > BREAKEVEN) else "pierde"
        print(f"{u:>5}p | {len(val):>11} | {wis:>5.1f}% | {woos:>6.1f}% | "
              f"{pnl:>+9.2f}% | {ok:>10}  (n_oos={n_oos})")

    print("\n" + "=" * 66)
    print("Si 'winOOS' supera 52.08% con P&L positivo y suficientes operaciones, la")
    print("señal es un candidato REAL. Falta el filtro final: forward-test en DEMO")
    print("sobre el feed de Pocket Option (el backtest usa feed externo).")
    print("=" * 66)


if __name__ == "__main__":
    print("BACKTEST · reversión tras pico (operada en secuencia, out-of-sample)\n")
    correr()
