"""
bot/test_scan_backwards.py
=========================
Valida el escaneo de historial hacia ATRÁS SIN red: guardado de velas OHLC (varios
formatos) y la lógica de paginación con un cliente falso que simula respuestas.
"""

import asyncio

from bot.pocket_service import PocketService


def _svc():
    return PocketService('42["auth",{}]', demo=True, db_path=":memory:")


def test_store_ohlc_dict():
    s = _svc()
    candles = [{"time": 1000 + i * 60, "open": 1.1, "high": 1.11,
                "low": 1.09, "close": 1.10, "volume": 1} for i in range(10)]
    ok = s._store_ohlc_candles("EURUSD_otc", {"period": 60}, candles)
    assert ok and s.repo.count("EURUSD_otc", "M1") == 10
    print("OK guarda velas OHLC en formato dict")


def test_store_ohlc_lista():
    s = _svc()
    # formato lista [t, open, close, high, low, volume]
    candles = [[2000 + i * 300, 1.1, 1.10, 1.12, 1.08, 5] for i in range(8)]
    ok = s._store_ohlc_candles("EURUSD_otc", {"period": 300}, candles)
    assert ok and s.repo.count("EURUSD_otc", "tf300") == 8
    print("OK guarda velas OHLC en formato lista")


def test_on_history_ruta_ohlc():
    s = _svc()
    s._on_history({"asset": "GBPUSD_otc", "period": 60,
                   "candles": [{"time": 1000, "open": 1, "high": 1,
                                "low": 1, "close": 1}]})
    assert s.repo.count("GBPUSD_otc", "M1") == 1
    print("OK _on_history detecta y guarda velas OHLC (no solo ticks)")


def test_scan_backwards_pagina_y_para():
    s = _svc()
    # Sembramos algo de historial (punto de partida).
    base = 1_700_000_000
    s.repo.record_many("EURUSD_otc", "M1",
                       [{"timestamp": (base + i * 60) * 1000, "open": 1.1,
                         "high": 1.1, "low": 1.1, "close": 1.1, "volume": 1}
                        for i in range(20)])

    # Cliente FALSO: cada página devuelve velas MÁS antiguas, hasta agotarse.
    class _FakeClient:
        def __init__(self, svc):
            self.svc = svc
            self.paginas = 3
        @property
        def is_connected(self):
            return True
        async def wait_connected(self, timeout=30.0):
            return True
        async def set_asset(self, asset, period=60):
            pass                                          # no-op (sin red)
        async def load_history_period(self, asset, period, end_time, index=1):
            if self.paginas <= 0:
                return                                    # sin más historial
            self.paginas -= 1
            # Devuelve 10 velas anteriores a end_time.
            cs = [{"time": end_time - (k + 1) * 60, "open": 1.1, "high": 1.1,
                   "low": 1.1, "close": 1.1, "volume": 1} for k in range(10)]
            self.svc._on_history({"asset": asset, "period": period, "candles": cs})

    s.connected = True
    s.client = _FakeClient(s)
    total = asyncio.run(s.scan_backwards("EURUSD_otc", period=60,
                                         max_days=365, paginas=50, espera=0.02))
    # 20 iniciales + 3 páginas * 10 = 50 (sin duplicar).
    assert total >= 45, total
    print(f"OK escaneo hacia atrás pagina y se detiene solo ({total} velas)")


def test_scan_backwards_sobrevive_caida():
    """
    La conexión se cae en la 1ª página (ConnectionClosed) y se recupera: el
    escaneo debe REINTENTAR y terminar con las velas, no abortar en 0. Esto
    reproduce el fallo real (1005) que dejaba en 0 las temporalidades largas.
    """
    from websockets.exceptions import ConnectionClosedOK

    s = _svc()
    base = 1_700_000_000
    s.repo.record_many("EURUSD_otc", "tf900",
                       [{"timestamp": (base + i * 900) * 1000, "open": 1.1,
                         "high": 1.1, "low": 1.1, "close": 1.1, "volume": 1}
                        for i in range(20)])

    class _FlakyClient:
        def __init__(self, svc):
            self.svc = svc
            self._vivo = True
            self.paginas = 2
            self.cayo_una_vez = False
        @property
        def is_connected(self):
            return self._vivo
        async def wait_connected(self, timeout=30.0):
            self._vivo = True                             # run() reconecta
            return True
        async def set_asset(self, asset, period=60):
            # Primera vez: simula el socket muerto (1005) y se marca caído.
            if not self.cayo_una_vez:
                self.cayo_una_vez = True
                self._vivo = False
                raise ConnectionClosedOK(None, None)
        async def load_history_period(self, asset, period, end_time, index=1):
            if self.paginas <= 0:
                return
            self.paginas -= 1
            cs = [{"time": end_time - (k + 1) * period, "open": 1.1, "high": 1.1,
                   "low": 1.1, "close": 1.1, "volume": 1} for k in range(10)]
            self.svc._on_history({"asset": asset, "period": period, "candles": cs})

    s.connected = True
    s.client = _FlakyClient(s)
    total = asyncio.run(s.scan_backwards("EURUSD_otc", period=900,
                                         max_days=365, paginas=50, espera=0.02))
    assert s.client.cayo_una_vez                          # hubo caída
    assert total >= 35, total                             # y aun así descargó
    print(f"OK sobrevive a la caída y completa ({total} velas)")


if __name__ == "__main__":
    test_store_ohlc_dict()
    test_store_ohlc_lista()
    test_on_history_ruta_ohlc()
    test_scan_backwards_pagina_y_para()
    test_scan_backwards_sobrevive_caida()
    print("\nTODOS OK — escaneo de historial hacia atrás")
