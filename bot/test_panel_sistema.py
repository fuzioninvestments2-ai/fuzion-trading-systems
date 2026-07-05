"""
bot/test_panel_sistema.py
=========================
Valida SIN red que el PANEL de la tarjeta salga del SISTEMA del trader (sus 12
temporalidades, consenso de los 10 indicadores) usando las velas FRESCAS del
último analyze — no del motor viejo (que metía tiempos ajenos como 4m/240s).
"""

import time
import pandas as pd
from bot import otc_system
from bot.pocket_service import PocketService


class _Svc:
    """Solo lo necesario: reutiliza los métodos reales del servicio."""
    def __init__(self):
        self._frames_recientes = {}
        self.repo = None
    _frames_para_sistema = PocketService._frames_para_sistema
    panel_sistema = PocketService.panel_sistema


def _df(n=260, subiendo=True):
    base = int(time.time()) - n * 60
    filas = []
    for i in range(n):
        c = 100 + (i if subiendo else (n - i)) * 0.2
        filas.append({"timestamp": (base + i * 60) * 1000, "open": c,
                      "high": c + 0.15, "low": c - 0.15, "close": c, "volume": 1})
    return pd.DataFrame(filas)


def test_panel_usa_tiempos_del_trader_sin_ajenos():
    svc = _Svc()
    # Velas frescas del motor: incluye tiempos AJENOS (240=4m, 7200=2h) que el
    # motor viejo mostraba. El panel del sistema debe IGNORARLOS.
    motor = {tf: _df() for tf in (5, 10, 15, 30, 60, 120, 180, 300, 600,
                                  900, 1800, 3600)}
    motor[240] = _df()        # 4m ajeno
    motor[7200] = _df()       # 2h ajeno
    svc._frames_recientes["EURUSD_otc"] = motor

    panel = svc.panel_sistema("EURUSD_otc", otc_system)
    # Solo tiempos del sistema (12), ninguno ajeno.
    assert 240 not in panel and 7200 not in panel, "no debe mostrar 4m/2h"
    assert set(panel).issubset(set(otc_system.TIMEFRAMES))
    assert len(panel) >= 11, panel          # 5s..1H con datos
    # Tendencia alcista -> todos CALL (consenso limpio, no desorden).
    dirs = {p["dir"] for p in panel.values()}
    assert dirs == {"CALL"}, f"panel no alineado: {panel}"
    # 'conf' es fracción de indicadores que coinciden (0-1).
    assert all(0.0 <= p["conf"] <= 1.0 for p in panel.values())
    print(f"OK panel = sistema del trader ({len(panel)} tiempos, todos CALL, "
          f"sin 4m/2h)")


def test_bajista_da_put_en_todo_el_panel():
    svc = _Svc()
    svc._frames_recientes["EURUSD_otc"] = {
        tf: _df(subiendo=False) for tf in otc_system.TIMEFRAMES}
    panel = svc.panel_sistema("EURUSD_otc", otc_system)
    assert {p["dir"] for p in panel.values()} == {"PUT"}, panel
    print("OK tendencia bajista -> panel todo PUT (consenso coherente)")


if __name__ == "__main__":
    test_panel_usa_tiempos_del_trader_sin_ajenos()
    test_bajista_da_put_en_todo_el_panel()
    print("\nTODOS OK — el panel de la tarjeta es el sistema del trader")
