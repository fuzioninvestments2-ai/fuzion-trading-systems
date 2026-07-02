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

from bot.collector import Collector, WATCHLIST
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


def _nuevo():
    return Collector("42[\"auth\",{}]", HistoryRepository(":memory:"), demo=True)


def test_set_focus_anade_si_falta():
    c = _nuevo()
    c.set_focus("XAUUSD_otc")               # no está en la lista por defecto
    assert c._focus == "XAUUSD_otc" and "XAUUSD_otc" in c.watchlist
    print("✅ set_focus añade el activo si no estaba.")


def test_set_focus_no_duplica():
    c = _nuevo()
    ya = c.watchlist[0]
    n = len(c.watchlist)
    c.set_focus(ya)
    assert c.watchlist.count(ya) == 1 and len(c.watchlist) == n
    print("✅ set_focus no duplica un activo existente.")


def test_set_focus_vacio_no_rompe():
    c = _nuevo()
    n = len(c.watchlist)
    c.set_focus(None); c.set_focus("")
    assert c._focus is None and len(c.watchlist) == n
    print("✅ set_focus con vacío no cambia nada.")


def test_intercalado_prioriza_foco():
    c = _nuevo()
    c.set_focus("EURUSD_otc")
    picks = [c._pick(i) for i in range(6)]
    # Turnos pares -> foco; el foco sale el DOBLE que un activo normal.
    assert [picks[0], picks[2], picks[4]] == ["EURUSD_otc"] * 3, picks
    print(f"✅ intercalado prioriza el foco (3/6): {picks}")


def test_sin_foco_rota_normal():
    c = _nuevo()
    picks = [c._pick(i) for i in range(len(c.watchlist))]
    assert picks == c.watchlist
    print("✅ sin foco rota la watchlist normal.")


if __name__ == "__main__":
    test_acumula_historial()
    test_set_focus_anade_si_falta()
    test_set_focus_no_duplica()
    test_set_focus_vacio_no_rompe()
    test_intercalado_prioriza_foco()
    test_sin_foco_rota_normal()
    print("-" * 60)
    print("✅ PRUEBAS PASADAS.")
