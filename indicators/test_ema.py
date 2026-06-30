"""
indicators/test_ema.py
=======================
Prueba de validación del módulo EMA (Regla 4).

Verifica DOS cosas:
  (A) Correctitud: el modo vectorizado y el streaming dan el MISMO resultado.
  (B) Latencia: cada tick (EMA.update) debe procesarse muy por debajo del
      presupuesto de 15 ms exigido para el procesamiento en vivo.
"""

import time
import numpy as np
from ema import ema_vectorized, EMA


def test_correctitud():
    """El histórico vectorizado y el streaming tick-a-tick deben coincidir."""
    precios = [10, 11, 12, 11, 10, 9, 10, 12, 14, 13]
    period = 5

    ema_vec = ema_vectorized(precios, period)          # modo lote
    ind = EMA(period)
    ema_stream = [ind.update(p) for p in precios]       # modo streaming

    print("Vectorizado:", np.round(ema_vec, 4))
    print("Streaming  :", np.round(ema_stream, 4))

    # np.allclose tolera el mínimo error de redondeo en coma flotante.
    assert np.allclose(ema_vec, ema_stream), "❌ Los dos modos NO coinciden"
    print("✅ (A) Correctitud OK: ambos modos coinciden.")
    print("Buffer circular (últimos precios):", ind.recent_prices())


def test_latencia():
    """
    Mide el tiempo de un único update() (un tick). Se promedia sobre muchas
    iteraciones para reducir el ruido del reloj; la latencia real por tick es
    el promedio. Umbral exigido: < 15 ms.
    """
    period = 20
    ind = EMA(period)

    # Calentamiento: la primera llamada puede pagar costes de import/JIT-cache.
    for p in range(100):
        ind.update(float(p))

    n_iter = 100_000
    t0 = time.perf_counter()
    for i in range(n_iter):
        ind.update(float(i % 1000))      # precios sintéticos variados
    t1 = time.perf_counter()

    ms_por_tick = (t1 - t0) / n_iter * 1000.0
    print(f"Latencia media por tick: {ms_por_tick:.6f} ms "
          f"(sobre {n_iter:,} ticks)")

    assert ms_por_tick < 15.0, (
        f"❌ Latencia {ms_por_tick:.4f} ms supera el umbral de 15 ms")
    print("✅ (B) Latencia OK: por debajo del umbral de 15 ms/tick.")


if __name__ == "__main__":
    test_correctitud()
    print("-" * 60)
    test_latencia()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
