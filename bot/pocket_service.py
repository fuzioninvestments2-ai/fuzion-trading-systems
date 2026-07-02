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
from bot.scoring_strategy import regime as _regime
from bot.void_detector import detect_void
from bot.payout import parse_assets
from bot.candle_patterns import detect_patterns
from bot.vwap import vwap_signal

# Umbral de PAGO BAJO (%): por debajo de esto avisamos "no entrar", según la
# regla del usuario ("EurUsdOTC está el % de pago bajo, yo no entro a ese
# candel"). Un payout más bajo empeora el valor esperado de cada operación.
LOW_PAYOUT_PCT = 80


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
        self._payouts = {}           # asset -> % de pago (payout) de Pocket Option
        self._last_dir = {}          # asset -> (direccion, ts) para estabilidad
        self.balance = None
        self.connected = False

        self.client = PocketOptionClient(
            ssid, on_tick=self._on_tick, on_history=self._on_history,
            on_balance=self._on_balance, on_assets=self._on_assets,
            demo=demo, logger=self.log)

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

    def _on_assets(self, assets):
        """
        Extrae el % de PAGO (payout) de cada activo de la lista de PO.
        Delegado a bot/payout.parse_assets, que valida por RANGO (un payout es un
        %, así que debe caer en un rango sensato) en vez de fiarse de un índice
        fijo. Así el filtro de "pago bajo" no falla si PO reordena el array.
        """
        nuevos = parse_assets(assets)
        if nuevos:
            self._payouts.update(nuevos)

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

        # ESCALERA COMPLETA de tiempos (lee toda la línea de tiempo, lo clave es
        # la ALINEACIÓN). OTC incluye sub-minuto; real empieza en 1m.
        is_otc = asset_code.endswith("_otc")
        if is_otc:
            tfs = (15, 30, 60, 180, 300, 600, 900, 1800)   # 15s..30m
        else:
            tfs = (60, 180, 300, 900, 1800)                # 1m..30m

        # CALIBRACIÓN que aprende: buscamos en el historial de ESTE activo el
        # umbral que mejor habría funcionado, y lo usamos. Se cachea y se
        # recalcula cuando hay ~30 velas nuevas (entrenamiento continuo).
        min_conf, win_rate = 0.18, None
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

        # RÉGIMEN (Oscillate/Slide) desde un tiempo medio con datos. Se calcula
        # ANTES del análisis para AJUSTAR los pesos de indicadores: en tendencia
        # mandan MACD/medias; en rango mandan los rebotes techo/piso (RSI/Bollinger).
        reg = adxv = None
        for tfm in (60, 180, 300):
            fm = frames.get(tfm)
            if fm is not None and len(fm) >= 20:
                reg, adxv = _regime(fm["high"], fm["low"], fm["close"])
                break

        resultado = analyzer.analyze_frames(frames, regimen=reg)
        resultado["umbral"] = min_conf
        if win_rate is not None:
            resultado["win_rate_hist"] = win_rate
        if reg:
            resultado["regime"] = reg
            resultado["adx"] = round(adxv, 1)

        # GRÁFICO: velas M1 recientes para dibujar en Telegram.
        chart_df = self.repo.get_recent(asset_code, "M1", 45)
        resultado["chart"] = chart_df

        # VWAP: nivel de referencia (precio "justo") ponderado por actividad.
        # Indica de qué lado del precio justo estamos: por encima = sesgo alcista,
        # por debajo = bajista. Es contexto, no una orden.
        if chart_df is not None and len(chart_df) >= 5:
            vw = vwap_signal(chart_df)
            if vw["vwap"] is not None:
                resultado["vwap"] = vw

        # PATRONES DE VELA sobre el tiempo más corto (el de la ENTRADA): la FORMA
        # de la vela cuenta lo que los indicadores no ven. Un doji = indecisión
        # (fuerza NO OPERAR); martillo/envolvente = confirmación de dirección.
        corto = min(frames) if frames else None
        if corto is not None and frames[corto] is not None and len(frames[corto]) >= 2:
            pat = detect_patterns(frames[corto])
            if pat["patrones"]:
                resultado["patrones"] = pat["patrones"]
            if pat["indecision"]:
                resultado["veredicto"] = "🚫 NO OPERAR"
                resultado["indecision_vela"] = True
                base_expl = resultado.get("explicacion", "")
                resultado["explicacion"] = (
                    "Vela DOJI (indecisión): compradores y vendedores empatados, "
                    "sin dirección clara. " + base_expl).strip()

        # DETECTOR DE VACÍO DEL MERCADO: huecos/silencio en el flujo de precios.
        # Distinto de "plano": aquí NO llegan ticks (feed congelado o con huecos),
        # así que la lectura se calcula sobre datos muertos -> NO OPERAR. Usamos
        # los timestamps de los propios ticks (gaps internos y densidad), que no
        # dependen de un reloj sincronizado con el servidor.
        vac = detect_void(ticks[-400:])
        if vac["void"]:
            resultado["veredicto"] = "🚫 NO OPERAR"
            resultado["direccion"] = "🕳️ vacío de mercado"
            resultado["explicacion"] = (
                "Vacío en el flujo de precios (" + "; ".join(vac["reasons"])
                + "). El feed no es fiable ahora; no operes sobre datos viejos.")
            resultado["vacio"] = vac["reasons"]

        # DETECTOR DE MERCADO PLANO: si el precio casi no se mueve, cualquier
        # "señal" es ruido -> avisamos claro para que el usuario elija otro activo.
        precios_v = [p for _, p in ticks[-600:]]
        if precios_v:
            media = sum(precios_v) / len(precios_v)
            rango_pct = (max(precios_v) - min(precios_v)) / media if media else 0
            if rango_pct < 0.0004:               # < 0.04% de rango = casi plano
                resultado["veredicto"] = "🚫 NO OPERAR"
                resultado["direccion"] = "😴 mercado plano"
                resultado["explicacion"] = ("Este activo casi no se mueve ahora; "
                                            "cualquier señal sería ruido. Elige "
                                            "un activo más activo.")
                resultado["plano"] = True

        # PAYOUT: añadimos el % de pago; si es bajo, avisamos (tu regla: no
        # entrar en activos con pago bajo).
        payout = self._payouts.get(asset_code)
        if payout is not None:
            resultado["payout"] = payout
            if payout < LOW_PAYOUT_PCT:
                resultado["pago_bajo"] = True

        # GUARDIÁN DE ESTABILIDAD (indecisión): si la señal acaba de cambiar de
        # dirección en pocos segundos, el mercado está indeciso -> NO OPERAR
        # hasta que se estabilice.
        now_ts = self._last_tick.get(asset_code)
        dtxt = resultado.get("direccion", "")
        cur = "UP" if "UP" in dtxt else ("DOWN" if "DOWN" in dtxt else None)
        if cur and now_ts:
            last = self._last_dir.get(asset_code)
            if last and (now_ts - last[1]) < 25 and last[0] != cur:
                resultado["veredicto"] = "🚫 NO OPERAR"
                resultado["explicacion"] = ("Indecisión: la señal acaba de "
                                            "cambiar de dirección. Espera a que "
                                            "se estabilice antes de entrar.")
                resultado["inestable"] = True
            self._last_dir[asset_code] = (cur, now_ts)

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
