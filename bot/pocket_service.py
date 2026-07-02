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
        self._last_tick = {}         # asset -> último timestamp (segundos, hora real de PO)
        self.balance = None
        self.connected = False

        self.client = PocketOptionClient(
            ssid, on_tick=self._on_tick, on_history=self._on_history,
            on_balance=self._on_balance, demo=demo, logger=self.log)

    # --- callbacks del cliente (se llaman desde el mismo loop async) ---

    def _builder(self, asset):
        return self._builders.setdefault(asset, CandleBuilder(self.period))

    def _on_tick(self, asset, ts, price):
        self._last_tick[asset] = ts          # hora real del mercado (PO)
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

    def seconds_to_next_candle(self, asset_code, tf_seconds):
        """
        Segundos que faltan para que ABRA la próxima vela del timeframe elegido.
        En binarias, la entrada correcta es al ABRIR la vela; por eso este dato
        es clave. Usa la hora REAL del mercado (último tick de PO).
        """
        last_ts = self._last_tick.get(asset_code)
        if not last_ts or tf_seconds <= 0:
            return None
        return int(tf_seconds - (last_ts % tf_seconds))

    async def analyze(self, asset_code, tf_seconds=60):
        """
        Cambia al activo pedido, espera datos y analiza usando TODO el historial
        acumulado. Devuelve (señal, confianza, detalles, nº_velas, seg_próx_vela).
        `tf_seconds` es la expiración elegida (M1=60, M5=300...), usada para el
        cálculo de TIMING (cuándo entrar).
        """
        try:
            # Datos siempre en M1 (buena resolución); el tf del usuario es la
            # expiración y se usa para el timing de entrada.
            await self.client.set_asset(asset_code, 60)
        except Exception:
            self.log.exception("No se pudo cambiar de activo")
        # Damos tiempo a que lleguen historial + primeros ticks.
        await asyncio.sleep(self.wait_seconds)

        # Analizamos con TODO lo acumulado en el historial (más datos = mejor),
        # más la vela que se está formando ahora mismo.
        df = self.repo.get_recent(asset_code, "M1", 400)
        cb = self._builders.get(asset_code)
        if cb is not None:
            live = cb.to_dataframe(include_forming=True)
            if len(live) and len(df):
                # Unimos y quitamos duplicados por timestamp (nos quedamos con
                # la última versión de cada vela).
                import pandas as pd
                df = (pd.concat([df, live])
                      .drop_duplicates(subset="timestamp", keep="last")
                      .sort_values("timestamp").reset_index(drop=True))
            elif len(live):
                df = live

        seg = self.seconds_to_next_candle(asset_code, tf_seconds)
        n = len(df) if df is not None else 0
        if n < 5:
            return HOLD, 0.0, {"motivo": "pocas velas todavía"}, n, seg

        cfg = TradingConfig(stack_method="aggressive")
        cfg.min_confidence = 0.25
        signal, conf, d = ScoringStrategy(cfg).analyze(df)
        return signal, conf, d, n, seg
