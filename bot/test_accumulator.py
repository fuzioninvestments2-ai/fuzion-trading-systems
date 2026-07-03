"""
bot/test_accumulator.py
=======================
Valida el acumulador SIN red: una ronda con cliente falso debe refrescar la
escalera y guardar velas; si la conexión se cae, espera y NO aborta la ronda.
"""

import asyncio

from bot.pocket_service import PocketService
from bot.accumulator import _accumulate_round, LADDER


def _svc():
    return PocketService('42["auth",{}]', demo=True, db_path=":memory:")


def test_ladder_cubre_5s_a_1d():
    assert LADDER[0] == 5 and LADDER[-1] == 86400
    assert 7200 in LADDER and 60 in LADDER            # 2h y 1m presentes
    print(f"OK escalera {LADDER[0]}s..{LADDER[-1]}s ({len(LADDER)} tiempos)")


def test_ronda_guarda_velas():
    s = _svc()

    class _FakeClient:
        def __init__(self, svc):
            self.svc = svc
        @property
        def is_connected(self):
            return True
        async def wait_connected(self, timeout=30.0):
            return True
        async def set_asset(self, asset, period=60):
            pass
        async def request_history(self, asset, periods):
            # Simula que PO devuelve velas recientes en cada temporalidad.
            for p in periods:
                cs = [{"time": 1_700_000_000 + p * k, "open": 1.1, "high": 1.1,
                       "low": 1.1, "close": 1.1, "volume": 1} for k in range(6)]
                self.svc._on_history({"asset": asset, "period": p, "candles": cs})

    s.connected = True
    s._conn_lock = asyncio.Lock()
    s.client = _FakeClient(s)
    asyncio.run(_accumulate_round(s, ["EURUSD_otc"], seg_por_activo=0))
    # M1 (period 60) y varios tf* deben haberse guardado.
    assert s.repo.count("EURUSD_otc", "M1") == 6
    assert s.repo.count("EURUSD_otc", "tf300") == 6
    print("OK una ronda refresca la escalera y guarda velas")


def test_ronda_sobrevive_sin_conexion():
    s = _svc()

    class _DeadClient:
        @property
        def is_connected(self):
            return False
        async def wait_connected(self, timeout=30.0):
            return False                              # nunca reconecta
        async def set_asset(self, asset, period=60):
            raise AssertionError("no debe pedir sin conexión")
        async def request_history(self, asset, periods):
            raise AssertionError("no debe pedir sin conexión")

    s.connected = True
    s._conn_lock = asyncio.Lock()
    s.client = _DeadClient()
    # No debe lanzar: salta el activo y termina la ronda limpio.
    asyncio.run(_accumulate_round(s, ["EURUSD_otc"], seg_por_activo=0))
    print("OK sin conexión la ronda salta el activo sin romper")


if __name__ == "__main__":
    test_ladder_cubre_5s_a_1d()
    test_ronda_guarda_velas()
    test_ronda_sobrevive_sin_conexion()
    print("\nTODOS OK — acumulador continuo")
