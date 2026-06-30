"""
indicators/test_stochastic.py
=============================
Prueba de validación del módulo Estocástico (Regla 4).

Verifica:
  (A) Correctitud: vectorizado y streaming coinciden donde ambos tienen valor.
  (B) Casos conocidos: precio en el máximo del rango -> %K_raw = 100;
      precio en el mínimo -> %K_raw = 0.
  (C) Latencia: cada update() (un tick) por debajo de 15 ms.
"""

import time
import numpy as np
from stochastic import stoch_vectorized, Stochastic


def test_correctitud():
    # Serie de precios sintética (similar a un feed OTC nervioso).
    precios = [10, 11, 12, 11, 13, 12, 14, 13, 15, 14,
               16, 15, 17, 16, 18, 17, 19, 18, 20, 19]
    k_period, smooth_k, d_period = 14, 3, 3

    k_vec, d_vec = stoch_vectorized(precios, k_period, smooth_k, d_period)

    ind = Stochastic(k_period, smooth_k, d_period)
    k_stream, d_stream = [], []
    for p in precios:
        k, d = ind.update(p)
        k_stream.append(k)
        d_stream.append(d)

    print("%K vectorizado:", np.round(k_vec, 4))
    print("%K streaming  :",
          [round(x, 4) if x is not None else None for x in k_stream])
    print("%D vectorizado:", np.round(d_vec, 4))
    print("%D streaming  :",
          [round(x, 4) if x is not None else None for x in d_stream])

    for i in range(len(precios)):
        if not np.isnan(k_vec[i]) and k_stream[i] is not None:
            assert abs(k_vec[i] - k_stream[i]) < 1e-9, \
                f"❌ %K discrepa en i={i}: {k_vec[i]} vs {k_stream[i]}"
        if not np.isnan(d_vec[i]) and d_stream[i] is not None:
            assert abs(d_vec[i] - d_stream[i]) < 1e-9, \
                f"❌ %D discrepa en i={i}: {d_vec[i]} vs {d_stream[i]}"
    print("✅ (A) Vectorizado y streaming coinciden.")
    print("Buffer circular:", ind.recent_prices())


def test_casos_conocidos():
    # Sin suavizado (smooth_k=1) para comparar %K_raw directamente.
    k_period = 5
    # El último precio es el máximo del rango -> %K = 100.
    sube = [1, 2, 3, 4, 5, 6]
    k, _ = stoch_vectorized(sube, k_period, smooth_k=1, d_period=1)
    assert abs(k[-1] - 100.0) < 1e-9, f"❌ Máximo del rango debería dar 100, dio {k[-1]}"
    print("✅ (B1) Precio en el máximo del rango -> %K = 100.")

    # El último precio es el mínimo del rango -> %K = 0.
    baja = [6, 5, 4, 3, 2, 1]
    k2, _ = stoch_vectorized(baja, k_period, smooth_k=1, d_period=1)
    assert abs(k2[-1] - 0.0) < 1e-9, f"❌ Mínimo del rango debería dar 0, dio {k2[-1]}"
    print("✅ (B2) Precio en el mínimo del rango -> %K = 0.")


def test_latencia():
    ind = Stochastic(14, 3, 3)
    for p in range(100):              # calentamiento
        ind.update(float(p % 50))
    n = 100_000
    t0 = time.perf_counter()
    for i in range(n):
        ind.update(float(i % 50))
    t1 = time.perf_counter()
    ms = (t1 - t0) / n * 1000.0
    print(f"Latencia media por tick: {ms:.6f} ms")
    assert ms < 15.0, f"❌ Latencia {ms:.4f} ms supera 15 ms"
    print("✅ (C) Latencia OK (< 15 ms/tick).")


if __name__ == "__main__":
    test_correctitud()
    print("-" * 60)
    test_casos_conocidos()
    print("-" * 60)
    test_latencia()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
