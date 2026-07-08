"""
bot/verificar_skip.py
=====================
PRUEBA DECISIVA: ¿la "reversión tras pico" (61-69% OOS) es real o es el artefacto de
PRECIO COMPARTIDO (ruido bid-ask corrigiéndose)?

El backtest anterior mide:
  pico   = close[i+1] - close[i]
  futuro = close[i+2] - close[i+1]     ← comparte close[i+1] con el pico
Si close[i+1] tiene ruido ε, aparece con signo + en el pico y − en el futuro →
covarianza negativa MECÁNICA (falsa reversión) que crece con |ε|. NO operable: para
cuando observas el pico, el precio ya se corrigió; entrarías al precio ya revertido.

Test: comparar dos formas de medir la reversión, por tamaño de pico:
  INMEDIATA  = signo(close[i+2]-close[i+1]) contra el pico   (comparte close[i+1])
  SALTADA    = signo(close[i+3]-close[i+2]) contra el pico   (entrada FRESca, sin
               compartir precio con el pico)
Si INMEDIATA da 65% pero SALTADA cae a ~50%, el "borde" era ruido compartido, no
mercado. Si SALTADA se mantiene >52%, habría algo real que perseguir.

Sin red. Reproducible.
"""
import glob
import os

import numpy as np
import pandas as pd


def _pip(par):
    return 0.01 if par.endswith("JPY") else 0.0001


def _rutas(patron, claves=("M1",)):
    out = []
    for r in glob.glob(f"{patron}/**/*__*.csv.gz", recursive=True):
        b = os.path.basename(r)
        if "_otc" in b.lower() or "/otc/" in r.replace(os.sep, "/").lower():
            continue
        if b.split("__")[1].replace(".csv.gz", "") in claves:
            out.append(r)
    return sorted(out)


def señales(df, par):
    c = df["close"].astype(float).to_numpy()
    if len(c) < 100:
        return None
    pip = _pip(par)
    n = len(c) - 3
    if n <= 10:
        return None
    pico = (c[1:n + 1] - c[0:n]) / pip                    # close[i+1]-close[i]
    fut_inm = (c[2:n + 2] - c[1:n + 1]) / pip             # close[i+2]-close[i+1] (comparte)
    fut_skip = (c[3:n + 3] - c[2:n + 2]) / pip            # close[i+3]-close[i+2] (fresco)
    return pd.DataFrame({"pico": pico, "fut_inm": fut_inm, "fut_skip": fut_skip})


def correr(patron="datasets", claves=("M1",)):
    partes = []
    for r in _rutas(patron, claves):
        par = os.path.basename(r).split("__")[0]
        s = señales(pd.read_csv(r).sort_values("timestamp").reset_index(drop=True), par)
        if s is not None:
            partes.append(s)
    if not partes:
        print("Sin datos M1 reales.")
        return
    s = pd.concat(partes, ignore_index=True)
    s = s[(s["fut_inm"] != 0) & (s["fut_skip"] != 0)]

    print(f"Señales: {len(s)}\n")
    print("REVERSIÓN, INMEDIATA (comparte precio) vs SALTADA (entrada fresca):")
    print(f"{'pico (pips)':>12} | {'n':>7} | {'INMEDIATA':>9} | {'SALTADA':>8}")
    for lo, hi, etq in [(1, 2, "1-2"), (2, 3, "2-3"), (3, 5, "3-5"), (5, 20, "5-20")]:
        m = (s["pico"].abs() >= lo) & (s["pico"].abs() < hi)
        sub = s[m]
        if len(sub) < 50:
            continue
        inm = (np.sign(sub["fut_inm"]) != np.sign(sub["pico"])).mean() * 100
        skip = (np.sign(sub["fut_skip"]) != np.sign(sub["pico"])).mean() * 100
        print(f"{etq:>12} | {len(sub):>7} | {inm:>8.1f}% | {skip:>7.1f}%")

    # Veredicto global (picos ≥2 pips).
    big = s[s["pico"].abs() >= 2]
    inm = (np.sign(big["fut_inm"]) != np.sign(big["pico"])).mean() * 100
    skip = (np.sign(big["fut_skip"]) != np.sign(big["pico"])).mean() * 100
    print("\n" + "=" * 60)
    print(f"Picos ≥2 pips:  INMEDIATA {inm:.1f}%   ·   SALTADA {skip:.1f}%")
    if inm - skip > 5 and skip < 52:
        print("\nVEREDICTO: la INMEDIATA gana solo por compartir el precio del pico")
        print("(ruido corrigiéndose). SALTADA cae a ~50% = NO hay reversión operable.")
        print("El 61-69% era un ESPEJISMO de microestructura. No se puede operar.")
    elif skip > 52:
        print("\nVEREDICTO: la SALTADA se mantiene >52% con entrada fresca. Habría una")
        print("reversión REAL a un paso. Merece forward-test en demo.")
    else:
        print("\nVEREDICTO: sin borde claro con entrada fresca.")
    print("=" * 60)


if __name__ == "__main__":
    print("PRUEBA DECISIVA: reversión real vs artefacto de precio compartido\n")
    correr()
