"""
bot/test_download_history.py
============================
Valida SIN red el troceado por lotes y la descarga de un activo (cliente falso).
"""

import asyncio

from bot.pocket_service import PocketService
from bot.download_history import _lotes, _descargar_uno, PERIODOS, COMPLETO_M1


def test_lotes_trocea_de_5_en_5():
    activos = [f"A{i}_otc" for i in range(12)]
    lotes = list(_lotes(activos, 5))
    assert len(lotes) == 3 and len(lotes[0]) == 5 and len(lotes[-1]) == 2
    # No pierde ni duplica activos.
    assert sum(len(x) for x in lotes) == 12
    print(f"OK trocea 12 activos en {[len(x) for x in lotes]} (de 5 en 5)")


def test_periodos_cubre_5s_a_1d():
    segundos = [p for p, _ in PERIODOS]
    assert segundos[0] == 5 and segundos[-1] == 86400
    assert COMPLETO_M1 == 5000
    print(f"OK periodos {segundos[0]}s..{segundos[-1]}s ({len(PERIODOS)} tiempos)")


def test_descargar_uno_guarda():
    s = PocketService('42["auth",{}]', demo=True, db_path=":memory:")
    s.connected = True
    s._conn_lock = asyncio.Lock()

    class _FakeClient:
        def __init__(self, svc):
            self.svc = svc
            self.restantes = {p: 2 for p, _ in PERIODOS}   # 2 páginas por periodo
        @property
        def is_connected(self):
            return True
        async def wait_connected(self, timeout=30.0):
            return True
        async def set_asset(self, asset, period=60):
            pass
        async def load_history_period(self, asset, period, end_time, index=1):
            if self.restantes.get(period, 0) <= 0:
                return
            self.restantes[period] -= 1
            cs = [{"time": end_time - (k + 1) * period, "open": 1.1, "high": 1.1,
                   "low": 1.1, "close": 1.1, "volume": 1} for k in range(10)]
            self.svc._on_history({"asset": asset, "period": period, "candles": cs})

    # Semilla de partida para que scan_backwards tenga desde dónde retroceder.
    base = 1_700_000_000
    for period, _ in PERIODOS:
        key = "M1" if period == 60 else f"tf{period}"
        s.repo.record_many("EURUSD_otc", key,
                           [{"timestamp": (base + i * period) * 1000, "open": 1.1,
                             "high": 1.1, "low": 1.1, "close": 1.1, "volume": 1}
                            for i in range(5)])
    s.client = _FakeClient(s)
    # espera=0/pausa=0: sin esperas reales, el test corre en < 1s.
    asyncio.run(_descargar_uno(s, "EURUSD_otc", espera=0, pausa=0))
    # Cada periodo debe haber crecido (5 semilla + 2 páginas * 10).
    assert s.repo.count("EURUSD_otc", "M1") > 5
    assert s.repo.count("EURUSD_otc", "tf300") > 5
    print("OK descargar_uno recorre 5s..1d y guarda velas")


if __name__ == "__main__":
    test_lotes_trocea_de_5_en_5()
    test_periodos_cubre_5s_a_1d()
    test_descargar_uno_guarda()
    print("\nTODOS OK — descarga por lotes")
