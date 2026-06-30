"""
indicators/test_rsi.py
======================
Prueba de validación del módulo RSI (Regla 4).

Verifica:
  (A) Correctitud: vectorizado y streaming coinciden donde ambos tienen valor.
  (B) Caso conocido: precios solo subiendo -> RSI = 100.
  (C) Latencia: cada update() (un tick) por debajo de 15 ms.
"""

import time
import numpy as np
from rsi import rsi_vectorized, RSI


def test_correctitud():
    # Serie clásica usada en ejemplos de RSI de Wilder.
    precios = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
               45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
    period = 14

    rsi_vec = rsi_vectorized(precios, period)
    ind = RSI(period)
    rsi_stream = [ind.update(p) for p in precios]

    print("Vectorizado:", np.round(rsi_vec, 4))
    print("Streaming  :",
          [round(x, 4) if x is not None else None for x in rsi_stream])

    for i in range(len(precios)):
        a = rsi_vec[i]
        b = rsi_stream[i]
        if not np.isnan(a) and b is not None:
            assert abs(a - b) < 1e-9, f"❌ Discrepancia en i={i}: {a} vs {b}"
    print("✅ (A) Vectorizado y streaming coinciden.")
    print("Buffer circular:", ind.recent_prices())


def test_caso_conocido():
    period = 14
    solo_sube = list(range(1, 30))     # precios estrictamente crecientes
    rsi_fin = rsi_vectorized(solo_sube, period)[-1]
    assert rsi_fin == 100.0, "❌ Subida pura debería dar RSI=100"
    print("✅ (B) Subida pura -> RSI = 100.")


def test_latencia():
    period = 14
    ind = RSI(period)
    for p in range(100):               # calentamiento
        ind.update(float(p))
    n = 100_000
    t0 = time.perf_counter()
    for i in range(n):
        ind.update(float(i % 1000))
    t1 = time.perf_counter()
    ms = (t1 - t0) / n * 1000.0
    print(f"Latencia media por tick: {ms:.6f} ms")
    assert ms < 15.0, f"❌ Latencia {ms:.4f} ms supera 15 ms"
    print("✅ (C) Latencia OK (< 15 ms/tick).")


if __name__ == "__main__":
    test_correctitud()
    print("-" * 60)
    test_caso_conocido()
    print("-" * 60)
    test_latencia()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
