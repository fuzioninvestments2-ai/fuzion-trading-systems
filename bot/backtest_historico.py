"""
bot/backtest_historico.py
=========================
BACKTEST HONESTO del sistema real sobre los datasets históricos de Pocket Option
(`datasets/*__tf5.csv.gz`). NO predice el futuro: aplica el MISMO motor que corre
en vivo (`validate_signal_90` sobre los 9 timeframes) a datos ya ocurridos y mide
el win-rate REAL que habría tenido cada señal.

Por qué desde tf5: las velas de 5s son la base más fina; agregándolas se reconstruyen
los 9 tiempos (5,10,15,60,120,180,300,600,900s) perfectamente alineados en el tiempo,
sin mezclar archivos de distintas descargas.

Metodología (sin red, reproducible):
  1. Cargar tf5 de un par. Resamplear OHLC a los 9 tamaños de vela.
  2. Caminar hacia adelante cada `paso_seg`. En cada punto t construir los 9 frames
     con SOLO la historia hasta t (nada de mirar el futuro).
  3. Correr `validate_signal_90`. Si dice OPERAR (CALL/PUT), registrar la entrada.
  4. Resultado: a los `expiry_seg` segundos (entrada de 1m del trader), ¿el precio
     se movió en la dirección predicha? WIN si sí, LOSS si no.
  5. Win-rate = wins / (wins+losses). Break-even con payout 92% = 52.08%.

El objetivo es que DECIDA EL DATO, no la opinión: el número que salga es el número.
"""
import glob
import math
import os

import pandas as pd

from bot.cuantico import TIMEFRAMES_9, validate_signal_90

# Payout típico del trader (92%): win-rate de equilibrio = 1/(1+0.92) = 52.08%.
PAYOUT = 0.92
BREAKEVEN = 1.0 / (1.0 + PAYOUT) * 100     # 52.08%
MIN_VELAS = 20                             # cada frame necesita >=20 velas (indicadores)


def _resample_ohlc(df5, tf_seg):
    """Agrega velas de 5s a velas de `tf_seg` segundos. Alinea por bloque temporal."""
    if tf_seg == 5:
        return df5.reset_index(drop=True)
    bloque = (df5["timestamp"] // (tf_seg * 1000)) * (tf_seg * 1000)
    agg = df5.groupby(bloque).agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
    )
    agg.index.name = "timestamp"
    return agg.reset_index()


def backtest_par(ruta_tf5, paso_seg=60, expiry_seg=60, max_decisiones=400):
    """
    Backtest de un par. Devuelve dict con señales, wins, losses, win_rate.
    `paso_seg`: cada cuánto se evalúa (60s = como el escaneo real).
    `expiry_seg`: horizonte de la opción binaria (60s = entrada de 1m del trader).
    """
    df5 = pd.read_csv(ruta_tf5)
    if len(df5) < 200:
        return None
    df5 = df5.sort_values("timestamp").reset_index(drop=True)

    # Resamplear una vez a los 9 tiempos (más medio de precio para el outcome real).
    frames_full = {tf: _resample_ohlc(df5, tf) for tf in TIMEFRAMES_9}
    t0, t1 = int(df5["timestamp"].iloc[0]), int(df5["timestamp"].iloc[-1])

    # Serie de cierres 5s indexada por timestamp para medir el resultado exacto.
    cierre_por_t = dict(zip(df5["timestamp"].astype(int), df5["close"].astype(float)))
    ts_ordenados = df5["timestamp"].astype(int).tolist()

    def cierre_en(t):
        """Cierre de la vela 5s en o justo después de t (precio de expiración)."""
        idx = _busca(ts_ordenados, t)
        if idx is None:
            return None
        return cierre_por_t[ts_ordenados[idx]]

    señales = 0
    wins = losses = empates = 0
    # Empezar con historia suficiente para el tiempo más largo (900s * 20 velas).
    inicio = t0 + 900 * MIN_VELAS * 1000
    decisiones = 0
    t = inicio
    while t <= t1 - expiry_seg * 1000 and decisiones < max_decisiones:
        # Construir los 9 frames con SOLO velas YA CERRADAS a las t. Clave anti
        # look-ahead: una vela de tf seg cuyo bloque empieza en `timestamp` NO está
        # cerrada hasta timestamp+tf. Si incluyéramos la vela en formación, su `close`
        # (y su momentum) contendría precios del FUTURO → win-rate falsamente inflado.
        frames = {}
        for tf in TIMEFRAMES_9:
            ff = frames_full[tf]
            sub = ff[ff["timestamp"] + tf * 1000 <= t]
            if len(sub) >= MIN_VELAS:
                frames[tf] = sub
        decisiones += 1
        res = validate_signal_90(frames, payout=PAYOUT * 100)
        if not res.get("operar"):
            t += paso_seg * 1000
            continue

        # Señal OPERAR: medir el resultado real a expiry_seg.
        señales += 1
        p_entrada = cierre_en(t)
        p_salida = cierre_en(t + expiry_seg * 1000)
        if p_entrada is None or p_salida is None:
            señales -= 1
            t += paso_seg * 1000
            continue
        subio = p_salida > p_entrada
        bajo = p_salida < p_entrada
        if p_salida == p_entrada:
            empates += 1
        elif (res["direccion"] == "CALL" and subio) or (res["direccion"] == "PUT" and bajo):
            wins += 1
        else:
            losses += 1
        t += paso_seg * 1000

    resueltas = wins + losses
    wr = (wins / resueltas * 100) if resueltas else None
    return {
        "par": os.path.basename(ruta_tf5).split("__")[0],
        "decisiones": decisiones, "señales": señales,
        "wins": wins, "losses": losses, "empates": empates,
        "win_rate": wr,
    }


def _busca(ordenados, t):
    """Índice del primer timestamp >= t (búsqueda binaria). None si no hay."""
    lo, hi = 0, len(ordenados)
    while lo < hi:
        mid = (lo + hi) // 2
        if ordenados[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(ordenados) else None


def correr(patron="datasets/*__tf5.csv.gz", n_pares=30, expiry_seg=60):
    """Corre el backtest sobre n_pares y agrega el win-rate global."""
    rutas = sorted(glob.glob(patron))[:n_pares]
    filas = []
    tot_w = tot_l = tot_s = tot_e = 0
    for r in rutas:
        try:
            res = backtest_par(r, expiry_seg=expiry_seg)
        except Exception as e:                     # robustez: un par malo no corta todo
            print(f"  {os.path.basename(r):28} ERROR {e}")
            continue
        if not res:
            continue
        filas.append(res)
        tot_w += res["wins"]; tot_l += res["losses"]
        tot_s += res["señales"]; tot_e += res["empates"]
        wr = f"{res['win_rate']:.1f}%" if res["win_rate"] is not None else "s/señales"
        print(f"  {res['par']:16} señales={res['señales']:3}  "
              f"W={res['wins']:3} L={res['losses']:3}  win-rate={wr}")

    resueltas = tot_w + tot_l
    wr_global = (tot_w / resueltas * 100) if resueltas else 0.0
    print("\n" + "=" * 60)
    print(f"GLOBAL: {len(filas)} pares · {tot_s} señales OPERAR · "
          f"{resueltas} resueltas ({tot_e} empates)")
    print(f"WIN-RATE REAL: {wr_global:.2f}%")
    print(f"Break-even payout 92%: {BREAKEVEN:.2f}%  "
          f"→ {'GANA' if wr_global > BREAKEVEN else 'PIERDE'} a largo plazo")
    # Margen estadístico: ±1.96*sqrt(p(1-p)/n) al 95%.
    if resueltas:
        p = wr_global / 100
        margen = 1.96 * math.sqrt(p * (1 - p) / resueltas) * 100
        print(f"Margen 95%: ±{margen:.2f}%  (rango {wr_global-margen:.1f}%–{wr_global+margen:.1f}%)")
    print("=" * 60)
    return wr_global, tot_s, resueltas


if __name__ == "__main__":
    correr()
