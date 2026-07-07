"""
scratchpad/buscar_borde.py — búsqueda EXHAUSTIVA y honesta de un borde ganador en OTC.
No argumenta: prueba. La única evidencia válida de un borde es que PERSISTA fuera de
muestra (out-of-sample): se mide en la 1ª mitad del historial (in-sample, IS) y se
verifica en la 2ª mitad (out-of-sample, OOS). Un borde real gana en AMBAS.

Prueba varias hipótesis distintas (no solo el sistema actual), por si alguna esconde
señal que los indicadores combinados diluyen:
  H1  sistema cuántico (validate_signal_90) — CALL/PUT del motor
  H2  momentum puro     — seguir la última vela de 1m (continuación)
  H3  reversión         — contra la última vela de 1m (mean-reversion)
  H4  reversión extrema — tras 3 velas 1m iguales, apostar al giro
Cada una, además, se corta por HORA UTC y por PAR, buscando un nicho que persista.

Umbral de borde: win-rate > 54% (margen sobre el break-even 52.08%) en IS y en OOS,
con n>=100 en cada mitad. Con menos, es ruido de muestreo.
"""
import glob
import math
import os

import pandas as pd

from bot.cuantico import TIMEFRAMES_9, calculate_quantum_probability
from bot.backtest_historico import _resample_ohlc, _busca, MIN_VELAS

PAYOUT = 0.92
BREAKEVEN = 1.0 / (1.0 + PAYOUT) * 100
BORDE_MIN = 54.0           # exigimos margen claro sobre break-even
N_MIN = 100               # mínimo por mitad para no medir ruido

# Acumuladores: clave -> {"is":[w,n], "oos":[w,n]}
acc = {}


def _reg(clave, mitad, gano):
    d = acc.setdefault(clave, {"is": [0, 0], "oos": [0, 0]})
    d[mitad][0] += int(gano)
    d[mitad][1] += 1


def _hora_utc(ts_ms):
    # Hora UTC sin depender de datetime (ms desde epoch): (ts/1000/3600) mod 24.
    return int((ts_ms // 1000 // 3600) % 24)


def procesar(ruta, mitad, paso_seg=60, expiry_seg=60, max_dec=400):
    # `mitad` ("is"/"oos") lo fija el LLAMADOR según el grupo de pares: los datasets
    # (~7h) son demasiado cortos para partir en el tiempo tras el warmup de 15m (5h),
    # así que el out-of-sample se hace por PARES: ¿el borde generaliza a otros pares?
    par = os.path.basename(ruta).split("__")[0]
    df5 = pd.read_csv(ruta).sort_values("timestamp").reset_index(drop=True)
    if len(df5) < 300:
        return
    frames_full = {tf: _resample_ohlc(df5, tf) for tf in TIMEFRAMES_9}
    m1 = frames_full[60]
    ts = df5["timestamp"].astype(int).tolist()
    cierre = dict(zip(ts, df5["close"].astype(float)))
    t0, t1 = ts[0], ts[-1]

    def c_en(t):
        i = _busca(ts, t)
        return cierre[ts[i]] if i is not None else None

    t = t0 + 900 * MIN_VELAS * 1000
    dec = 0
    while t <= t1 - expiry_seg * 1000 and dec < max_dec:
        t_dec = t
        t += paso_seg * 1000
        dec += 1
        # velas 1m cerradas hasta t (para H2/H3/H4).
        m1c = m1[m1["timestamp"] + 60 * 1000 <= t_dec]
        if len(m1c) < 5:
            continue
        pe, ps = c_en(t_dec), c_en(t_dec + expiry_seg * 1000)
        if pe is None or ps is None or ps == pe:
            continue
        subio = ps > pe
        hora = _hora_utc(t_dec)

        # ---- H1: sistema cuántico completo ----
        frames = {tf: frames_full[tf][frames_full[tf]["timestamp"] + tf * 1000 <= t_dec]
                  for tf in TIMEFRAMES_9}
        frames = {tf: f for tf, f in frames.items() if len(f) >= MIN_VELAS}
        if len(frames) == TIMEFRAMES_9.__len__():
            q = calculate_quantum_probability(frames)
            if q["direccion"]:
                gano = (q["direccion"] == "CALL") == subio
                _reg("H1-sistema", mitad, gano)
                _reg(f"H1-hora-{hora:02d}", mitad, gano)
                _reg(f"H1-par-{par}", mitad, gano)

        # Última(s) vela(s) 1m para H2/H3/H4.
        o1 = float(m1c["open"].iloc[-1]); c1 = float(m1c["close"].iloc[-1])
        vela_sube = c1 > o1
        # ---- H2: momentum (seguir la vela) ----
        _reg("H2-momentum", mitad, vela_sube == subio)
        # ---- H3: reversión (contra la vela) ----
        _reg("H3-reversion", mitad, (not vela_sube) == subio)
        # ---- H4: reversión extrema tras 3 iguales ----
        if len(m1c) >= 3:
            u3 = [float(m1c["close"].iloc[i]) > float(m1c["open"].iloc[i]) for i in (-1, -2, -3)]
            if all(u3):        # 3 subidas → apostar bajada
                _reg("H4-rev-extrema", mitad, (not subio))
            elif not any(u3):  # 3 bajadas → apostar subida
                _reg("H4-rev-extrema", mitad, subio)


def wr(par):
    w, n = par
    return (w / n * 100) if n else None


rutas = sorted(glob.glob("datasets/*__tf5.csv.gz"))[:95]
corte = len(rutas) // 2                       # primera mitad de pares = IS; resto = OOS
for i, r in enumerate(rutas):
    mitad = "is" if i < corte else "oos"
    try:
        procesar(r, mitad)
    except Exception as e:
        print(f"  ERR {os.path.basename(r)}: {e}")
    if (i + 1) % 25 == 0:
        print(f"... {i+1}/{len(rutas)}")

print(f"\nBreak-even 92%: {BREAKEVEN:.2f}%   ·   borde exigido: >{BORDE_MIN}% en IS Y OOS (n>={N_MIN})\n")

bordes = []
for clave, d in acc.items():
    wi, wo = wr(d["is"]), wr(d["oos"])
    ni, no = d["is"][1], d["oos"][1]
    if wi is None or wo is None or ni < N_MIN or no < N_MIN:
        continue
    persiste = wi > BORDE_MIN and wo > BORDE_MIN
    if persiste:
        bordes.append((clave, wi, wo, ni, no))

# Reporte de las hipótesis principales (siempre, aunque no sean borde).
print("HIPÓTESIS PRINCIPALES (IS = 1ª mitad, OOS = 2ª mitad):")
for clave in ["H1-sistema", "H2-momentum", "H3-reversion", "H4-rev-extrema"]:
    if clave in acc:
        d = acc[clave]
        wi, wo = wr(d["is"]), wr(d["oos"])
        si = f"{wi:5.1f}%" if wi is not None else "  s/n "
        so = f"{wo:5.1f}%" if wo is not None else "  s/n "
        print(f"  {clave:16} IS={si} (n={d['is'][1]:5})  "
              f"OOS={so} (n={d['oos'][1]:5})")

print(f"\nNICHOS QUE PERSISTEN >{BORDE_MIN}% EN AMBAS MITADES:")
if not bordes:
    print("  NINGUNO. No hay borde que sobreviva fuera de muestra.")
else:
    for clave, wi, wo, ni, no in sorted(bordes, key=lambda x: -(x[1] + x[2])):
        print(f"  *** {clave:20} IS={wi:.1f}% (n={ni})  OOS={wo:.1f}% (n={no})  ← BORDE REAL")
