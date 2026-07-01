"""
bot/test_motor_sim.py
=====================
Prueba de humo del simulador del motor completo (Regla 4).

Verifica que el motor corre de punta a punta y devuelve una estructura coherente.
(No mide rentabilidad; el resultado es una moneda al aire por diseño.)
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.run_motor_sim import run


def test_simulador_corre():
    res = run(preset="moderado", seed=7, n_ticks=1500)
    assert res["preset"] == "moderado"
    assert res["sesiones"] >= 1, "❌ Debía registrar al menos una sesión"
    for r in res["detalle"]:
        # Cada resumen de sesión debe tener las claves esperadas.
        for k in ("trades", "wins", "losses", "win_rate", "profit"):
            assert k in r, f"❌ Falta la clave '{k}' en el resumen"
    print("✅ El motor completo corre de punta a punta:", res["detalle"])


if __name__ == "__main__":
    test_simulador_corre()
    print("-" * 60)
    print("✅ PRUEBA PASADA.")
