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

from core.config import get_bot_config, ROOT
from core.results_store import ResultsStore
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine, NEUTRAL
from core.learning_engine import LearningEngine
from data.price_feed import PriceFeed, StubPriceFeed, CandleStoreFeed
from telegram.notifier import TelegramNotifier
from telegram.signal_formatter import SignalCardFormatter
from telegram.chart import render_candles
from indicators.pips import pip_size

# Base de velas COMPARTIDA que escribe el colector; los bots leen de aca.
PO_CANDLES_DB = os.path.join(ROOT, "data", "db", "po_candles.db")


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

        # store inyectable (tests usan ':memory:'); por defecto, la sqlite del bot.
        self.store = store or ResultsStore(cfg["db_path"])
        self.risk = RiskManager(cfg["risk"])
        self.engine = SignalEngine(cfg["indicators"], cfg["signal"])
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

    # ------------------------------------------------------------- tarjeta rica
    def build_card(self, pair: str, result: Dict[str, Any],
                   payout: Optional[float] = None) -> str:
        """
        Arma el dict de datos POR PAR y delega el formato en SignalCardFormatter.
        El bot solo calcula (tiempos, ATR en pips, acierto por par); el formato
        (estrella, colores, mercado, disclaimer) vive en el formatter (Regla 1).
        Los tiempos van en hora LOCAL de la PC.
        """
        from datetime import datetime, timezone

        ahora = datetime.now().astimezone()          # local, con tz
        off = ahora.utcoffset()
        horas_off = int(off.total_seconds() // 3600) if off else 0
        # Entrada = proximo borde de vela; vence = entrada + timeframe.
        seg = self.timeframe_seconds
        epoch = int(ahora.timestamp())
        entrada_ep = epoch - (epoch % seg) + seg
        entrada = datetime.fromtimestamp(entrada_ep).astimezone()
        vence = datetime.fromtimestamp(entrada_ep + seg).astimezone()

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

            # Emitir: persistir + notificar (tarjeta + grafico) + contadores.
            rec = {"ts": int(now), "pair": pair, "timeframe": self.timeframe,
                   "direction": result["signal"], "setup_id": result["setup_id"],
                   "confirmations": result["confirmations"],
                   "price": result["price"], "atr": result["atr"]}
            sid = self.store.save_signal(rec)
            rec["id"] = sid
            card = self.build_card(pair, result, payout=pago)
            if self.notifier:
                # Grafico de velas del par como foto; si falla, va solo texto.
                try:
                    img = render_candles(candles, f"{self.name} · {pair} · {self.card_label}",
                                         result["signal"])
                except Exception:
                    img = None
                self.notifier.send(card, photo_buffer=img)
            else:
                self.log.info("[DRY-RUN sin token] %s", card.replace("\n", " | "))

            self._last_dir[pair] = result["signal"]
            self._last_emit_ts[pair] = now         # para el re-armado por vencimiento
            self._emitted_ts.append(now)
            emitidas.append(rec)
            self.log.info("Senal emitida: %s %s (setup %s)", pair,
                          result["signal"], result["setup_id"])

            # CHECKPOINT: agendar revision X seg antes del cierre de la vela.
            expiry = int(now) - (int(now) % self.timeframe_seconds) + self.timeframe_seconds
            self._schedule_checkpoint(pair, result["signal"], expiry, result, now)

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
        if self.notifier:
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
            # Borde de entrada = proximo multiplo de tf tras la deteccion (misma
            # formula que la tarjeta en build_card). La vela operada abre ahi y
            # vence en borde+tf.
            entry_border = ts - (ts % tf) + tf
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
            "direccion": s["direction"],
            "resultado": result,
            "entrada": entry,
            "cierre": exit_price,
            "modo_recuperacion": modo_recuperacion,
        }
        txt = self.formatter.format_result(d)
        if self.notifier:
            self.notifier.send_text(txt)
        else:
            self.log.info("[DRY-RUN resultado] %s", txt.replace("\n", " | "))

    # ------------------------------------------------------------- loop
    def run(self) -> None:
        """Loop principal: resolver vencidas + una pasada, cada `timeframe_seconds`."""
        self._running = True
        self.log.info("%s arrancado (%d pares, cada %ds). Feed: %s | Telegram: %s",
                      self.name, len(self.pairs), self.timeframe_seconds,
                      type(self.feed).__name__, "ON" if self.notifier else "DRY-RUN")
        while self._running:
            try:
                self.resolve_pending()       # aprende de las senales ya vencidas
                self.scan_once()             # busca nuevas
            except Exception:
                self.log.exception("Error en la pasada; el bot sigue vivo")
            time.sleep(self.timeframe_seconds)

    def stop(self) -> None:
        self._running = False
