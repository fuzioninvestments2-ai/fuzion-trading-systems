"""
scratchpad/estratificado.py — análisis estratificado (NO se commitea, es diagnóstico).
Pregunta: ¿el win-rate MEJORA en las señales más fuertes (9/9 alineados, prob alta)?
Si el sistema gana en algún lado, está en su subconjunto más selectivo.

En cada punto de decisión llama a calculate_quantum_probability (sin el gate),
registra (alineados, direccion, prob) y el resultado real a 60s. Luego agrupa.
"""
import glob
import os

import pandas as pd

from bot.cuantico import TIMEFRAMES_9, calculate_quantum_probability
from bot.backtest_historico import _resample_ohlc, _busca, MIN_VELAS

PAYOUT = 0.92
BREAKEVEN = 1.0 / (1.0 + PAYOUT) * 100

# Acumuladores: por nº alineados y por bucket de probabilidad.
por_alin = {}     # alineados -> [wins, resueltas]
por_prob = {}     # bucket    -> [wins, resueltas]


def _bucket_prob(p):
    if p >= 95: return "95-100"
    if p >= 90: return "90-95"
    if p >= 80: return "80-90"
    if p >= 70: return "70-80"
    return "<70"


def procesar(ruta, paso_seg=60, expiry_seg=60, max_dec=400):
    df5 = pd.read_csv(ruta).sort_values("timestamp").reset_index(drop=True)
    if len(df5) < 200:
        return
    frames_full = {tf: _resample_ohlc(df5, tf) for tf in TIMEFRAMES_9}
    ts = df5["timestamp"].astype(int).tolist()
    cierre = dict(zip(ts, df5["close"].astype(float)))

    def c_en(t):
        i = _busca(ts, t)
        return cierre[ts[i]] if i is not None else None

    t0, t1 = ts[0], ts[-1]
    t = t0 + 900 * MIN_VELAS * 1000
    dec = 0
    while t <= t1 - expiry_seg * 1000 and dec < max_dec:
        frames = {}
        for tf in TIMEFRAMES_9:
            ff = frames_full[tf]
            sub = ff[ff["timestamp"] + tf * 1000 <= t]
            if len(sub) >= MIN_VELAS:
                frames[tf] = sub
        dec += 1
        t_dec = t
        t += paso_seg * 1000
        if len(frames) < TIMEFRAMES_9.__len__():
            continue
        q = calculate_quantum_probability(frames)
        if not q["direccion"]:
            continue
        pe, ps = c_en(t_dec), c_en(t_dec + expiry_seg * 1000)
        if pe is None or ps is None or ps == pe:
            continue
        gano = (q["direccion"] == "CALL" and ps > pe) or (q["direccion"] == "PUT" and ps < pe)
        a = q["alineados"]
        por_alin.setdefault(a, [0, 0])
        por_alin[a][0] += int(gano); por_alin[a][1] += 1
        b = _bucket_prob(q["probabilidad"])
        por_prob.setdefault(b, [0, 0])
        por_prob[b][0] += int(gano); por_prob[b][1] += 1


rutas = sorted(glob.glob("datasets/*__tf5.csv.gz"))[:95]
for i, r in enumerate(rutas):
    try:
        procesar(r)
    except Exception as e:
        print(f"  ERR {os.path.basename(r)}: {e}")
    if (i + 1) % 20 == 0:
        print(f"... {i+1}/{len(rutas)} pares")

print(f"\nBreak-even payout 92%: {BREAKEVEN:.2f}%\n")
print("POR Nº DE TIEMPOS ALINEADOS (de 9):")
for a in sorted(por_alin):
    w, n = por_alin[a]
    wr = w / n * 100 if n else 0
    flag = "GANA" if wr > BREAKEVEN else "pierde"
    print(f"  {a}/9 alineados: n={n:5}  win-rate={wr:5.1f}%  {flag}")

print("\nPOR PROBABILIDAD (la que decide OPERAR):")
for b in ["95-100", "90-95", "80-90", "70-80", "<70"]:
    if b in por_prob:
        w, n = por_prob[b]
        wr = w / n * 100 if n else 0
        flag = "GANA" if wr > BREAKEVEN else "pierde"
        print(f"  prob {b:>7}: n={n:5}  win-rate={wr:5.1f}%  {flag}")
