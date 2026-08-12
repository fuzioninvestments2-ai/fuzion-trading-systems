"""
bots/base_bot.py (fuzion_fx)
============================
Clase base con el LOOP principal de un bot. Cada uno de los 4 procesos crea un
BaseBot con su bot_id (f1_m1, ...) y llama run(). Cablea todas las piezas:

    config -> (store, risk, signal_engine, learning, notifier, price_feed)

Flujo por par: velas -> senal (confirmaciones) -> filtros de riesgo -> filtro de
aprendizaje (descarta setups que fallan) -> limite por hora -> tarjeta a Telegram.

`scan_once()` hace UNA pasada (testeable sin dormir ni red). `run()` la repite
cada `timeframe_seconds`. Sin feed real, el price_feed placeholder devuelve None
y no se emite (seguro).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from core.config import get_bot_config, load_config, ROOT
from core.results_store import ResultsStore
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine, NEUTRAL
from core.multi_timeframe import MultiTimeframeAnalyzer, TF_SEGUNDOS
from core.learning_engine import LearningEngine
from core import news_guard
from core import control
from core import afiliados
from data.price_feed import PriceFeed, StubPriceFeed, CandleStoreFeed
from telegram.notifier import TelegramNotifier
from telegram.signal_formatter import SignalCardFormatter
from telegram.chart import render_candles
from indicators.pips import pip_size

# Base de velas COMPARTIDA que escribe el colector; los bots leen de aca.
PO_CANDLES_DB = os.path.join(ROOT, "data", "db", "po_candles.db")
# Calendario de noticias (bloqueo por evento de alto impacto). Editable en caliente.
NEWS_PATH = os.path.join(ROOT, "config", "news.json")


class BaseBot:
    def __init__(self, bot_id: str, price_feed: Optional[PriceFeed] = None,
                 notifier: Optional[TelegramNotifier] = None,
                 store: Optional[ResultsStore] = None) -> None:
        cfg = get_bot_config(bot_id)
        self.id = bot_id
        self.name = cfg["name"]
        self.pairs = cfg["pairs"]
        self.timeframe = cfg["timeframe"]
        self.timeframe_seconds = int(cfg["timeframe_seconds"])
        self.card_label = cfg["card_label"]
        self.max_signals_per_hour = int(cfg["signal"].get("max_signals_per_hour", 10))
        # Mercado operado (otc/real): el colector se suscribe a ese activo y la
        # tarjeta lo muestra, para que el usuario opere el MISMO (OTC != real: son
        # series de precio distintas). Se lee del top-level 'market' del yaml.
        try:
            self.mercado = str(load_config().get("market", "otc")).lower()
        except Exception:
            self.mercado = "otc"

        # store inyectable (tests usan ':memory:'); por defecto, la sqlite del bot.
        self.store = store or ResultsStore(cfg["db_path"])
        self.risk = RiskManager(cfg["risk"])
        self.engine = SignalEngine(cfg["indicators"], cfg["signal"])
        # LA FOTO COMPLETA: analizador de convergencia multi-temporalidad. El motor
        # de una sola tf da el disparo de ENTRADA; la convergencia confirma que TODA
        # la foto (corto/medio/largo) apoya la direccion. Solo se aplica como filtro
        # cuando hay datos de al menos `min_tf_convergencia` temporalidades (si no,
        # cae al motor de una tf: no bloquea al arranque cuando aun no hay historia).
        self.mtf = MultiTimeframeAnalyzer(cfg["indicators"])
        self.min_tf_convergencia = int(cfg.get("min_tf_convergencia", 3))
        self.learning = LearningEngine(self.store, cfg["learning"])
        # Feed real por defecto: lee po_candles.db del colector. Si el colector
        # no arranco (archivo inexistente), CandleStoreFeed devuelve None y el
        # bot simplemente no emite (seguro).
        self.feed = price_feed or CandleStoreFeed(PO_CANDLES_DB)

        # Notifier: cada bot manda por SU token (telegram_token del bot) para que
        # cada tiempo llegue a su propio bot de Telegram; si el bot no define uno,
        # cae al token comun (telegram.bot_token). Mismo canal/chat para todos.
        tg = cfg.get("telegram", {})
        token = cfg.get("telegram_token") or tg.get("bot_token")
        canal = tg.get("channel_id")
        if notifier is not None:
            self.notifier = notifier
        elif token and canal:
            self.notifier = TelegramNotifier(token, canal)
        else:
            self.notifier = None

        # Formateador unico de tarjetas (senal y resultado): el bot no duplica
        # el formato, solo provee los datos ya calculados (Regla 1).
        self.formatter = SignalCardFormatter()

        self._emitted_ts: List[float] = []     # timestamps de emisiones (rate limit)
        # Anti-duplicado (re-armado): ultima direccion avisada por par y CUANDO se
        # aviso. En direccion opuesta se avisa al toque; en la misma direccion se
        # re-avisa solo cuando la senal anterior ya vencio (paso un ciclo del
        # timeframe). Asi una tendencia con varias CALL validas no se silencia.
        self._last_dir: Dict[str, str] = {}
        self._last_emit_ts: Dict[str, float] = {}
        self.payout_pct = 85                   # fallback de DISPLAY si no hay pago real
        # Filtro de pago real: el usuario exige emitir solo en activos con pago
        # >= min_pct (72%). require: si el colector aun no recibio el pago del par,
        # NO emitir (mejor callar que a ciegas). El pago real lo provee el feed
        # (lo guarda el colector desde updateAssets de PO).
        pf = cfg.get("payout", {}) or {}
        self.payout_min = float(pf.get("min_pct", 72))
        self.payout_max = float(pf.get("max_pct", 100))
        self.payout_require = bool(pf.get("require", True))
        # Margen para resolver contra el OHLC real: si al vencer aun no llego la
        # vela real de PO (el colector rota 22 pares), se ESPERA hasta este margen
        # antes de declarar la senal NULA. Evita nulificar de mas por demora del
        # colector, sin inventar un resultado. Configurable por bot.
        self.null_grace_seconds = int(cfg.get("null_grace_seconds", 600))

        # Sistema de Checkpoint Cuantico:
        # - prefilter: recalcula 10s despues; emite SOLO si coincide (menos falsas).
        # - checkpoint: X seg antes del cierre revisa si la direccion se dio vuelta;
        #   si cambio, manda una ALERTA de autocorreccion (informa, no opera).
        self.checkpoint_offset = int(cfg.get("checkpoint_offset", 20))
        self.prefilter_seconds = 10
        self._schedule_enabled = True          # los tests lo apagan
        self._timers: List[threading.Timer] = []
        self._running = False
        self.log = self._setup_logger(cfg.get("log_level", "INFO"))

    def _setup_logger(self, level: str) -> logging.Logger:
        logger = logging.getLogger(f"bot.{self.id}")
        logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
        if not logger.handlers:
            logs_dir = os.path.join(ROOT, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            # UTF-8 en el archivo: las tarjetas llevan emojis (⬆️/⬇️) que en
            # Windows (consola cp1252) romperian el log. Con utf-8 no falla.
            fh = logging.FileHandler(os.path.join(logs_dir, f"{self.id}.log"),
                                     encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
            # Consola: se intenta reconfigurar a utf-8; si no se puede, se
            # reemplazan los caracteres no imprimibles en vez de crashear.
            sh = logging.StreamHandler()
            try:
                sh.stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        return logger

    # ------------------------------------------------------------- rate limit
    def _rate_ok(self, now: float) -> bool:
        """True si no se supero el tope de senales/hora. Purga las viejas."""
        limite = now - 3600.0
        self._emitted_ts = [t for t in self._emitted_ts if t >= limite]
        return len(self._emitted_ts) < self.max_signals_per_hour

    # ------------------------------------------------------------- filtro de pago
    def _payout_de(self, pair: str) -> Optional[float]:
        """Pago real (%) del par segun el feed (colector). None si no hay dato."""
        getter = getattr(self.feed, "get_payout", None)
        if getter is None:
            return None
        try:
            return getter(pair)
        except Exception:
            return None

    def _pago_ok(self, payout: Optional[float]) -> bool:
        """
        True si se puede emitir por pago. Sin dato: depende de payout_require
        (True -> no emitir a ciegas). Con dato: dentro de [min, max].
        """
        if payout is None:
            return not self.payout_require
        return self.payout_min <= payout <= self.payout_max

    # ------------------------------------------------------------- foto completa
    def convergencia(self, pair: str) -> Optional[Dict[str, Any]]:
        """
        Lee las velas de TODAS las temporalidades disponibles (5s..1h) del par y
        devuelve el veredicto de convergencia (o None si el feed no las tiene). Es
        la "foto completa": el conjunto de tiempos, no una sola tf.
        """
        velas: Dict[int, Any] = {}
        for tf in TF_SEGUNDOS.values():
            try:
                c = self.feed.get_candles(pair, tf)
            except Exception:
                c = None
            if c and len(c.get("close", [])) >= 2:
                velas[tf] = c
        if not velas:
            return None
        return self.mtf.analizar(velas)

    # ------------------------------------------------------------- tarjeta rica
    def build_card(self, pair: str, result: Dict[str, Any],
                   payout: Optional[float] = None,
                   entry_ts: Optional[int] = None,
                   confluencia: str = "") -> str:
        """
        Arma el dict de datos POR PAR y delega el formato en SignalCardFormatter.
        El bot solo calcula (tiempos, ATR en pips, acierto por par); el formato
        (estrella, colores, mercado, disclaimer) vive en el formatter (Regla 1).
        Los tiempos van en hora LOCAL de la PC.

        entry_ts: borde de vela de entrada (epoch seg) YA calculado al emitir. Es
        el MISMO que se guarda y se liquida, para que la hora anunciada y la vela
        operada sean identicas. Si no se pasa, se calcula aca (compatibilidad).
        """
        from datetime import datetime, timezone

        ahora = datetime.now().astimezone()          # local, con tz
        off = ahora.utcoffset()
        horas_off = int(off.total_seconds() // 3600) if off else 0
        # Entrada = borde de vela ya fijado al emitir; vence = entrada + timeframe.
        seg = self.timeframe_seconds
        if entry_ts is None:
            epoch = int(ahora.timestamp())
            entry_ts = epoch - (epoch % seg) + seg
        entry_ts = int(entry_ts)
        entrada = datetime.fromtimestamp(entry_ts).astimezone()
        vence = datetime.fromtimestamp(entry_ts + seg).astimezone()

        # ATR en pips (volatilidad reciente real).
        ps = pip_size(pair)
        atr_pips = round(result["atr"] / ps, 1) if ps else 0.0

        # Acierto reciente POR PAR (win_rate(pair)): acumulado del par, no por
        # setup. Sin muestra -> acierto_pct None para que el formatter muestre
        # "sin muestra aún".
        wr = self.store.win_rate(pair)
        acierto_pct = wr["win_pct"] if wr["trades"] > 0 else None

        # card_label de bots.yaml; si no hubiera, cae al nombre del bot.
        etiqueta = self.card_label or self.name

        d = {
            "bot_name": self.name,
            "card_label": etiqueta,
            "par": pair,
            "es_otc": self.mercado == "otc",     # muestra "OTC" -> operar el activo correcto
            "direccion": result["signal"],
            "hora_entrada": entrada.strftime("%H:%M"),
            "hora_vencimiento": vence.strftime("%H:%M"),
            "tz_offset": horas_off,
            # utc_hour: el formatter deriva el mercado (Asia/Europe/America).
            "utc_hour": datetime.now(timezone.utc).hour,
            # Pago REAL del activo (lo que paga PO ahora); si no hay dato, el
            # fallback de display. El filtro ya garantizo que es >= min_pct.
            "payout": int(round(payout)) if payout is not None else self.payout_pct,
            "confirmaciones": result["confirming"],
            "acierto_pct": acierto_pct,
            "n_muestras": wr["trades"],
            "atr": atr_pips,
            "confluencia": confluencia,        # foto completa (multi-temporalidad)
        }
        return self.formatter.format_signal(d)

    # ------------------------------------------------------------- una pasada
    def scan_once(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Una pasada por todos los pares. Devuelve la lista de senales emitidas.
        No duerme ni exige red (con feed en memoria se testea entero).
        """
        now = time.time() if now is None else now
        emitidas: List[Dict[str, Any]] = []
        # PAUSA global (boton del panel): si esta pausado, no se emite nada. No
        # mata el proceso (el vigilante no pelea); solo silencia hasta reanudar.
        if control.esta_pausado():
            return emitidas
        # Noticias: se releen cada pasada (el archivo se puede editar en caliente).
        eventos = news_guard.cargar_eventos(NEWS_PATH)

        for pair in self.pairs:
            if not self._rate_ok(now):
                self.log.info("Tope de %d senales/hora alcanzado; se corta la pasada",
                              self.max_signals_per_hour)
                break

            candles = self.feed.get_candles(pair, self.timeframe_seconds)
            if not candles or len(candles.get("close", [])) < 2:
                continue

            result = self.engine.analyze(candles)
            if result["signal"] == NEUTRAL:
                # Sin senal: se resetea el par para que una nueva CALL/PUT avise.
                self._last_dir[pair] = None
                continue

            # ANTI-DUPLICADO (re-armado): direccion OPUESTA -> avisa al toque;
            # MISMA direccion -> re-avisa solo si la senal anterior YA vencio (paso
            # un ciclo del timeframe). Evita repetir la misma senal dentro del
            # mismo minuto, pero no se pierde una tendencia con varias CALL seguidas.
            if self._last_dir.get(pair) == result["signal"]:
                if now - self._last_emit_ts.get(pair, 0.0) < self.timeframe_seconds:
                    continue

            # BLOQUEO POR NOTICIAS: en la ventana de una noticia de alto impacto no
            # se opera (precio erratico, spread alto). Ventana = news_buffer_minutes.
            bloqueo, evento = news_guard.en_bloqueo(
                now, eventos, self.risk.news_buffer_minutes, pair)
            if bloqueo:
                self.log.info("Noticia bloquea %s: %s (±%d min)", pair,
                              evento["titulo"], self.risk.news_buffer_minutes)
                continue

            # FILTRO DE PAGO: solo emitir si el activo paga >= min_pct (72%). Es
            # exigencia del usuario: un pago bajo destruye la ventaja aunque el
            # acierto sea bueno (break-even sube). Sin dato de pago -> no emitir.
            pago = self._payout_de(pair)
            if not self._pago_ok(pago):
                self.log.debug("Pago fuera de rango en %s: %s (min %s)",
                               pair, pago, self.payout_min)
                continue

            ok, motivo = self.risk.can_trade(pair)
            if not ok:
                self.log.debug("Riesgo bloquea %s: %s", pair, motivo)
                continue

            if not self.learning.should_emit(result["setup_id"]):
                self.log.debug("Aprendizaje descarta setup %s", result["setup_id"])
                continue

            # PRE-FILTRO: recalcular tras `prefilter_seconds`; emitir SOLO si la
            # direccion se mantiene (descarta setups que se dan vuelta al toque).
            confirmado = self._prefiltro(pair, result["signal"])
            if confirmado is None or confirmado["signal"] != result["signal"]:
                self.log.info("Pre-filtro descarta %s %s (cambio en %ds)",
                              pair, result["signal"], self.prefilter_seconds)
                continue
            result = confirmado                # usar la lectura fresca confirmada

            # FOTO COMPLETA (convergencia multi-temporalidad): el disparo de esta tf
            # solo vale si el CONJUNTO de tiempos (corto/medio/largo) apoya la misma
            # direccion. Solo se aplica si hay datos de >= min_tf_convergencia
            # temporalidades; si no, cae al motor de una tf (no bloquea al arranque).
            conv = self.convergencia(pair)
            conv_detalle = ""
            if conv is not None and conv["total"] >= self.min_tf_convergencia:
                if conv["signal"] != result["signal"]:
                    self.log.info("Foto completa NO confirma %s %s (conv=%s, %s) "
                                  "-> no emito", pair, result["signal"],
                                  conv["signal"], conv["detalle"])
                    continue
                conv_detalle = (f"{conv['alineadas']}/{conv['total']} tiempos "
                                f"({conv['detalle']}) conv {conv['convergencia']:.0%}")

            # Borde de entrada = proximo borde de vela DESDE EL INSTANTE DE EMISION
            # (tras el pre-filtro de 10s, que es cuando el humano recibe la tarjeta y
            # entra). Se calcula UNA sola vez, se guarda y lo usan TANTO la tarjeta
            # como la liquidacion -> operan EXACTAMENTE la misma vela. Antes la
            # tarjeta lo derivaba de datetime.now() y resolve_pending lo recalculaba
            # desde ts (inicio del escaneo, ~10s+ antes): si un borde caia en el
            # medio, anunciaba una vela y liquidaba otra (horarios y win/loss
            # cruzados, justo lo que se veia mal).
            emitido = time.time()
            tf = self.timeframe_seconds
            entry_border = int(emitido) - (int(emitido) % tf) + tf

            # Emitir: persistir + notificar (tarjeta + grafico) + contadores.
            rec = {"ts": int(emitido), "pair": pair, "timeframe": self.timeframe,
                   "direction": result["signal"], "setup_id": result["setup_id"],
                   "confirmations": result["confirmations"],
                   "price": result["price"], "atr": result["atr"],
                   "entry_ts": entry_border}
            sid = self.store.save_signal(rec)
            rec["id"] = sid
            card = self.build_card(pair, result, payout=pago, entry_ts=entry_border,
                                   confluencia=conv_detalle)
            if self.notifier:
                # Grafico coordinado con la senal (velas frescas + direccion + entrada).
                img = None
                try:
                    velas_grafico = self.feed.get_candles(pair, self.timeframe_seconds) or candles
                    img = render_candles(
                        velas_grafico, f"{self.name} · {pair} · {self.card_label}",
                        result["signal"], entry_price=result["price"])
                except Exception:
                    img = None
                # 1) Al DUENO: respeta su toggle de Telegram por temporalidad.
                if control.telegram_activo(self.id):
                    self.notifier.send(card, photo_buffer=img)
                # 2) A los AFILIADOS activos suscriptos a esta temporalidad. En bytes
                #    (no BytesIO) para reenviar la misma foto a muchos sin consumirla.
                img_bytes = img.getvalue() if img is not None else None
                for a in afiliados.destinatarios_para(self.id):
                    try:
                        self.notifier.enviar_a(a["chat_id"], card, photo=img_bytes)
                    except Exception:
                        self.log.warning("No se pudo enviar a afiliado %s",
                                         a.get("nombre"))
            else:
                self.log.info("[DRY-RUN sin token] %s", card.replace("\n", " | "))

            self._last_dir[pair] = result["signal"]
            self._last_emit_ts[pair] = now         # para el re-armado por vencimiento
            self._emitted_ts.append(now)
            emitidas.append(rec)
            self.log.info("Senal emitida: %s %s (setup %s)", pair,
                          result["signal"], result["setup_id"])

            # CHECKPOINT: agendar revision X seg antes del CIERRE de la vela operada
            # (entry_border..entry_border+tf), la misma que se liquida.
            expiry = entry_border + tf
            self._schedule_checkpoint(pair, result["signal"], expiry, result, emitido)

        return emitidas

    # ---------------------------------------------- Checkpoint Cuantico
    def _prefiltro(self, pair: str, direccion: str) -> Optional[Dict[str, Any]]:
        """
        Espera `prefilter_seconds` y recalcula con datos frescos. Devuelve el
        nuevo `analyze` (para reusarlo) o None si no hay datos. El caller compara
        la direccion: si cambio, no emite.
        """
        if self.prefilter_seconds > 0:
            time.sleep(self.prefilter_seconds)
        candles = self.feed.get_candles(pair, self.timeframe_seconds)
        if not candles or len(candles.get("close", [])) < 2:
            return None
        return self.engine.analyze(candles)

    def _schedule_checkpoint(self, pair: str, direccion: str, expiry_ts: int,
                             orig: Dict[str, Any], ts_emitida: float) -> None:
        """Agenda el checkpoint en expiry - checkpoint_offset (timer en background)."""
        if not self._schedule_enabled:
            return
        delay = expiry_ts - self.checkpoint_offset - time.time()
        if delay <= 0:
            return                             # ya no da tiempo; se omite
        t = threading.Timer(delay, self._run_checkpoint,
                            args=(pair, direccion, orig, ts_emitida))
        t.daemon = True
        t.start()
        self._timers.append(t)

    def _run_checkpoint(self, pair: str, direccion_orig: str,
                        orig: Dict[str, Any], ts_emitida: float) -> Optional[str]:
        """
        Recalcula con los datos mas frescos. Si la direccion se dio vuelta, manda
        una ALERTA de autocorreccion. Devuelve el texto de la alerta (o None).
        """
        candles = self.feed.get_candles(pair, self.timeframe_seconds)
        if not candles or len(candles.get("close", [])) < 2:
            return None
        nuevo = self.engine.analyze(candles)
        nueva_dir = nuevo["signal"]
        # Misma direccion (o sin senal) -> no se hace nada.
        if nueva_dir == NEUTRAL or nueva_dir == direccion_orig:
            return None

        segs = int(time.time() - ts_emitida)
        cambios = self._describir_cambios(orig, nuevo)
        alerta = (f"*AUTOCORRECCION* · {self.name}\n"
                  f"Par: *{pair}*\n"
                  f"Señal original: *{direccion_orig}*  →  detectado ahora: *{nueva_dir}*\n"
                  f"Emitida hace {segs}s\n"
                  f"Cambios: {cambios}\n"
                  f"_Alerta informativa. El bot no opera por vos._")
        if self.notifier and control.telegram_activo(self.id):
            self.notifier.send_alert(alerta)
        else:
            self.log.info("[DRY-RUN alerta] %s", alerta.replace("\n", " | "))
        return alerta

    @staticmethod
    def _describir_cambios(orig: Dict[str, Any], nuevo: Dict[str, Any]) -> str:
        """Describe que indicadores se movieron (ej: 'RSI cruzo de 65 a 35')."""
        partes = []
        o = orig.get("readings", {})
        n = nuevo.get("readings", {})
        if "rsi" in o and "rsi" in n and abs(o["rsi"] - n["rsi"]) >= 5:
            partes.append(f"RSI cruzó de {o['rsi']:.0f} a {n['rsi']:.0f}")
        # Votos de indicadores que cambiaron de signo.
        ov, nv = orig.get("votes", {}), nuevo.get("votes", {})
        for k in ov:
            if ov[k] != nv.get(k):
                partes.append(f"{k} se dio vuelta")
        return "; ".join(partes) or "el balance de indicadores se invirtió"

    # ------------------------------------------------- feedback loop (aprendizaje)
    PAYOUT_ASUMIDO = 0.80          # payout tipico para el PnL sintetico de aprendizaje

    def resolve_pending(self, now: Optional[float] = None) -> int:
        """
        Cierra el loop de aprendizaje: para cada senal vencida, la liquida sobre LA
        MISMA vela que opera el humano y decide win/loss. Actualiza el store (que
        alimenta al LearningEngine) y el riesgo. Devuelve cuantas resolvio con
        resultado REAL (las nulas no cuentan).

        HONESTIDAD (Pasos 3 y 4): la tarjeta le dice al humano que ENTRE en el
        proximo borde de vela y venza un timeframe despues. Entonces la operacion
        real es UNA vela: la del borde. Se puntua sobre ESA vela real de PO
        (open=precio de entrada en el borde, close=precio al vencimiento), NO desde
        el instante en que el bot detecto (eso adelantaba el resultado y daba un
        win-rate irreal). Si no hay vela real de esa operacion, se ESPERA hasta
        `null_grace_seconds`; pasado el margen, NULA (no se interpola, no se
        inventa, no se gana por defecto). Las nulas se ignoran en win-rate y
        aprendizaje; quedan registradas para auditoria.

        PnL SINTETICO (senal, no dinero real del usuario): +stake*payout si acierta,
        -stake si falla; sirve para que el bot mida su propio rendimiento y aprenda.
        """
        now = time.time() if now is None else now
        tf = self.timeframe_seconds
        # Resolucion SOLO contra el OHLC real de la vela operada: si el feed no lo
        # expone, no se resuelve (mejor no resolver que resolver sobre datos malos).
        real_candle_at = getattr(self.feed, "real_candle_at", None)
        if real_candle_at is None:
            return 0
        cutoff = now - tf
        n = 0
        nulas = 0
        for s in self.store.pending_older_than(int(cutoff)):
            ts = int(s["ts"])
            # Borde de entrada = el que se FIJO y guardo al emitir (entry_ts): la
            # tarjeta anuncio ESE borde y la vela operada abre ahi y vence en
            # borde+tf. Se liquida contra la MISMA vela que vio el humano. Fallback
            # legado (senales viejas sin entry_ts): recalcular desde ts.
            entry_border = s.get("entry_ts")
            entry_border = int(entry_border) if entry_border is not None else (
                ts - (ts % tf) + tf)
            expiry = entry_border + tf
            vela = real_candle_at(s["pair"], tf, entry_border)
            if vela is None:
                # Sin vela real de la operacion: esperar dentro del margen; pasado
                # el margen, NULA (no se inventa un cierre).
                if now - expiry < self.null_grace_seconds:
                    continue
                self.store.resolve_signal(s["id"], "NULL", 0.0)
                nulas += 1
                self.log.info("Senal NULA %s %s: sin vela real de la operacion "
                              "(borde %d, +%ds). No cuenta en win-rate ni aprendizaje.",
                              s["pair"], s["direction"], entry_border,
                              int(now - expiry))
                continue
            entry, exit_price = vela                 # open (borde) y close (vencimiento)
            if exit_price == entry:
                result, won = "tie", False
            elif s["direction"] == "CALL":
                won = exit_price > entry
                result = "win" if won else "loss"
            else:                                    # PUT
                won = exit_price < entry
                result = "win" if won else "loss"

            stake = self.risk.position_size()
            pnl = round(stake * self.PAYOUT_ASUMIDO, 2) if won else (
                0.0 if result == "tie" else -stake)
            self.store.resolve_signal(s["id"], result, pnl)
            if result != "tie":
                self.risk.register_result(s["pair"], pnl, won)

            # RESULTADO a Telegram: cuando vence la senal, avisa WIN/LOSS. En una
            # perdida, en vez de doblar (martingala, prohibido y peligroso), el par
            # entra en RECUPERACION: la proxima senal sera mas estricta y menor.
            self._notificar_resultado(s, entry, exit_price, result)
            n += 1
        if n or nulas:
            self.log.info("Resueltas %d senales reales, %d nulas (sin dato real)",
                          n, nulas)
        return n

    def _notificar_resultado(self, s: Dict[str, Any], entry: float,
                             exit_price: float, result: str) -> None:
        """Manda la tarjeta de RESULTADO (WIN/LOSS/EMPATE) al Telegram del bot.

        El par va CON barra en la tarjeta de resultado (GBP/AUD). La nota de
        recuperacion se agrega SOLO en perdida y si el RiskManager marca al par
        en recuperacion (in_recovery); nunca en WIN. En vez de doblar (martingala,
        prohibido), la proxima senal del par sera mas estricta y de menor tamano.
        """
        pair = s["pair"]
        modo_recuperacion = (result == "loss" and self.risk.in_recovery(pair))
        d = {
            "bot_name": self.name,
            "card_label": self.card_label or self.name,
            "par": pair,                       # con barra (GBP/AUD)
            "es_otc": self.mercado == "otc",
            "direccion": s["direction"],
            "resultado": result,
            "entrada": entry,
            "cierre": exit_price,
            "modo_recuperacion": modo_recuperacion,
        }
        txt = self.formatter.format_result(d)
        if self.notifier and control.telegram_activo(self.id):
            self.notifier.send_text(txt)
        else:
            self.log.info("[DRY-RUN resultado] %s", txt.replace("\n", " | "))

    # ------------------------------------------------- salud / latido (visibilidad)
    def estado_operativo(self, now: Optional[float] = None) -> Dict[str, Any]:
        """
        Radiografia RAPIDA de por que emite o no AHORA: cuantos pares tienen velas
        para analizar y cuantos tienen pago dentro de la banda. Es lo que necesita
        el usuario para saber si el freno es el colector (sin velas), el pago (0 en
        banda) o el motor (hay datos y pago pero no hubo setup). Solo lee.
        """
        now = time.time() if now is None else now
        con_datos = 0
        en_banda: List = []
        con_pago: List = []                          # TODOS los pagos capturados
        for pair in self.pairs:
            try:
                c = self.feed.get_candles(pair, self.timeframe_seconds)
                if c and len(c.get("close", [])) >= 2:
                    con_datos += 1
                p = self._payout_de(pair)
                if p is not None:
                    con_pago.append((pair, p))
                    if self.payout_min <= p <= self.payout_max:
                        en_banda.append((pair, p))
            except Exception:
                continue
        emitidas_hora = len([t for t in self._emitted_ts if t >= now - 3600.0])
        # top: mejores pagos capturados (en la banda o no) -> revela si el mercado
        # paga poco (real de madrugada) o si directamente no se capturo pago.
        top = sorted(con_pago, key=lambda x: -x[1])[:6]
        return {"pares": len(self.pairs), "con_datos": con_datos,
                "en_banda": en_banda, "con_pago": len(con_pago), "top": top,
                "emitidas_hora": emitidas_hora}

    def _tarjeta_salud(self, prefijo: str, now: Optional[float] = None) -> str:
        """Tarjeta de estado para Telegram: dice si busca o QUE lo frena, en claro."""
        e = self.estado_operativo(now)
        n_banda = len(e["en_banda"])
        if e["con_datos"] == 0:
            diag = ("⏳ Sin velas aún: el colector está cargando o el mercado está "
                    "cerrado. En cuanto lleguen velas, analizo.")
        elif n_banda == 0:
            # Revelar los mejores pagos capturados: si hay pagos pero por debajo de
            # 72%, el mercado paga poco ahora (bajar el minimo o esperar); si no hay
            # NINGUN pago capturado, es problema de captura (no de banda).
            if e.get("con_pago", 0) == 0:
                extra = ("No se capturo NINGUN pago todavia (updateAssets). Espera "
                         "1-2 min; si sigue en 0, es la captura de pagos.")
            else:
                mejores = ", ".join(f"{p} {int(v)}%" for p, v in e.get("top", []))
                extra = f"Mejores pagos AHORA: {mejores}."
            diag = (f"🚫 0 pares con pago {int(self.payout_min)}-"
                    f"{int(self.payout_max)}%. {extra}")
        else:
            muestra = ", ".join(f"{p} {int(v)}%" for p, v in sorted(
                e["en_banda"], key=lambda x: -x[1])[:6])
            diag = (f"✅ Operativo: {n_banda} pares con buen pago ({muestra}). "
                    f"Buscando setups.")
        return (f"🩺 *{self.name}* — {prefijo}\n"
                f"Pares: {e['pares']} · con datos: {e['con_datos']} · "
                f"pago {int(self.payout_min)}-{int(self.payout_max)}%: {n_banda}\n"
                f"Señales última hora: {e['emitidas_hora']}\n"
                f"{diag}")

    def _notificar_salud(self, prefijo: str, now: Optional[float] = None) -> None:
        """Manda la tarjeta de salud al Telegram del dueño (si está activo)."""
        txt = self._tarjeta_salud(prefijo, now)
        if self.notifier and control.telegram_activo(self.id):
            try:
                self.notifier.send_alert(txt)
            except Exception:
                self.log.warning("No se pudo enviar la tarjeta de salud")
        else:
            self.log.info("[DRY-RUN salud] %s", txt.replace("\n", " | "))

    # ------------------------------------------------------------- loop
    def run(self) -> None:
        """
        Loop principal: resolver vencidas + una pasada. Escanea MÁS SEGUIDO que el
        timeframe (cada `scan_interval`, tope 30s) para más análisis y reacción; el
        anti-duplicado evita repetir la misma señal dentro del ciclo. Manda una
        tarjeta de SALUD al arrancar y un latido cada hora (visibilidad: el usuario
        ve al toque si busca o qué lo frena, sin mirar logs).
        """
        self._running = True
        # Cadencia de escaneo: mas energia = revisar seguido. No baja de 15s para no
        # golpear el feed, ni pasa del timeframe (para M1 igual conviene 30s).
        intervalo = int(getattr(self, "scan_interval",
                                min(self.timeframe_seconds, 30)) or 30)
        intervalo = max(15, intervalo)
        self.log.info("%s arrancado (%d pares, escaneo cada %ds, tf %ds). Feed: %s | "
                      "Telegram: %s", self.name, len(self.pairs), intervalo,
                      self.timeframe_seconds, type(self.feed).__name__,
                      "ON" if self.notifier else "DRY-RUN")
        self._notificar_salud("arranque")          # el bot avisa que está vivo
        ultimo_latido = time.time()
        while self._running:
            try:
                self.resolve_pending()       # aprende de las senales ya vencidas
                self.scan_once()             # busca nuevas
                # Latido cada hora: sigue vivo + estado (aunque esté callado).
                if time.time() - ultimo_latido >= 3600:
                    self._notificar_salud("latido (1h)")
                    ultimo_latido = time.time()
            except Exception:
                self.log.exception("Error en la pasada; el bot sigue vivo")
            time.sleep(intervalo)

    def stop(self) -> None:
        self._running = False
