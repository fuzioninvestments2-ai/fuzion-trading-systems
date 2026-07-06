"""
bot/test_panel_sistema.py
=========================
Valida SIN red que el PANEL de la tarjeta salga del SISTEMA PONDERADO (9 tiempos
5s-15m, `calculate_timeframe_signal`), usando las velas FRESCAS del último analyze
— sin tiempos ajenos (4m/2h/1H).
"""

import time
import pandas as pd
from bot import otc_system
from bot.pocket_service import PocketService
from bot.cuantico import TIMEFRAMES_9


class _Svc:
    """Solo lo necesario: reutiliza los métodos reales del servicio."""
    def __init__(self):
        self._frames_recientes = {}
        self.repo = None
    _frames_para_sistema = PocketService._frames_para_sistema
    panel_sistema = PocketService.panel_sistema


def _df(n=120, subiendo=True):
    base = int(time.time()) - n * 60
    filas = []
    for i in range(n):
        c = 100 + (i if subiendo else (n - i)) * 0.3
        filas.append({"timestamp": (base + i * 60) * 1000, "open": c,
                      "high": c + 0.2, "low": c - 0.2, "close": c, "volume": 100})
    return pd.DataFrame(filas)


def test_panel_usa_los_9_tiempos_sin_ajenos():
    svc = _Svc()
    # Velas frescas del motor: incluye tiempos AJENOS (240=4m, 1800=30m, 3600=1H,
    # 7200=2h) que NO están en los 9 del sistema ponderado (5s-15m).
    motor = {tf: _df() for tf in TIMEFRAMES_9}
    for ajeno in (240, 1800, 3600, 7200):
        motor[ajeno] = _df()
    svc._frames_recientes["EURUSD_otc"] = motor

    panel = svc.panel_sistema("EURUSD_otc", otc_system)
    assert set(panel).issubset(set(TIMEFRAMES_9)), panel
    for ajeno in (240, 1800, 3600, 7200):
        assert ajeno not in panel, f"no debe mostrar {ajeno}"
    assert len(panel) == len(TIMEFRAMES_9), panel
    # Tendencia alcista -> dirección CALL y % > 50 en los tiempos.
    for tf, p in panel.items():
        assert p["dir"] == "CALL", (tf, p)
        assert p["pct"] > 50 and 0.0 <= p["conf"] <= 1.0
    print(f"OK panel = 9 tiempos ponderados (5s-15m), alcista -> CALL, sin ajenos")


def test_bajista_da_put():
    svc = _Svc()
    svc._frames_recientes["EURUSD_otc"] = {tf: _df(subiendo=False)
                                           for tf in TIMEFRAMES_9}
    panel = svc.panel_sistema("EURUSD_otc", otc_system)
    for tf, p in panel.items():
        assert p["dir"] == "PUT" and p["pct"] < 50, (tf, p)
    print("OK tendencia bajista -> panel todo PUT")


if __name__ == "__main__":
    test_panel_usa_los_9_tiempos_sin_ajenos()
    test_bajista_da_put()
    print("\nTODOS OK — panel del sistema ponderado (9 tiempos)")
