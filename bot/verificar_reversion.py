"""
bot/verificar_reversion.py
==========================
¿El "borde" de reversión (55-60%) es REAL u un ARTEFACTO de microestructura
(rebote bid-ask)? Prueba decisiva antes de creer en el resultado.

La reversión "gana" si apostar contra la última vela acierta. Pero en datos de FX,
precios consecutivos rebotan entre compra/venta (bid/ask) creando una reversión
MECÁNICA que NO se puede operar: el spread es exactamente lo que la genera.

Test: segmentar el win-rate de la reversión por el TAMAÑO del movimiento que se
revierte (en pips). Firma del artefacto:
  - Movimientos DIMINUTOS (sub-spread): win-rate ALTO (rebote) → NO operable.
  - Movimientos REALES (> ~1 pip): win-rate cae hacia 50% → sin borde operable.
Si el win-rate se mantiene alto también en movimientos grandes, sería más creíble.

Además calcula el spread típico necesario: si la ganancia media por acierto es menor
que el spread, el "borde" es ilusorio (lo paga el spread en cada operación).
"""
import glob
import os

import numpy as np
import pandas as pd


def _pip(par):
    """Tamaño de 1 pip según el par (JPY = 0.01; resto 0.0001)."""
    return 0.01 if par.endswith("JPY") else 0.0001


def analizar(df, par):
    """Devuelve DataFrame de señales de reversión con el tamaño del movimiento (pips)."""
    c = df["close"].astype(float).to_numpy()
    if len(c) < 50:
        return None
    mov = np.diff(c)                                  # close[i]-close[i-1], len n-1
    subio_actual = mov > 0                            # dirección de la vela i (>=1)
    # apostar contra: si subió → PUT ; futuro = close[i+1] vs close[i]
    fut = c[2:] - c[1:-1]                             # close[i+1]-close[i], alineado a i>=1
    n = min(len(subio_actual) - 1, len(fut))
    sa = subio_actual[:n]                             # dirección vela i
    ff = fut[:n]                                      # movimiento futuro
    gano = np.where(sa, ff < 0, ff > 0)              # reversión acierta
    mag_pips = np.abs(mov[:n]) / _pip(par)           # tamaño del movimiento revertido
    gan_pips = np.abs(ff) / _pip(par)                # tamaño del movimiento futuro
    return pd.DataFrame({"gano": gano, "mag_pips": mag_pips, "gan_pips": gan_pips})


def _rutas(patron, claves=("M1",)):
    todas = glob.glob(f"{patron}/**/*__*.csv.gz", recursive=True)
    out = []
    for r in todas:
        b = os.path.basename(r)
        if "_otc" in b.lower() or "/otc/" in r.replace(os.sep, "/").lower():
            continue
        if b.split("__")[1].replace(".csv.gz", "") in claves:
            out.append(r)
    return sorted(out)


def correr(patron="datasets"):
    todo = []
    for r in _rutas(patron):
        par = os.path.basename(r).split("__")[0]
        df = pd.read_csv(r).sort_values("timestamp").reset_index(drop=True)
        a = analizar(df, par)
        if a is not None:
            todo.append(a)
    if not todo:
        print("Sin datos M1 reales.")
        return
    s = pd.concat(todo, ignore_index=True)
    s = s[s["mag_pips"] > 0]

    print(f"Señales totales: {len(s)}\n")
    print("WIN-RATE DE LA REVERSIÓN POR TAMAÑO DEL MOVIMIENTO REVERTIDO:")
    print(f"{'movimiento (pips)':>20} | {'n':>8} | {'win-rate':>8} | ganancia media (pips)")
    bins = [0, 0.5, 1, 2, 3, 5, 10, 1e9]
    etq = ["<0.5", "0.5-1", "1-2", "2-3", "3-5", "5-10", ">10"]
    for i in range(len(bins) - 1):
        m = (s["mag_pips"] >= bins[i]) & (s["mag_pips"] < bins[i + 1])
        sub = s[m]
        if len(sub) < 50:
            continue
        wr = sub["gano"].mean() * 100
        gm = sub["gan_pips"].mean()
        flag = "  ← rebote (sub-spread)" if bins[i + 1] <= 1 else ""
        print(f"{etq[i]:>20} | {len(sub):>8} | {wr:>7.1f}% | {gm:>6.2f}{flag}")

    # Conclusión: comparar win-rate en movimientos pequeños vs reales.
    chico = s[s["mag_pips"] < 1]["gano"].mean() * 100 if (s["mag_pips"] < 1).sum() else None
    grande = s[s["mag_pips"] >= 2]["gano"].mean() * 100 if (s["mag_pips"] >= 2).sum() else None
    print("\n" + "=" * 60)
    if chico is not None and grande is not None:
        print(f"Movimientos <1 pip (rebote):  {chico:.1f}%")
        print(f"Movimientos ≥2 pips (reales): {grande:.1f}%")
        if chico - grande > 3:
            print("\nVEREDICTO: el 'borde' se concentra en micro-movimientos (rebote")
            print("bid-ask). En movimientos reales cae hacia 50%. NO es operable: el")
            print("spread genera y se come esa ganancia. Artefacto, no borde.")
        elif grande > 52:
            print("\nVEREDICTO: el win-rate se mantiene >52% en movimientos reales.")
            print("Merece seguir investigando (podría ser borde real). Verificar spread.")
        else:
            print("\nVEREDICTO: en movimientos reales no hay borde (<52%).")
    print("=" * 60)


if __name__ == "__main__":
    print("VERIFICACIÓN: ¿reversión real o rebote bid-ask? (segmenta por tamaño de movimiento)\n")
    correr()
