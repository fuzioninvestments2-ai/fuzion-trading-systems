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
from bot.weight_learning import learn_weights
from bot.signal_log import SignalTracker, CALL as _SIG_CALL, PUT as _SIG_PUT
from bot.scoring_strategy import regime as _regime, compression as _compression
from bot.void_detector import detect_void
from bot.payout import parse_assets
from bot.candle_patterns import detect_patterns
from bot.vwap import vwap_signal
from bot.levels import detect_levels

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
        self._weights = {}           # asset -> pesos aprendidos por indicador
        self._payouts = {}           # asset -> % de pago (payout) de Pocket Option
        self._last_dir = {}          # asset -> (direccion, ts) para estabilidad
        self._last_signal = {}       # asset -> ts_ms de la última señal registrada
        self.tracker = SignalTracker(self.repo)   # ciclo de aprendizaje real
        self.balance = None
        self.connected = False

        # COLECTOR INTEGRADO (una sola conexión): en los ratos libres el bot rota
        # por la watchlist acumulando historial; cuando llega un análisis, le cede
        # el paso al instante (mediante _conn_lock + _want_analysis). Así tenemos
        # aprendizaje 24/7 SIN abrir una segunda conexión (que era lo inestable).
        from bot.collector import WATCHLIST
        self._watchlist = list(WATCHLIST)
        self._focus = None           # activo prioritario (el que mira el usuario)
        self._conn_lock = None       # asyncio.Lock (se crea al arrancar el loop)
        self._want_analysis = False  # un análisis está esperando la conexión
        self._hist_event = None      # asyncio.Event: llegó historial (escaneo rápido)
        self.collect_seconds = 60    # tiempo por activo (>=60 forma 1 vela M1)

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

    def _marcar_historia(self):
        """Avisa (evento) que acaba de llegar historial: el escáner deja de
        esperar en fijo y avanza YA. Es la clave de la velocidad."""
        ev = getattr(self, "_hist_event", None)
        if ev is not None:
            ev.set()

    def _on_history(self, payload):
        if not isinstance(payload, dict):
            return
        asset = payload.get("asset")
        # Respuesta de historial: puede venir como TICKS ("history": [[t,p],...])
        # o como VELAS ya hechas ("candles"/"data": [{time,open,...},...]). El
        # escaneo hacia atrás (loadHistoryPeriod) suele traer velas OHLC.
        candles = payload.get("candles") or payload.get("data")
        if asset and candles and self._store_ohlc_candles(asset, payload, candles):
            self._marcar_historia()
            return
        hist = payload.get("history", [])
        if not asset or not hist:
            return
        # Periodo del historial recibido (60=M1, 300=M5, ...). Construimos las
        # velas a ESE periodo para dar profundidad a esa temporalidad.
        try:
            period = int(payload.get("period", 60) or 60)
        except (TypeError, ValueError):
            period = 60
        cb = CandleBuilder(period)
        ticks = []
        for row in hist:
            try:
                t, p = float(row[0]), float(row[1])
            except (IndexError, TypeError, ValueError):
                continue
            cb.add_tick(p, t * 1000.0)
            ticks.append((t, p))
        # Guardamos las velas de este periodo (period 60 -> "M1"; otros -> "tf<s>").
        key = "M1" if period == 60 else f"tf{period}"
        velas = cb.closed_candles()
        if velas:
            self.repo.record_many(asset, key, velas)
            self._marcar_historia()
        # Sembramos el buffer/builder en vivo SOLO si aún no hay nada: NO pisamos
        # lo que _on_tick ya acumuló (antes se borraba en cada cambio de activo).
        if period == 60:
            if not self._ticks.get(asset):
                self._ticks[asset] = deque(ticks, maxlen=10000)
            if asset not in self._builders:
                self._builders[asset] = cb

    def _store_ohlc_candles(self, asset, payload, candles):
        """
        Guarda velas OHLC ya hechas (del escaneo hacia atrás). Cada vela puede ser
        dict {time/open/high/low/close/volume} o lista [t,o,c,h,l,...]. Devuelve
        True si guardó algo. Robusto ante formatos distintos (aún por confirmar).
        """
        try:
            period = int(payload.get("period", 60) or 60)
        except (TypeError, ValueError):
            period = 60
        key = "M1" if period == 60 else f"tf{period}"
        filas = []
        for c in candles:
            try:
                if isinstance(c, dict):
                    t = float(c.get("time") or c.get("t") or c.get("timestamp"))
                    o = float(c.get("open", c.get("o")))
                    h = float(c.get("high", c.get("h", o)))
                    lo = float(c.get("low", c.get("l", o)))
                    cl = float(c.get("close", c.get("c", o)))
                    vol = float(c.get("volume", c.get("v", 0)) or 0)
                elif isinstance(c, (list, tuple)) and len(c) >= 5:
                    t, o, cl, h, lo = (float(c[0]), float(c[1]), float(c[2]),
                                       float(c[3]), float(c[4]))
                    vol = float(c[5]) if len(c) > 5 else 0.0
                else:
                    continue
            except (TypeError, ValueError):
                continue
            ts_ms = int(t * 1000) if t < 1e12 else int(t)   # seg o ms -> ms
            filas.append({"timestamp": ts_ms, "open": o, "high": h,
                          "low": lo, "close": cl, "volume": vol})
        if filas:
            self.repo.record_many(asset, key, filas)
            return True
        return False

    async def _sembrar_punto(self, asset, period, key, espera=3.0):
        """
        SIEMBRA un punto de partida cuando el activo no dio tick vivo: fija el
        activo a ESTE periodo (changeSymbol), con lo que PO responde con su
        historial reciente (updateHistoryNewFast) y _on_history lo guarda. Espera
        por evento. Devuelve end_time (segundos, la vela más antigua sembrada
        menos 1) o None si ni así llegó nada. No rompe si el socket está caído:
        aguarda reconexión, coherente con el reinicio interno.
        """
        import contextlib
        try:
            if not self.client.is_connected:
                if not await self.client.wait_connected(timeout=30):
                    return None
                await asyncio.sleep(2)
            lock = self._conn_lock or contextlib.nullcontext()
            async with lock:
                self._hist_event.clear()
                await self.client.set_asset(asset, period)
                try:
                    await asyncio.wait_for(self._hist_event.wait(), timeout=espera)
                except asyncio.TimeoutError:
                    pass
        except Exception:
            return None
        df = self.repo.get_recent(asset, key, 5000)
        if df is not None and len(df):
            return int(df["timestamp"].iloc[0] // 1000) - 1
        # A veces el tick vivo llega aunque no vengan velas de ese periodo.
        return int(self._last_tick.get(asset, 0)) or None

    async def scan_backwards(self, asset, period=60, max_days=60, paginas=200,
                             espera=1.3):
        """
        ESCÁNER HACIA ATRÁS: pide a Pocket Option velas cada vez más ANTIGUAS de
        `asset` para acumular su historial (meses/años si PO los sirve). Va desde
        la vela más antigua que ya tenemos y retrocede, guardando lo que llega,
        hasta que PO deje de dar más (llegó a su límite) o alcancemos `max_days`.

        ⚠️ EXPERIMENTAL: depende del mensaje loadHistoryPeriod (formato no oficial).
        Devuelve cuántas velas hay al final. Honesto: PO puede NO tener años de
        OTC; tomamos lo que exista, sin inventar nada.
        """
        key = "M1" if period == 60 else f"tf{period}"
        # EVENTO de historial: se necesita también para SEMBRAR (abajo).
        if self._hist_event is None:
            self._hist_event = asyncio.Event()
        df = self.repo.get_recent(asset, key, 5000)
        if df is not None and len(df):
            end_time = int(df["timestamp"].iloc[0] // 1000) - 1
        else:
            end_time = int(self._last_tick.get(asset, 0)) or None
            if not end_time:
                # SIN punto de partida: el activo aún no dio un tick vivo (típico
                # en activos poco líquidos o recién puestos). En vez de rendirse
                # con 0 velas (dejaba archivos atrás), SEMBRAMOS: pedimos a PO su
                # historial reciente a ESTE periodo y esperamos por evento; con eso
                # la BD ya tiene velas y sacamos el punto de partida. Antes esto
                # dependía de la suerte de una reconexión.
                end_time = await self._sembrar_punto(asset, period, key)
                if not end_time:
                    self.log.warning("scan_backwards: sin punto de partida para "
                                     "%s (ni sembrando)", asset)
                    return 0
        limite = end_time - int(max_days) * 86400
        sin_avance = 0
        sin_respuesta = 0                       # páginas SIN respuesta (lentas/perdidas)
        reintentos = 0                          # reintentos por caída de conexión
        # Pedimos la conexión con prioridad (el colector cede) y fijamos el foco.
        self._focus = asset
        import contextlib
        from websockets.exceptions import ConnectionClosed
        asset_puesto = False                    # el activo se fija UNA vez (no por página)
        for i in range(1, int(paginas) + 1):
            if not self.connected or end_time <= limite or sin_avance >= 3:
                break
            # Si el socket se cayó (p.ej. PO cierra con 1005), esperar a que run()
            # reconecte antes de pedir. Sin esto, la descarga larga (5s->1d) moría
            # a mitad y las temporalidades grandes quedaban en 0 velas.
            if not self.client.is_connected:
                if not await self.client.wait_connected(timeout=30):
                    self.log.warning("scan_backwards: sin conexión, se corta %s %s",
                                     asset, key)
                    break
                await asyncio.sleep(2)          # dar tiempo a re-autenticar
                asset_puesto = False            # re-fijar el activo tras reconectar
            antes = self.repo.count(asset, key)
            self._want_analysis = True
            lock = self._conn_lock or contextlib.nullcontext()
            try:
                async with lock:               # una página a la vez; suelta entre páginas
                    self._want_analysis = False
                    # Fijar el activo SOLO una vez (o tras reconexión): re-pedirlo
                    # en cada página era espera muerta y ruido de respuestas.
                    if not asset_puesto:
                        await self.client.set_asset(asset, 60)
                        await asyncio.sleep(0.3)
                        asset_puesto = True
                    self._hist_event.clear()
                    await self.client.load_history_period(asset, period, end_time,
                                                          index=i)
                    # Espera POR EVENTO: sigue en cuanto llegan las velas; el
                    # `espera` es solo el tope si PO tarda o no responde.
                    # `respondio` distingue "PO contestó" de "no llegó nada":
                    # sin esto, una respuesta LENTA se confundía con "fin del
                    # historial" y se saltaban páginas (dejaba datos atrás).
                    respondio = True
                    try:
                        await asyncio.wait_for(self._hist_event.wait(),
                                               timeout=espera)
                    except asyncio.TimeoutError:
                        respondio = False
            except (ConnectionClosed, OSError) as exc:
                # Caída a mitad de página: esperar reconexión y REINTENTAR la misma
                # página (no abortar). Límite de reintentos para no colgarse.
                reintentos += 1
                if reintentos > 5:
                    self.log.warning("scan_backwards: demasiadas caídas en %s %s",
                                     asset, key)
                    break
                self.log.info("scan_backwards: reconectando (%s)...", exc)
                await self.client.wait_connected(timeout=30)
                await asyncio.sleep(2)
                continue                        # reintenta esta página tras reconectar
            except Exception:
                self.log.exception("scan_backwards: fallo pidiendo página")
                break
            # NO RESPONDIÓ: página lenta/perdida. No es "fin del historial":
            # se REINTENTA la misma ventana (no se salta) y solo se corta tras
            # muchas seguidas. Así no se dejan páginas atrás por una tardanza.
            if not respondio:
                sin_respuesta += 1
                if sin_respuesta >= 8:
                    self.log.warning("scan_backwards: %s %s sin respuesta x%d, "
                                     "se corta", asset, key, sin_respuesta)
                    break
                continue                        # reintenta la MISMA end_time
            sin_respuesta = 0                    # PO contestó: cadena de silencio rota
            df = self.repo.get_recent(asset, key, 5000)
            nuevo_end = (int(df["timestamp"].iloc[0] // 1000) - 1
                         if df is not None and len(df) else end_time)
            avanzo = (self.repo.count(asset, key) > antes and nuevo_end < end_time)
            # Solo cuenta como "fin" cuando PO RESPONDIÓ y no trajo más antiguas.
            sin_avance = 0 if avanzo else sin_avance + 1
            end_time = min(end_time, nuevo_end)
            self.log.info("scan_backwards %s: pág %d -> %d velas totales",
                          asset, i, self.repo.count(asset, key))
        return self.repo.count(asset, key)

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
        self._conn_lock = asyncio.Lock()
        self._task_client = asyncio.create_task(
            self.client.run(asset="EURUSD_otc", period=self.period))
        # Colector integrado: acumula historial en los ratos libres (misma conexión).
        self._task_collect = asyncio.create_task(self._collect_loop())

    async def stop(self):
        """
        Apagado LIMPIO: para el cliente y cancela las tareas de fondo antes de
        que se cierre el loop. Así no quedan "Task was destroyed" ni tracebacks
        feos al cerrar (Ctrl+C o cerrar la ventana).
        """
        self.connected = False
        try:
            self.client.stop()
        except Exception:
            pass
        for t in (getattr(self, "_task_collect", None),
                  getattr(self, "_task_client", None)):
            if t is not None:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    def _watch_pick(self, i):
        """
        Activo a recolectar en el turno `i`. Intercala el activo en FOCO (el que
        miras) con la rotación normal, para que su historial se llene antes.
        """
        if self._focus and i % 2 == 0:
            return self._focus
        return self._watchlist[i % len(self._watchlist)]

    async def _collect_loop(self):
        """
        Rota por la watchlist acumulando historial usando la ÚNICA conexión. Cada
        ráfaga toma el lock; si un análisis está esperando (_want_analysis), corta
        la ráfaga y suelta la conexión en ~1s para no hacerte esperar.
        """
        await asyncio.sleep(8)                     # deja conectar/autenticar
        self.log.info("Colector integrado en marcha (misma conexión).")
        i = 0
        while self.connected:
            try:
                asset = self._watch_pick(i)
                async with self._conn_lock:
                    self._want_analysis = False
                    await self.client.set_asset(asset, 60)
                    # Recolecta en ráfaga; cede de inmediato si llega un análisis.
                    for _ in range(self.collect_seconds):
                        if self._want_analysis:
                            break
                        await asyncio.sleep(1)
                i += 1
            except asyncio.CancelledError:
                raise                              # apagado limpio
            except Exception as exc:
                # Aviso CORTO (sin traceback que asuste). Suele ser la conexión
                # reconectando; el propio cliente se reconecta solo.
                self.log.warning("Colector: salto una ráfaga (%s)", exc)
                await asyncio.sleep(2)
            await asyncio.sleep(0.2)               # deja que el análisis tome el lock

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

    async def analyze(self, asset_code, tf_seconds=60, registrar=True):
        """
        Cambia al activo pedido, espera datos y hace ANÁLISIS PROFUNDO
        multi-temporalidad (la "ecuación": tiempo corto + medio + largo).

        registrar: si False, NO guarda la señal en el tracker (lo usa el camino
        del SISTEMA del trader, que registra SU propia señal, no la del motor
        viejo — así el aprendizaje mide el sistema correcto).

        Devuelve (resultado_dict, seg_próx_vela, nº_ticks).
        El `resultado_dict` viene de DeepAnalyzer: veredicto, dirección, fuerza,
        por_tiempo.
        """
        # HORARIO: si el mercado real está cerrado, ni siquiera analizamos.
        abierto, motivo = is_open(asset_code)
        if not abierto:
            return ({"veredicto": "🚫 MERCADO CERRADO", "direccion": motivo,
                     "fuerza": 0.0, "por_tiempo": {}, "cerrado": True}, None, 0)

        # El análisis tiene PRIORIDAD sobre el colector: pedimos la conexión y el
        # colector cede en ~1s. Priorizamos también este activo para lo siguiente.
        self._focus = asset_code
        self._want_analysis = True
        import contextlib
        lock = self._conn_lock or contextlib.nullcontext()
        async with lock:
            self._want_analysis = False
            try:
                await self.client.set_asset(asset_code, 60)
            except Exception:
                self.log.exception("No se pudo cambiar de activo")
            # Si el activo tiene POCO historial, pedimos a PO más profundidad a
            # varios periodos (5m/15m/30m) para que los tiempos largos no salgan
            # "pocos datos". Solo cuando hace falta (no molesta a los ya cargados).
            try:
                if self.repo.count(asset_code, "M1") < 120:
                    await self.client.request_history(asset_code,
                                                      (300, 900, 1800))
            except Exception:
                self.log.exception("No se pudo pedir historial profundo")
            await asyncio.sleep(self.wait_seconds)
            seg = self.seconds_to_next_candle(asset_code, tf_seconds)
            ticks = list(self._ticks.get(asset_code, []))
        # POCOS TICKS EN VIVO: solo es "pocos datos" si TAMPOCO hay historial
        # guardado. Antes salía siempre vacío al reiniciar (ticks en vivo = 0),
        # aunque en disco hubiera miles de velas: el análisis lee el HISTORIAL
        # (abajo), así que si lo hay, seguimos y la tarjeta sale con datos.
        hist_m1 = self.repo.count(asset_code, "M1")
        if len(ticks) < 50 and hist_m1 < 60:
            return ({"veredicto": "🚫 NO OPERAR", "direccion": "⏸️ pocos datos",
                     "fuerza": 0.0, "por_tiempo": {}}, seg, len(ticks))

        # LECTURA ENVOLVENTE: escalera COMPLETA de 5s a 1 día, SIN saltos. El
        # trader lee toda la escala temporal a la vez: los micro-tiempos (5s-30s)
        # dan la ENTRADA fina y los macro-tiempos (1h-1d) dan el SESGO/tendencia
        # mayor. Cuanto más ancha la escalera, más robusta la ALINEACIÓN fractal.
        # OTC incluye sub-minuto (velas sintéticas de PO); real empieza en 1m.
        # Un tiempo sin >=6 velas se ignora solo en _combinar (no ensucia nada),
        # así que añadir 1h-1d es seguro: solo suma cuando ya hay historial.
        is_otc = asset_code.endswith("_otc")
        _FULL = (5, 10, 15, 30, 60, 120, 180, 240, 300, 600, 900, 1800,
                 3600, 7200, 14400, 86400)                   # 5s .. 1d
        if is_otc:
            tfs = _FULL
        else:
            tfs = tuple(t for t in _FULL if t >= 60)         # 1m .. 1d
        # Garantizamos que la temporalidad ELEGIDA por el usuario esté siempre
        # en el panel (p.ej. si pide M2 = 120s, que aparezca su línea de 2m).
        if tf_seconds not in tfs:
            tfs = tuple(sorted(set(tfs) | {tf_seconds}))

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

        # APRENDIZAJE DE PESOS: además del umbral, aprendemos qué INDICADORES han
        # acertado más en ESTE activo y ajustamos su peso. Mismo caché/cadencia
        # que la calibración (~30 velas nuevas) porque es costoso (recorre el
        # historial re-evaluando indicadores).
        learned = None
        learned_stats = None
        if m1_cal is not None and len(m1_cal) >= 60:
            wcache = self._weights.get(asset_code)
            if wcache is None or len(m1_cal) - wcache.get("count", 0) >= 30:
                lw = learn_weights(m1_cal)
                if lw:
                    self._weights[asset_code] = {
                        "multipliers": lw["multipliers"],
                        "stats": lw["stats"], "count": len(m1_cal)}
            wcache = self._weights.get(asset_code)
            if wcache:
                learned = wcache["multipliers"]
                learned_stats = wcache["stats"]

        # PREFERIR el aprendizaje de señales REALES cuando ya hay bastantes
        # resueltas: es la verdad del bot (no un backtest). Si no, se queda el de
        # backtest. Reemplaza (no promedia) porque mide exactamente lo que pasó.
        learned_source = "backtest" if learned else None
        try:
            real = self.tracker.learned_multipliers(asset_code)
            if real:
                learned = real["multipliers"]
                learned_stats = real["stats"]
                learned_source = "real"
        except Exception:
            self.log.exception("No se pudo aprender de señales reales")

        # LECTURA CONTINUA: los tiempos largos usan las velas ACUMULADAS en el
        # historial (cuanto más ha leído el bot, más profundo analiza); los
        # cortos usan los ticks recientes (con ruido filtrado).
        analyzer = DeepAnalyzer(timeframes=tfs, min_conf=min_conf)
        analyzer.learned = learned            # pesos aprendidos por indicador
        suaves = analyzer._filtrar_ruido(ticks)
        frames = {}
        for tf in tfs:
            # 1) HISTORIAL GUARDADO primero (para TODOS los tiempos, incluido el
            #    sub-minuto). Clave: 'M1' para 60s; 'tf<seg>' el resto. Así la
            #    tarjeta tiene datos AL INSTANTE tras un reinicio, sin esperar a
            #    que se calienten los ticks en vivo (antes el sub-minuto salía
            #    vacío y 60s buscaba 'tf60' en vez de 'M1' -> "pocos datos").
            clave = "M1" if tf == 60 else f"tf{tf}"
            stored = self.repo.get_recent(asset_code, clave, 300)
            if stored is not None and len(stored) >= 6:
                frames[tf] = stored
                continue
            # 2) Sub-minuto sin guardar: construir desde los ticks recientes.
            if tf < 60:
                cb = CandleBuilder(tf)
                for t, p in suaves:
                    cb.add_tick(p, t * 1000.0)
                frames[tf] = cb.to_dataframe(include_forming=True)
                continue
            # 3) Tiempos largos sin guardar: agregar desde M1; si tampoco, ticks.
            agg = self._aggregate_m1(asset_code, tf)
            if agg is None or len(agg) < 6:
                cb = CandleBuilder(tf)
                for t, p in suaves:
                    cb.add_tick(p, t * 1000.0)
                agg = cb.to_dataframe(include_forming=True)
            frames[tf] = agg

        # RÉGIMEN (Oscillate/Slide) desde un tiempo medio con datos. Se calcula
        # ANTES del análisis para AJUSTAR los pesos de indicadores: en tendencia
        # mandan MACD/medias; en rango mandan los rebotes techo/piso (RSI/Bollinger).
        reg = adxv = None
        comprimido, ancho_rel = False, None
        for tfm in (60, 180, 300):
            fm = frames.get(tfm)
            if fm is not None and len(fm) >= 20:
                reg, adxv = _regime(fm["high"], fm["low"], fm["close"])
                # COMPRESIÓN (squeeze): cuando lateraliza, las bandas se estrechan.
                # La lectura del trader: la entrada vive en el TIEMPO CORTO; el
                # largo solo da el sesgo. Se avisa para no entrar "a ciegas" en
                # un rango que está por romper.
                comprimido, ancho_rel = _compression(fm["close"])
                break

        resultado = analyzer.analyze_frames(frames, regimen=reg)
        resultado["umbral"] = min_conf
        if win_rate is not None:
            resultado["win_rate_hist"] = win_rate
        if reg:
            resultado["regime"] = reg
            resultado["adx"] = round(adxv, 1)
        if comprimido:
            resultado["comprimido"] = True
            resultado["ancho_rel"] = ancho_rel
            aviso = ("🔬 Mercado COMPRIMIDO (rango estrecho, posible RUPTURA): "
                     "la entrada vive en el tiempo CORTO; usa el tiempo largo solo "
                     "como sesgo y espera confirmación de la ruptura.")
            resultado["explicacion"] = aviso + " " + resultado.get("explicacion", "")

        # Pesos aprendidos: mostramos los indicadores que MÁS aciertan en este
        # activo (los que el bot ha "aprendido" a valorar), de la FUENTE activa
        # (señales reales si las hay, si no backtest), para que se vea el
        # aprendizaje continuo en acción.
        if learned_stats:
            top = [(n, s["hit_rate"]) for n, s in learned_stats.items()
                   if s.get("hit_rate") is not None]
            top.sort(key=lambda x: x[1], reverse=True)
            if top:
                resultado["pesos_top"] = top[:3]        # 3 mejores (ind, hit_rate)
        if learned_source:
            resultado["pesos_fuente"] = learned_source   # "real" o "backtest"

        # GRÁFICO: velas del TIEMPO ELEGIDO por el usuario (¡no siempre M1!). Así
        # el gráfico coincide con la temporalidad que se está analizando (si pides
        # M5, ves velas de 5 min). Incluye la vela EN FORMACIÓN para no ir atrás.
        if tf_seconds < 60:
            cbf = CandleBuilder(tf_seconds)
            for t, p in suaves:
                cbf.add_tick(p, t * 1000.0)
            chart_df = cbf.to_dataframe(include_forming=True)
        else:
            chart_df = self._aggregate_m1(asset_code, tf_seconds,
                                          incluir_formacion=True)
            if chart_df is None or len(chart_df) < 5:
                # Sin historial suficiente todavía -> construir desde ticks.
                cbf = CandleBuilder(tf_seconds)
                for t, p in suaves:
                    cbf.add_tick(p, t * 1000.0)
                chart_df = cbf.to_dataframe(include_forming=True)
        if chart_df is not None and len(chart_df) > 45:
            chart_df = chart_df.tail(45).reset_index(drop=True)
        resultado["chart"] = chart_df

        # COBERTURA DE DATOS: cuántas velas M1 lleva acumuladas este activo. Es
        # transparencia: los tiempos largos (15m, 30m) necesitan muchas velas y
        # se van llenando con el uso (el historial se GUARDA entre reinicios).
        try:
            resultado["m1_count"] = self.repo.count(asset_code, "M1")
        except Exception:
            pass

        # VWAP: nivel de referencia (precio "justo") ponderado por actividad.
        # Indica de qué lado del precio justo estamos: por encima = sesgo alcista,
        # por debajo = bajista. Es contexto, no una orden.
        if chart_df is not None and len(chart_df) >= 5:
            vw = vwap_signal(chart_df)
            if vw["vwap"] is not None:
                resultado["vwap"] = vw

            # SOPORTE/RESISTENCIA (techo y piso) para dibujar en el gráfico y
            # avisar si el precio está pegado a un nivel (posible rebote/rechazo).
            lv = detect_levels(chart_df)
            if lv["soportes"] or lv["resistencias"]:
                resultado["levels"] = lv
                # ALERTA DE PROXIMIDAD: si el precio está MUY cerca (<0.05%) de un
                # techo o piso, es zona de rebote/rechazo -> avisamos. Cerca del
                # techo conviene PUT (rechazo); cerca del piso, CALL (rebote).
                precio_actual = float(chart_df["close"].iloc[-1])
                cerca = precio_actual * 0.0005          # 0.05% del precio
                techo = lv["resistencias"][0] if lv["resistencias"] else None
                piso = lv["soportes"][0] if lv["soportes"] else None
                if techo is not None and abs(precio_actual - techo) <= cerca:
                    resultado["nivel_alerta"] = ("techo", round(techo, 6))
                elif piso is not None and abs(precio_actual - piso) <= cerca:
                    resultado["nivel_alerta"] = ("piso", round(piso, 6))

        # PATRONES DE VELA sobre el tiempo más corto (el de la ENTRADA): la FORMA
        # de la vela cuenta lo que los indicadores no ven. Un doji = indecisión
        # (fuerza NO OPERAR); martillo/envolvente = confirmación de dirección.
        # IMPORTANTE: se miran solo velas YA CERRADAS. La vela en formación aún
        # puede cambiar; detectar un patrón sobre ella daría señales prematuras
        # (era la vela "que aún no estaba hecha" que notó el usuario).
        corto = min(frames) if frames else None
        if corto is not None and frames[corto] is not None and len(frames[corto]) >= 3:
            velas_cerradas = frames[corto].iloc[:-1]      # quita la vela en curso
            pat = detect_patterns(velas_cerradas)
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

        # CICLO DE APRENDIZAJE REAL. Se hace al FINAL, tras todas las barreras, así
        # solo registramos lo que el bot de verdad recomendaría:
        #   1) Resolvemos señales pasadas ya vencidas (con el historial acumulado).
        #   2) Si el veredicto final es operable (OPERAR/OPCIONAL) con dirección
        #      clara, registramos esta señal para medir después si acierta.
        now_ms = int((self._last_tick.get(asset_code) or 0) * 1000)
        if now_ms:
            try:
                self.tracker.resolve_pending(now_ms)
            except Exception:
                self.log.exception("No se pudieron resolver señales pendientes")

        dfin = resultado.get("direccion", "")
        lado = (_SIG_CALL if "CALL" in dfin
                else (_SIG_PUT if "PUT" in dfin else None))
        vfin = resultado.get("veredicto", "")
        operable = ("OPERAR" in vfin) or ("OPCIONAL" in vfin)
        if registrar and operable and lado and now_ms and ticks:
            # Anti-duplicado: no registrar dos veces dentro del mismo horizonte
            # (si el usuario pulsa "Analizar de nuevo" varias veces seguidas).
            ultimo = self._last_signal.get(asset_code, 0)
            if now_ms - ultimo >= tf_seconds * 1000:
                entry_price = ticks[-1][1]
                # Votos del tiempo de ENTRADA (el más corto) para poder aprender
                # luego qué indicadores acertaron de verdad.
                por_tiempo = resultado.get("por_tiempo", {})
                votos = None
                if corto is not None and corto in por_tiempo:
                    votos = por_tiempo[corto].get("votes") or None
                try:
                    self.tracker.record(asset_code, self._tf_label(tf_seconds),
                                        lado, entry_price, now_ms, tf_seconds,
                                        votes=votos)
                    self._last_signal[asset_code] = now_ms
                except Exception:
                    self.log.exception("No se pudo registrar la señal")

        # Win-rate REAL del bot (de señales ya resueltas) para mostrarlo.
        try:
            st = self.tracker.stats(asset=asset_code)
            if st["decididas"] >= 5:
                resultado["win_rate_real"] = st["win_rate"]
                resultado["senales_reales"] = st["decididas"]
        except Exception:
            pass

        return resultado, seg, len(ticks)

    async def analyze_sistema(self, asset_code, tf_seconds, sistema, titulo,
                              asset_display):
        """
        Análisis con el SISTEMA DEL TRADER (10 indicadores, 12 tiempos, alineación
        ponderada + ley EMA200-1H + filtros). Reutiliza analyze() SOLO para enfocar
        el activo y traer datos frescos + el timing de entrada (seg); el veredicto
        sale de veredicto_final leyendo el historial de las 12 temporalidades.

        Devuelve (texto, resultado_sistema, seg, n_ticks).
        """
        from bot.sistema_signal import senal_desde_repo, lectura_extra
        # Enfoca el activo y refresca datos. registrar=False: el motor viejo NO
        # guarda su señal; la del SISTEMA se guarda abajo (aprendizaje correcto).
        _old, seg, n = await self.analyze(asset_code, tf_seconds, registrar=False)
        payout = self._payouts.get(asset_code)
        pago_pct = payout if payout is None else float(payout)

        # En el mercado REAL pasamos la hora (para el filtro de sesión). EST ~
        # UTC-5 (sin ajuste fino de horario de verano; se afina luego).
        hora_est = None
        if getattr(sistema, "NOTICIAS_DURANTE", None) is not None:
            from datetime import datetime, timezone
            hora_est = (datetime.now(timezone.utc).hour - 5) % 24

        # LECTURA extra para la tarjeta: hora de entrada (seg) + VWAP/techo/piso/
        # patrones/historial (del análisis clásico _old). Es lo que el trader pidió
        # para poder OPERAR: saber cuándo entrar, con la lectura completa.
        extras = lectura_extra(seg, _old if isinstance(_old, dict) else None)
        texto, res = senal_desde_repo(self.repo, sistema, titulo, asset_code,
                                      asset_display, self._tf_label(tf_seconds),
                                      payout=pago_pct, hora_est=hora_est,
                                      extras=extras)

        # Registrar la señal del SISTEMA cuando dice OPERAR (para medir su
        # win-rate real y calibrar). Anti-duplicado por horizonte.
        if res.get("veredicto") == "OPERAR":
            self._registrar_senal_sistema(asset_code, tf_seconds, res)
        return texto, res, seg, n

    def _registrar_senal_sistema(self, asset_code, tf_seconds, res):
        """Guarda la señal del sistema (dirección de la EMA200 de 1H) en el tracker."""
        from datetime import datetime, timezone
        lado = res.get("direccion_1h")
        if lado not in (_SIG_CALL, _SIG_PUT):
            return
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if now_ms - self._last_signal.get(asset_code, 0) < tf_seconds * 1000:
            return                                # ya registrada en este horizonte
        buf = self._ticks.get(asset_code)
        entry_price = buf[-1][1] if buf else None
        if entry_price is None:
            df = self.repo.get_recent(asset_code, "M1", 1)
            entry_price = (float(df["close"].iloc[-1])
                           if df is not None and len(df) else None)
        if entry_price is None:
            return
        try:
            self.tracker.record(asset_code, self._tf_label(tf_seconds), lado,
                                entry_price, now_ms, tf_seconds)
            self._last_signal[asset_code] = now_ms
        except Exception:
            self.log.exception("No se pudo registrar la señal del sistema")

    def _tf_label(self, tf_seconds):
        """Etiqueta legible de un timeframe en segundos (para guardar la señal)."""
        if tf_seconds < 60:
            return f"{tf_seconds}s"
        if tf_seconds < 3600:
            return f"{tf_seconds // 60}m"
        return f"{tf_seconds // 3600}h"

    def _aggregate_m1(self, asset, tf_seconds, incluir_formacion=False):
        """
        Agrega las velas M1 ACUMULADAS en el historial a un timeframe mayor.
        Cuantas más velas M1 haya guardado el bot, más velas del tiempo largo
        se pueden formar (la "lectura continua"). Devuelve un DataFrame OHLC.

        incluir_formacion=True: añade la vela M1 EN FORMACIÓN (el minuto en curso)
        antes de agregar, para que el gráfico llegue hasta AHORA y no vaya atrás.
        """
        import pandas as pd
        m1 = self.repo.get_recent(asset, "M1", 5000)
        if m1 is None or len(m1) == 0:
            return None
        m1 = m1.copy()
        if incluir_formacion:
            b = self._builders.get(asset)
            f = b.forming_candle() if b is not None else None
            if f is not None:
                last_ts = int(m1["timestamp"].iloc[-1]) if len(m1) else None
                if last_ts is None or int(f["timestamp"]) > last_ts:
                    m1 = pd.concat([m1, pd.DataFrame([f])], ignore_index=True)
        tf_ms = tf_seconds * 1000
        m1["bucket"] = (m1["timestamp"] // tf_ms) * tf_ms
        agg = (m1.groupby("bucket")
               .agg(open=("open", "first"), high=("high", "max"),
                    low=("low", "min"), close=("close", "last"),
                    volume=("volume", "sum"))
               .reset_index()
               .rename(columns={"bucket": "timestamp"})
               .sort_values("timestamp").reset_index(drop=True))
        return agg
