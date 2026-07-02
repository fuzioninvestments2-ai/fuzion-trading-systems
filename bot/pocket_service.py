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
from collections import deque

from bot.pocket_client import PocketOptionClient
from bot.candles import CandleBuilder
from bot.history import HistoryRepository
from bot.deep_analysis import DeepAnalyzer
from bot.manipulation import ManipulationGuard
from bot.market_hours import is_open
from bot.calibration import calibrate


class PocketService:
    def __init__(self, ssid, demo=True, period=60, logger=None,
                 db_path=None, wait_seconds=10.0):
        self.ssid = ssid
        self.period = period
        self.log = logger or logging.getLogger("pocket_service")
        self.wait_seconds = wait_seconds
        self.repo = HistoryRepository(
            db_path or os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "history.db"))

        self._builders = {}          # asset -> CandleBuilder (para guardar historial)
        self._ticks = {}             # asset -> deque de (ts_seg, precio) para análisis profundo
        self._last_tick = {}         # asset -> último timestamp (segundos, hora real de PO)
        self._calib = {}             # asset -> umbral aprendido (calibración)
        self.balance = None
        self.connected = False

        self.client = PocketOptionClient(
            ssid, on_tick=self._on_tick, on_history=self._on_history,
            on_balance=self._on_balance, demo=demo, logger=self.log)

    # --- callbacks del cliente (se llaman desde el mismo loop async) ---

    def _builder(self, asset):
        return self._builders.setdefault(asset, CandleBuilder(self.period))

    def _tick_buffer(self, asset):
        return self._ticks.setdefault(asset, deque(maxlen=10000))

    def _on_tick(self, asset, ts, price):
        self._last_tick[asset] = ts          # hora real del mercado (PO)
        self._tick_buffer(asset).append((ts, price))
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
        # Reconstruimos las velas + el buffer de ticks desde el historial recibido.
        cb = CandleBuilder(self.period)
        buf = deque(maxlen=10000)
        for row in hist:
            try:
                t, p = float(row[0]), float(row[1])
            except (IndexError, TypeError, ValueError):
                continue
            cb.add_tick(p, t * 1000.0)
            buf.append((t, p))
        self._builders[asset] = cb
        self._ticks[asset] = buf
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
        Cambia al activo pedido, espera datos y hace ANÁLISIS PROFUNDO
        multi-temporalidad (la "ecuación": tiempo corto + medio + largo).

        Devuelve (resultado_dict, seg_próx_vela, nº_ticks).
        El `resultado_dict` viene de DeepAnalyzer: veredicto, dirección, fuerza,
        por_tiempo.
        """
        # HORARIO: si el mercado real está cerrado, ni siquiera analizamos.
        abierto, motivo = is_open(asset_code)
        if not abierto:
            return ({"veredicto": "🚫 MERCADO CERRADO", "direccion": motivo,
                     "fuerza": 0.0, "por_tiempo": {}, "cerrado": True}, None, 0)

        try:
            await self.client.set_asset(asset_code, 60)
        except Exception:
            self.log.exception("No se pudo cambiar de activo")
        await asyncio.sleep(self.wait_seconds)

        seg = self.seconds_to_next_candle(asset_code, tf_seconds)
        ticks = list(self._ticks.get(asset_code, []))
        if len(ticks) < 50:
            return ({"veredicto": "🚫 NO OPERAR", "direccion": "⏸️ pocos datos",
                     "fuerza": 0.0, "por_tiempo": {}}, seg, len(ticks))

        # La "ecuación de tiempo": un tiempo corto (entrada), uno medio y uno
        # largo (tendencia). OTC permite sub-minuto; real nunca baja de 1m.
        is_otc = asset_code.endswith("_otc")
        if is_otc:
            corto = max(5, tf_seconds // 4)
            tfs = tuple(sorted({corto, max(60, tf_seconds), max(300, tf_seconds * 5)}))
        else:
            tfs = tuple(sorted({max(60, tf_seconds), tf_seconds * 3, tf_seconds * 5}))

        # CALIBRACIÓN que aprende: buscamos en el historial de ESTE activo el
        # umbral que mejor habría funcionado, y lo usamos. Se cachea y se
        # recalcula cuando hay ~30 velas nuevas (entrenamiento continuo).
        min_conf, win_rate = 0.25, None
        m1_cal = self.repo.get_recent(asset_code, "M1", 600)
        if m1_cal is not None and len(m1_cal) >= 60:
            cache = self._calib.get(asset_code)
            if cache is None or len(m1_cal) - cache.get("count", 0) >= 30:
                best = calibrate(m1_cal)
                if best:
                    self._calib[asset_code] = {
                        "min_conf": best["min_confidence"],
                        "win_rate": best["win_rate"], "count": len(m1_cal)}
            cache = self._calib.get(asset_code)
            if cache:
                min_conf, win_rate = cache["min_conf"], cache["win_rate"]

        # LECTURA CONTINUA: los tiempos largos usan las velas ACUMULADAS en el
        # historial (cuanto más ha leído el bot, más profundo analiza); los
        # cortos usan los ticks recientes (con ruido filtrado).
        analyzer = DeepAnalyzer(timeframes=tfs, min_conf=min_conf)
        suaves = analyzer._filtrar_ruido(ticks)
        frames = {}
        for tf in tfs:
            if tf < 60:
                cb = CandleBuilder(tf)
                for t, p in suaves:
                    cb.add_tick(p, t * 1000.0)
                frames[tf] = cb.to_dataframe(include_forming=True)
            else:
                agg = self._aggregate_m1(asset_code, tf)
                if agg is None or len(agg) < 6:
                    # Aún no hay historial suficiente -> construir desde ticks.
                    cb = CandleBuilder(tf)
                    for t, p in suaves:
                        cb.add_tick(p, t * 1000.0)
                    agg = cb.to_dataframe(include_forming=True)
                frames[tf] = agg

        resultado = analyzer.analyze_frames(frames)
        resultado["umbral"] = min_conf
        if win_rate is not None:
            resultado["win_rate_hist"] = win_rate

        # BARRERA ANTI-MANIPULACIÓN: si el mercado se comporta raro (spike,
        # congelado, estallido), forzamos NO OPERAR sin importar la señal.
        precios = [p for _, p in ticks[-300:]]
        alerta = ManipulationGuard().check(precios)
        if alerta["suspicious"]:
            resultado["veredicto"] = "🚫 NO OPERAR"
            resultado["manipulacion"] = alerta["reasons"]

        return resultado, seg, len(ticks)

    def _aggregate_m1(self, asset, tf_seconds):
        """
        Agrega las velas M1 ACUMULADAS en el historial a un timeframe mayor.
        Cuantas más velas M1 haya guardado el bot, más velas del tiempo largo
        se pueden formar (la "lectura continua"). Devuelve un DataFrame OHLC.
        """
        import pandas as pd
        m1 = self.repo.get_recent(asset, "M1", 5000)
        if m1 is None or len(m1) == 0:
            return None
        tf_ms = tf_seconds * 1000
        m1 = m1.copy()
        m1["bucket"] = (m1["timestamp"] // tf_ms) * tf_ms
        agg = (m1.groupby("bucket")
               .agg(open=("open", "first"), high=("high", "max"),
                    low=("low", "min"), close=("close", "last"),
                    volume=("volume", "sum"))
               .reset_index()
               .rename(columns={"bucket": "timestamp"})
               .sort_values("timestamp").reset_index(drop=True))
        return agg
