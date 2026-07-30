"""
bot/robot_reversion.py
======================
LANZADOR EN VIVO del robot de reversión (FX real). Une todo:

  Pocket Option (velas M1 en vivo)  ->  VigilanteReversion (detecta el pico)
        ->  tarjeta  ->  Telegram (@FuZionFzbot).

Cómo funciona, en simple:
  - Lee tu sesión de `ssid_real.txt` (perfil REAL) y se conecta a Pocket Option (solo
    lectura, nunca opera).
  - El websocket escucha UN par a la vez, así que ROTA por la lista dejando ~75s a cada
    uno (lo justo para que cierre una vela de 1m). No es simultáneo: es un muestreo.
  - Cada vela M1 que cierra pasa por el vigilante; si hay reversión con ventaja, te
    manda la tarjeta a Telegram. Guarda las velas en `history_real.db` (historial que
    crece con lo que llega en vivo).
  - Respeta el horario real (calla con el mercado cerrado).

Requisitos en la carpeta / entorno:
  - `ssid_real.txt`  (o env POCKET_OPTION_SSID_REAL) — tu sesión de PO.
  - `TELEGRAM_BOT_TOKEN_REAL` en el .env — token de @FuZionFzbot.
  - chat: manda un mensaje al bot una vez (o define TELEGRAM_CHAT_ID_REAL).

Arranque:  python -m bot.robot_reversion REAL
No correr a la vez que INICIAR_REAL.bat si comparten el mismo SSID (PO rechaza doble
conexión). Las partes puras se prueban en bot/test_robot_reversion.py.
"""
import asyncio
import datetime
import logging
import math
import os
import sys
import time

from bot.profiles import get_profile
from bot.pocket_probe import _load_ssid
from bot.pocket_client import PocketOptionClient
from bot.candles import CandleBuilder
from bot.history import HistoryRepository
from bot.market_hours import is_open
from bot.senal_reversion import cargar_tabla
from bot.vigilante_reversion import VigilanteReversion
from bot.signal_log import SignalTracker
from bot.autocorrector import debe_enviar
from bot.news_filter import NewsFilter
from bot.confirmacion_reversion import confirma

# Activos que Pocket Option ofrece en el mercado REAL (según su menú) y que además
# TENEMOS con historial/borde. PO real NO ofrece pares con NZD ni USDJPY; de la lista
# de PO nos faltan AUDCHF y CADCHF (no descargados). Estos 18 son los operables.
ACTIVOS_PO = ("AUDCAD", "AUDUSD", "AUDJPY", "EURCAD", "EURUSD", "EURJPY", "EURCHF",
              "EURGBP", "EURAUD", "USDCAD", "USDCHF", "CHFJPY", "GBPAUD", "GBPJPY",
              "GBPUSD", "GBPCHF", "GBPCAD", "CADJPY")
# Pares con el borde de reversión más fuerte a 3m (de reversion_tabla.json), ya SOLO
# los que Pocket Option ofrece en real (sin NZD). Son los de entradas más seguras; al
# ser ~10 la vuelta es más rápida (~12 min) = más señales que vigilando los 18.
PARES_FUERTES = ("EURCHF", "AUDCAD", "EURGBP", "USDCHF", "GBPCHF", "CHFJPY",
                 "AUDUSD", "EURCAD", "GBPCAD", "AUDJPY")
DWELL_SEG = 75                 # segundos escuchando cada par (>=1 vela M1)
# Tiempos cuyo historial se pide al saltar a cada par (para guardar historial completo).
PERIODOS_HISTORIAL = (120, 180, 300, 600, 900, 1800, 3600)


def _chat_de_updates(updates):
    """Saca el chat_id del último update entrante (para no pedirlo a mano). None si no
    hay ninguno. `updates`: lista de objetos Update de python-telegram-bot."""
    for u in reversed(list(updates or [])):
        chat = getattr(u, "effective_chat", None)
        if chat is not None and getattr(chat, "id", None) is not None:
            return str(chat.id)
        msg = getattr(u, "message", None)
        cid = getattr(getattr(msg, "chat", None), "id", None)
        if cid is not None:
            return str(cid)
    return None


def _es_tardia(ts_sec, inicio_ms, seg, max_atraso):
    """True si el cierre de la vela se detectó demasiado tarde: el tick actual llegó más
    de `max_atraso` seg después de que la vela terminara. Todo en hora del bróker (el
    desfase se cancela al restar). Una vela detectada tarde daría una entrada ya pasada."""
    fin = inicio_ms / 1000.0 + seg
    return (ts_sec - fin) > max_atraso


def _necesita_reinicio(ticks_prev, ticks_now, mercado_abierto):
    """Reinicio si el mercado está abierto pero NO llegó ningún tick en el intervalo
    (el flujo se cortó y la reconexión interna no lo resolvió). Con mercado cerrado el
    silencio es normal: no se reinicia."""
    return bool(mercado_abierto) and ticks_now == ticks_prev


class RobotReversion:
    def __init__(self, profile, pares=None, expiry_min=3, dwell_seg=DWELL_SEG,
                 ssid=None, token=None, chat_id=None, tabla=None, repo=None,
                 is_open_fn=None, demo=True, payout_min=79.0, con_grafico=True,
                 nombre=None, expiries=None, con_noticias=True):
        self.profile = profile
        self.pares = list(pares) if pares else list(PARES_FUERTES)
        self.expiry_min = int(expiry_min)
        # Tiempos que emite: uno o varios (la matriz manda los 4 desde una conexión).
        self.expiries = [int(e) for e in (expiries or [expiry_min])]
        self.nombre = nombre or f"FUZION FX {int(expiry_min)}M"   # nombre del bot
        self.dwell_seg = int(dwell_seg)
        self.demo = demo
        self.payout_min = float(payout_min)      # solo avisa si el activo paga >= esto
        self.con_grafico = bool(con_grafico)     # adjuntar gráfico de velas al aviso
        self._payouts = {}                       # asset -> % de pago en vivo (de PO)
        self.ssid = ssid if ssid is not None else _load_ssid(profile.nombre)
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN_REAL", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID_REAL", "")
        self.repo = repo if repo is not None else HistoryRepository(profile.db_path)
        if tabla is None:
            tabla = cargar_tabla(os.path.join(profile.datasets_dir, "reversion_tabla.json"))
        self.tabla = tabla
        gate = is_open_fn if is_open_fn is not None else (lambda p: is_open(p)[0])
        # UN vigilante POR TIEMPO: cada bot analiza las velas de SU temporalidad (el de
        # 5m mira velas de 5m, el de 3m velas de 3m...), no el mismo pico de 1m repetido.
        # Así los 4 bots son 4 análisis distintos y las señales son raras y propias.
        self.vigilantes = {exp: VigilanteReversion(self.pares, tabla=tabla,
                                                   expiry_min=exp, is_open=gate)
                           for exp in self.expiries}
        self.vig = self.vigilantes[self.expiries[0]]     # compat / precarga base
        # CORRECTOR: registra cada señal y, con los precios que llegan luego, mide su
        # acierto REAL en vivo. Silencia el par+tiempo que baja del punto de equilibrio
        # para no arrastrar el error a las demás señales (ver bot/autocorrector).
        self.tracker = SignalTracker(self.repo)
        self.corrector_min_muestra = 20   # antes de esta muestra se confía en el histórico
        self.corrector_margen = 0.0       # exigencia extra sobre el equilibrio (0.03=+3pts)
        # NOTICIAS: en mercado real, callar el par si una de sus monedas tiene noticia
        # de alto impacto en la ventana (±15 min). El OTC nunca se bloquea (sintético).
        self.con_noticias = bool(con_noticias)
        self.news = NewsFilter()
        # CONFIRMACIÓN: exige que el precio esté estirado de su media (z>=z_min) en el
        # sentido del pico; filtra picos que son arranque de tendencia, no reversión.
        self.con_confirmacion = True
        self.conf_z_min = 1.0
        # WATCHDOG: si deja de llegar el flujo de ticks (con el mercado abierto) se
        # reinicia la conexión sola, sin apagar el bot.
        self.con_watchdog = True
        self.watchdog_seg = 180
        # TIEMPO/FRESCURA: por la rotación, una vela puede detectarse tarde y mandaría
        # una hora de entrada ya pasada. Se descarta si el cierre se detectó > max_atraso
        # seg después de terminar la vela; y si la señal se quedó vieja en la cola.
        self.con_atraso = True
        self.max_atraso_seg = 25                 # detección tardía del cierre -> se descarta
        self.max_cola_seg = 30                   # vieja en cola al enviar -> se descarta
        self._ticks = 0                          # contador de ticks recibidos (latido)
        self._builders = {}
        self._cola = asyncio.Queue()
        self.client = None
        self.bots = {}                   # exp -> Bot de Telegram (uno por tiempo)
        self._bot_primario = None
        self.log = logging.getLogger("robot_reversion")

    def _token_para(self, exp):
        """Token del bot de Telegram de ese tiempo: TELEGRAM_BOT_TOKEN_REAL_<N>M, o el
        base TELEGRAM_BOT_TOKEN_REAL si no hay uno propio (así 1m usa el base)."""
        return (os.getenv(f"TELEGRAM_BOT_TOKEN_REAL_{exp}M")
                or self.token or os.getenv("TELEGRAM_BOT_TOKEN_REAL", ""))

    # --- construcción de velas POR TIEMPO desde ticks ---
    def _builder(self, asset, seg):
        """CandleBuilder por (par, segundos): 60=M1, 120=2m, 180=3m, 300=5m. Cada tiempo
        arma sus PROPIAS velas para que su bot analice su temporalidad."""
        return self._builders.setdefault((asset, seg), CandleBuilder(seg))

    def _add_seguro(self, asset, seg, price, ts):
        try:
            return self._builder(asset, seg).add_tick(price, ts * 1000.0)
        except Exception:
            return None

    def _guardar(self, asset, seg, vela):
        clave = "M1" if seg == 60 else f"tf{seg}"
        try:
            self.repo.record_candle(asset, clave, vela)
        except Exception:
            self.log.exception("No se pudo guardar la vela de %s (%s)", asset, clave)

    def _hora_entrada(self, exp):
        """Inicio de la vela ACTUAL del tiempo, en el RELOJ REAL del usuario: es el
        minuto exacto en que debe poner la operación (la vela que arranca ya). Se ancla
        al reloj real (como el gráfico), no al timestamp del bróker (desfasado)."""
        seg = exp * 60
        inicio = math.floor(datetime.datetime.now().timestamp() / seg) * seg
        return datetime.datetime.fromtimestamp(inicio)

    def _on_tick(self, asset, ts, price):
        """Alimenta las velas de cada tiempo; cuando CIERRA una vela de un tiempo, ese
        bot analiza SU vela y decide su señal. Los 4 bots son 4 análisis distintos (no el
        mismo pico de 1m repetido), por eso las señales son propias y raras."""
        self._ticks += 1                         # latido para el watchdog
        # Vela M1 base SIEMPRE: historial reciente, gráfico 1m y resolución del tracker.
        try:
            m1 = self._builder(asset, 60).add_tick(price, ts * 1000.0)   # ts en ms
        except Exception:
            return
        if m1:
            self._guardar(asset, 60, m1)
            cts_m1 = m1.get("timestamp")
            if cts_m1:
                try:
                    self.tracker.resolve_pending(cts_m1)   # acierto real al día (continuo)
                except Exception:
                    self.log.exception("No se pudieron resolver señales vencidas")

        # Un análisis POR TIEMPO: cada bot con la vela de SU temporalidad.
        for exp in self.expiries:
            seg = exp * 60
            cerrada = m1 if seg == 60 else self._add_seguro(asset, seg, price, ts)
            if not cerrada:
                continue
            if seg != 60:
                self._guardar(asset, seg, cerrada)     # historial del tiempo (gráfico)
            # FRESCURA: si el cierre se detectó tarde (rotación), la entrada ya pasó -> se
            # descarta. Así no llega una hora de entrada en el pasado (desfase de tiempo).
            if self.con_atraso and _es_tardia(ts, cerrada.get("timestamp", 0), seg,
                                              self.max_atraso_seg):
                self.log.info("Señal %sm de %s descartada: cierre detectado tarde.",
                              exp, asset)
                continue
            vig = self.vigilantes[exp]
            if not vig.registrar(asset, cerrada["close"], ts=cerrada.get("timestamp")):
                continue
            # FILTRO DE PAGO
            pago = self._payouts.get(asset)
            if pago is not None and pago < self.payout_min:
                continue
            # FILTRO DE NOTICIAS
            if self.con_noticias and not self.news.can_trade(asset):
                self.log.info("Noticia de alto impacto: %s en silencio.", asset)
                continue
            s = vig.senal_para(asset, exp)
            if not s:
                continue
            # CONFIRMACIÓN por extensión, sobre las velas de ESE tiempo.
            if self.con_confirmacion and not confirma(vig.buffer(asset),
                                                      s["direccion"], self.conf_z_min):
                self.log.info("Sin confirmación (no estirado): %s %sm en silencio.",
                              asset, exp)
                continue
            tf = f"M{exp}"
            cts = cerrada.get("timestamp")
            # SIEMPRE se registra (sombra) para mantener viva la medición del corrector.
            if cts:
                try:
                    self.tracker.record(asset, tf, s["direccion"], cerrada["close"],
                                        cts, exp * 60)
                except Exception:
                    self.log.exception("No se pudo registrar la señal de %s", asset)
            # CORRECTOR: si este par+tiempo viene fallando bajo el equilibrio, se calla
            # (no se envía) pero queda registrado. No afecta a los demás pares/tiempos.
            wr, muestra = self.tracker.win_rate_reciente(asset, tf,
                                                         self.corrector_min_muestra)
            pago_ref = pago if pago else self.payout_min   # si no se conoce, usa el piso
            enviar, motivo = debe_enviar(wr, muestra, pago_ref,
                                         self.corrector_min_muestra, self.corrector_margen)
            if not enviar:
                self.log.info("Silenciado %s %s: %s", asset, tf, motivo)
                continue
            s["payout"] = pago
            s["expiry_min"] = exp
            s["nombre_bot"] = (self.nombre if len(self.expiries) == 1
                               else f"FUZION FX {exp}M")
            s["_mono"] = time.monotonic()          # cuándo se creó (para descartar viejas)
            self._sellar_hora(s, exp)              # hora + tarjeta (se refresca al enviar)
            self._cola.put_nowait(s)

    def _sellar_hora(self, s, exp):
        """Fija la hora de entrada/vencimiento en el RELOJ REAL del usuario y arma la
        tarjeta. Se llama al crear y OTRA VEZ al enviar, para que la hora que ve el
        usuario sea la del momento de recibir (no la de hace minutos)."""
        from bot.escaner_reversion import tarjeta
        from bot.sesiones import etiqueta
        entra = self._hora_entrada(exp)
        vence = entra + datetime.timedelta(minutes=exp)
        s["hora_entrada"] = entra.strftime("%H:%M")
        s["hora_vence"] = vence.strftime("%H:%M")
        # Zona horaria del PC (offset real de ESA fecha: respeta horario de verano).
        off = entra.astimezone().utcoffset()
        mins = int(off.total_seconds() // 60) if off else 0
        signo = "+" if mins >= 0 else "-"
        hh, mm = divmod(abs(mins), 60)
        s["zona_horaria"] = f"UTC{signo}{hh}:{mm:02d}"
        s["sesion_mercado"] = etiqueta(datetime.datetime.utcnow().hour)
        s["tarjeta"] = tarjeta(s)

    def _on_assets(self, assets):
        """Guarda el % de pago (payout) en vivo de cada activo, para el filtro."""
        try:
            from bot.payout import parse_assets
            self._payouts.update(parse_assets(assets))
        except Exception:
            self.log.exception("No se pudo leer el payout")

    def _on_history(self, payload):
        """Guarda el historial que Pocket Option manda al saltar a un par (velas OHLC
        ya hechas o ticks que agregamos), en su tiempo (60->M1, otros->tf<seg>). Así
        `history_real.db` crece completo mientras el robot corre."""
        if not isinstance(payload, dict):
            return
        asset = payload.get("asset")
        if not asset:
            return
        try:
            period = int(payload.get("period", 60) or 60)
        except (TypeError, ValueError):
            period = 60
        key = "M1" if period == 60 else f"tf{period}"
        filas = []
        candles = payload.get("candles") or payload.get("data")
        if candles:
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
        else:
            hist = payload.get("history", [])
            if not hist:
                return
            cb = CandleBuilder(period)
            for row in hist:
                try:
                    t, p = float(row[0]), float(row[1])
                except (IndexError, TypeError, ValueError):
                    continue
                cb.add_tick(p, t * 1000.0)
            filas = cb.closed_candles()
        if filas:
            try:
                self.repo.record_many(asset, key, filas)
            except Exception:
                self.log.exception("No se pudo guardar historial de %s", asset)

    # --- precarga de contexto desde el historial guardado ---
    def _precargar(self):
        # Cada bot carga las velas de SU tiempo (M1/tf120/tf180/tf300), para tener
        # contexto inmediato (incluida la confirmación por extensión) sin esperar.
        for exp in self.expiries:
            seg = exp * 60
            clave = "M1" if seg == 60 else f"tf{seg}"
            vig = self.vigilantes[exp]
            for p in self.pares:
                try:
                    df = self.repo.get_recent(p, clave, 50)
                except Exception:
                    df = None
                if df is not None and len(df):
                    vig.precargar(p, df["close"].astype(float).tolist())

    # --- Telegram ---
    async def _resolver_chat(self):
        if self.chat_id:
            return True
        try:
            ups = await self._bot_primario.get_updates(timeout=5)
            self.chat_id = _chat_de_updates(ups) or ""
        except Exception:
            self.log.exception("No se pudo leer get_updates")
        return bool(self.chat_id)

    def _grafico(self, par, direccion, exp):
        """Genera el PNG del gráfico con las velas de SU tiempo (1m->M1, 2m->tf120,
        3m->tf180, 5m->tf300). Si aún no hay velas de ese tiempo, cae a M1. None si no
        puede."""
        if not self.con_grafico:
            return None
        try:
            import tempfile
            from bot.chart import draw_candles
            clave = "M1" if exp == 1 else f"tf{exp * 60}"
            df = self.repo.get_recent(par, clave, 40)
            etiqueta = f"{exp}m"
            if df is None or len(df) < 10:        # sin velas de ese tiempo -> usa 1m
                df = self.repo.get_recent(par, "M1", 40)
                etiqueta = f"1m (opera {exp}m)"
                if df is None or len(df) < 10:
                    return None
            ruta = os.path.join(tempfile.gettempdir(), f"fuzion_{par}_{exp}.png")
            return draw_candles(df, par, etiqueta, ruta, direccion=direccion)
        except Exception:
            self.log.exception("No se pudo generar el gráfico de %s", par)
            return None

    async def _enviar_loop(self):
        while True:
            s = await self._cola.get()
            exp = s.get("expiry_min")
            # Si la señal se quedó vieja en la cola (rotación/red), se descarta: mejor no
            # mandar una entrada tarde que mandarla con la hora ya pasada.
            if self.max_cola_seg and time.monotonic() - s.get("_mono", 0) > self.max_cola_seg:
                self.log.info("Señal %sm de %s descartada: vieja en cola.", exp, s.get("par"))
                continue
            self._sellar_hora(s, exp)          # refresca la hora al momento de enviar
            bot = self.bots.get(exp) or self._bot_primario   # el bot de ESE tiempo
            foto = self._grafico(s["par"], s.get("direccion", ""), exp)
            try:
                if foto:
                    with open(foto, "rb") as fh:
                        await bot.send_photo(chat_id=self.chat_id, photo=fh,
                                             caption=s["tarjeta"], read_timeout=30,
                                             write_timeout=30, connect_timeout=15)
                else:
                    await bot.send_message(chat_id=self.chat_id, text=s["tarjeta"],
                                           read_timeout=30, write_timeout=30,
                                           connect_timeout=15)
                self.log.info("Señal %sm enviada: %s %s %.1f%%",
                              exp, s["par"], s["direccion"], s.get("probabilidad", 0))
            except Exception:
                self.log.exception("No se pudo enviar a Telegram (bot %sm)", exp)
                try:                              # respaldo: al menos el texto
                    await bot.send_message(chat_id=self.chat_id, text=s["tarjeta"])
                except Exception:
                    self.log.exception("Tampoco se pudo enviar el texto")

    async def _refrescar_noticias(self):
        """Descarga el calendario económico al arrancar y lo refresca cada 30 min. La
        descarga corre en un hilo para no frenar el async; es defensiva (si falla la
        red conserva la caché y no bloquea de más)."""
        while True:
            try:
                n = await asyncio.to_thread(self.news.actualizar)
                self.log.info("Calendario de noticias: %d eventos cargados.", n)
            except Exception:
                self.log.exception("No se pudo refrescar el calendario de noticias")
            await asyncio.sleep(1800)             # media hora

    async def _watchdog(self):
        """Vigila el latido de ticks. Si con el mercado abierto no llega ninguno en la
        ventana, reinicia la conexión sola (backstop de la reconexión interna)."""
        prev = self._ticks
        while True:
            await asyncio.sleep(self.watchdog_seg)
            abierto = (any(self.vig.is_open(p) for p in self.pares)
                       if self.vig.is_open else True)
            if _necesita_reinicio(prev, self._ticks, abierto):
                self.log.warning("Watchdog: sin ticks en %ds con mercado abierto. "
                                 "Reiniciando conexión.", self.watchdog_seg)
                try:
                    self.client.stop()
                except Exception:
                    self.log.exception("No se pudo detener el cliente")
                try:
                    self.client = PocketOptionClient(
                        self.ssid, on_tick=self._on_tick, on_history=self._on_history,
                        on_assets=self._on_assets, demo=self.demo, logger=self.log)
                    asyncio.create_task(
                        self.client.run(asset=self.pares[0], period=60))
                except Exception:
                    self.log.exception("No se pudo reiniciar la conexión")
            prev = self._ticks

    async def _rotar(self):
        i = 0
        while True:
            par = self.pares[i % len(self.pares)]
            try:
                await self.client.set_asset(par, 60)                 # M1 en vivo
                # Pide el historial de los tiempos largos para guardarlo completo;
                # request_history vuelve a 60s al final para seguir con los ticks M1.
                await self.client.request_history(par, PERIODOS_HISTORIAL)
                # Latido: muestra qué escucha y cuánto paga (para ver que está vivo y
                # si el filtro de pago lo está callando).
                pago = self._payouts.get(par)
                pago_txt = f"{pago:.0f}%" if pago is not None else "?"
                self.log.info("Escuchando %s (pago %s)  [%d/%d]",
                              par, pago_txt, (i % len(self.pares)) + 1, len(self.pares))
            except Exception:
                self.log.exception("No se pudo cambiar a %s", par)
            i += 1
            await asyncio.sleep(self.dwell_seg)

    async def arrancar(self):
        """Punto de entrada async: crea un bot por tiempo, conecta a PO, rota y envía."""
        if not self.ssid:
            raise RuntimeError("Falta ssid_real.txt (o POCKET_OPTION_SSID_REAL).")
        from telegram import Bot
        # UN bot de Telegram por cada tiempo (4 bots separados). Cae al base si falta.
        self.bots = {}
        for exp in self.expiries:
            tok = self._token_para(exp)
            if not tok:
                raise RuntimeError(f"Falta el token del bot de {exp}m "
                                   f"(TELEGRAM_BOT_TOKEN_REAL_{exp}M en el .env).")
            b = Bot(tok)
            await b.initialize()
            self.bots[exp] = b
        self._bot_primario = self.bots[self.expiries[0]]
        if not await self._resolver_chat():
            raise RuntimeError("No sé a qué chat enviar. Define TELEGRAM_CHAT_ID_REAL o "
                               "manda /start a tu bot.")
        self._precargar()
        self.client = PocketOptionClient(self.ssid, on_tick=self._on_tick,
                                         on_history=self._on_history,
                                         on_assets=self._on_assets,
                                         demo=self.demo, logger=self.log)
        # Aviso de arranque por CADA bot (ves activarse cada uno en su chat).
        for exp, b in self.bots.items():
            try:
                await b.send_message(
                    chat_id=self.chat_id,
                    text=f"FUZION FX {exp}M activo. Vigilando {len(self.pares)} pares. "
                         f"Aviso cuando haya reversión con ventaja a {exp} min.")
            except Exception:
                self.log.exception("No se pudo avisar arranque del bot %sm", exp)
        tarea_cli = asyncio.create_task(self.client.run(asset=self.pares[0], period=60))
        tareas = [self._rotar(), self._enviar_loop(), tarea_cli]
        if self.con_noticias:
            tareas.append(self._refrescar_noticias())
        if self.con_watchdog:
            tareas.append(self._watchdog())
        try:
            await asyncio.gather(*tareas)
        finally:
            self.client.stop()
            for b in self.bots.values():
                try:
                    await b.shutdown()
                except Exception:
                    pass


def main(argv):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    # Cargar el .env (token de Telegram, etc.) igual que hace telegram_signals.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    nombre = (argv[0] if argv else "REAL").upper()
    profile = get_profile(nombre)
    # Argumentos tras el perfil: pares (o TODOS), y opciones --exp N (vencimiento en
    # minutos: 1/2/3/5) y --pago N (payout mínimo, p.ej. 79).
    resto = argv[1:]
    expiry, payout_min, pares, nombre = 3, 72.0, [], None   # pago mínimo 72% por defecto
    tiempos = None                               # varios vencimientos (la matriz)
    i = 0
    while i < len(resto):
        a = resto[i]
        if a in ("--exp", "-e") and i + 1 < len(resto):
            expiry = int(resto[i + 1]); i += 2; continue
        if a in ("--tiempos", "-t") and i + 1 < len(resto):
            tiempos = [int(x) for x in resto[i + 1].replace(" ", "").split(",") if x]
            i += 2; continue
        if a in ("--pago", "--payout") and i + 1 < len(resto):
            payout_min = float(resto[i + 1]); i += 2; continue
        if a in ("--nombre", "-n") and i + 1 < len(resto):
            nombre = resto[i + 1]; i += 2; continue
        pares.append(a.upper()); i += 1
    if pares and pares[0] in ("TODOS", "ALL"):
        pares = list(ACTIVOS_PO)         # 'TODOS' = los 18 de Pocket Option
    elif not pares:
        pares = list(PARES_FUERTES)      # sin lista = los ~10 de mejor borde (seguros)
    else:
        # Descarta lo que Pocket Option no ofrece / no tenemos, y avisa.
        fuera = [p for p in pares if p not in ACTIVOS_PO]
        if fuera:
            print(f"Aviso: no operables (PO no los da o sin historial), fuera: "
                  f"{', '.join(fuera)}")
        pares = [p for p in pares if p in ACTIVOS_PO]
    demo = os.getenv("POCKET_DEMO_REAL", "1") not in ("0", "false", "False")
    robot = RobotReversion(profile, pares=pares or None, expiry_min=expiry,
                           payout_min=payout_min, demo=demo, nombre=nombre,
                           expiries=tiempos)
    ciclo = robot.dwell_seg * len(robot.pares)
    tiempos_txt = "/".join(f"{e}m" for e in robot.expiries)
    print(f"{robot.nombre} · perfil {profile.nombre} · {len(robot.pares)} pares · "
          f"tiempos {tiempos_txt} · pago min {payout_min:.0f}% · demo={demo} · "
          f"vuelta ~{ciclo//60} min")
    try:
        asyncio.run(robot.arrancar())
    except KeyboardInterrupt:
        print("\nDetenido.")
    except RuntimeError as e:
        print(f"\nNo pudo arrancar: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
