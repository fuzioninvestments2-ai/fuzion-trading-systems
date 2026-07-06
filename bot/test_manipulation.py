"""
bot/test_manipulation.py
========================
Prueba del guardián anti-manipulación (Regla 4).

Verifica:
  (A) Un mercado normal (paseo aleatorio suave) NO se marca como sospechoso.
  (B) Un SPIKE (salto gigante) se detecta.
  (C) Un precio CONGELADO se detecta.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.manipulation import ManipulationGuard


def _normal(n=200, seed=1):
    rng = random.Random(seed)
    p = 100.0
    out = []
    for _ in range(n):
        p += rng.uniform(-0.2, 0.2)
        out.append(p)
    return out


def test_normal_no_sospechoso():
    g = ManipulationGuard()
    r = g.check(_normal())
    assert not r["suspicious"], f"❌ Mercado normal marcado como raro: {r}"
    print("✅ (A) Mercado normal -> no sospechoso.")


def test_spike():
    g = ManipulationGuard()
    precios = _normal()
    precios[120] += 15.0        # salto gigante artificial (spike)
    r = g.check(precios)
    assert r["suspicious"] and any("spike" in x for x in r["reasons"]), r
    print("✅ (B) Spike detectado:", r["reasons"])


def test_movimiento_direccional_no_es_spike():
    # Un movimiento FUERTE y direccional (vela grande a favor de la tendencia, sin
    # rebote) NO es manipulación -> el trader lo opera. No debe marcarse "spike".
    g = ManipulationGuard()
    precios = _normal(120)
    salto = precios[-1]
    for k in range(1, 40):                     # empujón sostenido hacia arriba
        precios.append(salto + k * 2.0)
    r = g.check(precios)
    assert not any("spike" in x for x in r["reasons"]), r
    print("✅ (B2) Movimiento direccional (sin rebote) NO se marca como spike.")


def test_congelado():
    g = ManipulationGuard()
    # Mitad normal, mitad congelado (mismo precio repetido).
    precios = _normal(100) + [100.0] * 100
    r = g.check(precios)
    assert r["suspicious"] and any("congelado" in x for x in r["reasons"]), r
    print("✅ (C) Precio congelado detectado:", r["reasons"])


if __name__ == "__main__":
    test_normal_no_sospechoso()
    test_spike()
    test_movimiento_direccional_no_es_spike()
    test_congelado()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
