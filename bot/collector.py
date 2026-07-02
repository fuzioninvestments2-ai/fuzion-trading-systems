"""
bot/collector.py
================
Colector 24/7: lee activos SIN PARAR y acumula su historial en la base de datos.

EL PORQUÉ (tu visión de "aprendizaje continuo"): los tiempos largos (5m, 15m,
30m) necesitan MUCHAS velas para opinar. Este colector va rotando por una lista
de activos, escuchando cada uno un rato y guardando sus velas. Así, cuando pidas
una señal, los tiempos largos YA tienen datos -> menos indecisión, más firmeza.

Usa su PROPIA conexión a Pocket Option (aparte de la del análisis on-demand) y
comparte la misma base de datos de historial. Es robusto y aislado: si falla, se
reconecta solo y NO afecta al bot principal.

⚠️ Experimental: usa una segunda conexión con el mismo SSID. Si Pocket Option la
rechazara, el bot on-demand sigue funcionando igual.
"""

import asyncio
import logging

from bot.pocket_client import PocketOptionClient
from bot.candles import CandleBuilder

# Lista de activos ACTIVOS (majors + cruces OTC que suelen moverse) para acumular.
WATCHLIST = ["EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", "USDJPY_otc",
             "USDCAD_otc", "USDCHF_otc", "NZDUSD_otc", "EURJPY_otc",
             "GBPJPY_otc", "AUDCAD_otc", "EURGBP_otc", "AUDJPY_otc"]


class Collector:
    def __init__(self, ssid, repo, watchlist=None, demo=True, logger=None,
                 collect_seconds=45):
        self.repo = repo                       # se COMPARTE con el servicio
        self.watchlist = watchlist or WATCHLIST
        self.collect_seconds = collect_seconds
        self.log = logger or logging.getLogger("collector")
        self._builders = {}
        self._stop = False
        self._focus = None                     # activo prioritario (el que mira el usuario)
        self.client = PocketOptionClient(
            ssid, on_tick=self._on_tick, on_history=self._on_history,
            demo=demo, logger=self.log)

    def _builder(self, asset):
        return self._builders.setdefault(asset, CandleBuilder(60))

    def _on_tick(self, asset, ts, price):
        closed = self._builder(asset).add_tick(price, ts * 1000.0)
        if closed is not None:
            self.repo.record_candle(asset, "M1", closed)

    def _on_history(self, payload):
        if not isinstance(payload, dict):
            return
        asset = payload.get("asset")
        hist = payload.get("history", [])
        if not asset:
            return
        cb = CandleBuilder(60)
        for row in hist:
            try:
                t, p = float(row[0]), float(row[1])
            except (IndexError, TypeError, ValueError):
                continue
            cb.add_tick(p, t * 1000.0)
        self._builders[asset] = cb
        for c in cb.closed_candles():
            self.repo.record_candle(asset, "M1", c)

    def set_focus(self, asset):
        """
        Marca el activo que el usuario está mirando ahora para PRIORIZARLO en la
        recolección (así sus tiempos largos se llenan antes). Si no está en la
        watchlist, se añade para poder acumularlo también en la rotación normal.
        """
        if not asset:
            return
        self._focus = asset
        if asset not in self.watchlist:
            self.watchlist.append(asset)

    def _pick(self, i):
        """
        Elige qué activo recolectar en el turno `i`. Intercala el activo en FOCO
        (turnos pares) con la rotación normal de la watchlist. Separado para
        poder probar la lógica sin red.
        """
        if self._focus and i % 2 == 0:
            return self._focus
        return self.watchlist[i % len(self.watchlist)]

    def stop(self):
        self._stop = True
        self.client.stop()

    async def run(self):
        """Conecta y rota por la watchlist acumulando historial, para siempre."""
        # El cliente corre en su propia tarea (con su reconexión).
        asyncio.create_task(self.client.run(asset=self.watchlist[0], period=60))
        await asyncio.sleep(6)                 # dar tiempo a conectar/autenticar
        self.log.info("Colector 24/7 en marcha (aprendizaje continuo).")
        i = 0
        while not self._stop:
            # Intercalamos: un turno el activo en FOCO (si hay), el siguiente la
            # rotación normal. Así el activo que miras acumula el DOBLE de tiempo
            # sin dejar de recolectar el resto de la watchlist.
            asset = self._pick(i)
            try:
                await self.client.set_asset(asset, 60)
            except Exception:
                self.log.exception("Colector: no pudo cambiar de activo")
            await asyncio.sleep(self.collect_seconds)
            i += 1
