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
from bot.scoring_strategy import regime as _regime
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

    def _on_history(self, payload):
        if not isinstance(payload, dict):
            return
        asset = payload.get("asset")
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
        # Sembramos el buffer/builder en vivo SOLO si aún no hay nada: NO pisamos
        # lo que _on_tick ya acumuló (antes se borraba en cada cambio de activo).
        if period == 60:
            if not self._ticks.get(asset):
                self._ticks[asset] = deque(ticks, maxlen=10000)
            if asset not in self._builders:
                self._builders[asset] = cb

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
            except Exception:
                self.log.exception("Colector integrado: fallo en una ráfaga")
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
        if len(ticks) < 50:
            return ({"veredicto": "🚫 NO OPERAR", "direccion": "⏸️ pocos datos",
                     "fuerza": 0.0, "por_tiempo": {}}, seg, len(ticks))

        # ESCALERA COMPLETA de tiempos (lee toda la línea de tiempo, lo clave es
        # la ALINEACIÓN). OTC incluye sub-minuto; real empieza en 1m. Cubrimos
        # 15s → 30m SIN saltos (incluye 2m y 4m) para un análisis completo.
        is_otc = asset_code.endswith("_otc")
        if is_otc:
            tfs = (15, 30, 60, 120, 180, 240, 300, 600, 900, 1800)  # 15s..30m
        else:
            tfs = (60, 120, 180, 240, 300, 600, 900, 1800)          # 1m..30m
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
            if tf < 60:
                cb = CandleBuilder(tf)
                for t, p in suaves:
                    cb.add_tick(p, t * 1000.0)
                frames[tf] = cb.to_dataframe(include_forming=True)
                continue
            # 1) Velas REALES de PO a ese periodo (si las pedimos y llegaron).
            stored = self.repo.get_recent(asset_code, f"tf{tf}", 300)
            if stored is not None and len(stored) >= 6:
                frames[tf] = stored
                continue
            # 2) Si no, agregamos desde el historial M1 acumulado.
            agg = self._aggregate_m1(asset_code, tf)
            if agg is None or len(agg) < 6:
                # 3) Último recurso: construir desde los ticks recientes.
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
        if operable and lado and now_ms and ticks:
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
