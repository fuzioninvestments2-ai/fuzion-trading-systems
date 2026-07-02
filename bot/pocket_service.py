"""
bot/pocket_service.py
=====================
Puente entre el cliente EN VIVO de Pocket Option y el menú de Telegram.

Mantiene la conexión abierta y, cuando el usuario pide analizar un activo:
  1. cambia el flujo de PO a ese activo,
  2. espera un momento a que lleguen historial + precios,
  3. construye velas, corre la estrategia y devuelve la señal REAL.

También guarda todo en el historial (SQLite). SOLO LECTURA: no opera.
"""

import asyncio
import logging
import os

from bot.pocket_client import PocketOptionClient
from bot.candles import CandleBuilder
from bot.history import HistoryRepository
from bot.scoring_strategy import ScoringStrategy, CALL, PUT, HOLD
from bot.config import TradingConfig


class PocketService:
    def __init__(self, ssid, demo=True, period=60, logger=None,
                 db_path=None, wait_seconds=3.0):
        self.ssid = ssid
        self.period = period
        self.log = logger or logging.getLogger("pocket_service")
        self.wait_seconds = wait_seconds
        self.repo = HistoryRepository(
            db_path or os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "history.db"))

        self._builders = {}          # asset -> CandleBuilder
        self.balance = None
        self.connected = False

        self.client = PocketOptionClient(
            ssid, on_tick=self._on_tick, on_history=self._on_history,
            on_balance=self._on_balance, demo=demo, logger=self.log)

    # --- callbacks del cliente (se llaman desde el mismo loop async) ---

    def _builder(self, asset):
        return self._builders.setdefault(asset, CandleBuilder(self.period))

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
        # Reconstruimos las velas de ese activo desde el historial recibido.
        cb = CandleBuilder(self.period)
        for row in hist:
            try:
                t, p = float(row[0]), float(row[1])
            except (IndexError, TypeError, ValueError):
                continue
            cb.add_tick(p, t * 1000.0)
        self._builders[asset] = cb
        for c in cb.closed_candles():
            self.repo.record_candle(asset, "M1", c)

    def _on_balance(self, payload):
        if isinstance(payload, dict):
            self.balance = float(payload.get("balance", 0))

    # --- API para Telegram ---

    async def start(self):
        """Arranca la conexión en segundo plano (como tarea del mismo loop)."""
        self.connected = True
        asyncio.create_task(self.client.run(asset="EURUSD_otc",
                                            period=self.period))

    async def analyze(self, asset_code, period=60):
        """
        Cambia al activo pedido, espera datos y analiza. Devuelve
        (señal, confianza, detalles, nº_velas).
        """
        try:
            await self.client.set_asset(asset_code, period)
        except Exception:
            self.log.exception("No se pudo cambiar de activo")
        # Damos tiempo a que lleguen historial + primeros ticks.
        await asyncio.sleep(self.wait_seconds)

        cb = self._builders.get(asset_code)
        if cb is None:
            return HOLD, 0.0, {"motivo": "sin datos aún"}, 0
        df = cb.to_dataframe(include_forming=True)
        if len(df) < 5:
            return HOLD, 0.0, {"motivo": "pocas velas"}, len(df)

        cfg = TradingConfig(stack_method="aggressive")
        cfg.min_confidence = 0.25     # sensible para dar dirección en modo manual
        signal, conf, d = ScoringStrategy(cfg).analyze(df)
        return signal, conf, d, len(df)
