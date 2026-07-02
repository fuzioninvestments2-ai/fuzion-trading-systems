"""
bot/test_collector.py
=====================
Prueba del colector 24/7 (Regla 4), sin red.

Verifica que, al recibir ticks e historial, guarda velas en el repositorio
(que es lo que hace crecer los tiempos largos = aprendizaje continuo).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.collector import Collector
from bot.history import HistoryRepository


def test_acumula_historial():
    repo = HistoryRepository(":memory:")
    # ssid falso: no conectamos, solo probamos los callbacks de guardado.
    col = Collector("42[\"auth\",{}]", repo, watchlist=["EURUSD_otc"])

    # Simulamos historial recibido (varias velas de 1 min).
    hist = [[i * 60.0 + s, 1.10 + i * 0.001] for i in range(10) for s in (0, 30)]
    col._on_history({"asset": "EURUSD_otc", "period": 60, "history": hist})

    # Simulamos un tick nuevo que cierra otra vela.
    col._on_tick("EURUSD_otc", 700.0, 1.12)   # minuto 11 -> cierra el 10

    n = repo.count("EURUSD_otc", "M1")
    assert n >= 9, f"❌ Debería haber acumulado velas, hay {n}"
    print(f"✅ El colector acumuló {n} velas M1 en el historial.")


if __name__ == "__main__":
    test_acumula_historial()
    print("-" * 60)
    print("✅ PRUEBA PASADA.")
