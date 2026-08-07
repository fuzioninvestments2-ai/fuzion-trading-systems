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
import time
from typing import Any, Dict, List, Optional

from core.config import get_bot_config, ROOT
from core.results_store import ResultsStore
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine, NEUTRAL
from core.learning_engine import LearningEngine
from data.price_feed import PriceFeed, StubPriceFeed, CandleStoreFeed
from telegram.notifier import TelegramNotifier
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

        self._emitted_ts: List[float] = []     # timestamps de emisiones (rate limit)
        # Anti-duplicado: ultima direccion avisada por par. Se avisa SOLO cuando
        # cambia (una alerta por setup nuevo), no en cada pasada.
        self._last_dir: Dict[str, str] = {}
        self.payout_pct = 85                   # pago asumido (PO no lo expone aca)
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

    # ------------------------------------------------------------- sesion / tz
    @staticmethod
    def _sesion_fx(hora_utc: int) -> str:
        """Sesion FX dominante por hora UTC (solape Londres-NuevaYork = top)."""
        h = int(hora_utc) % 24
        if 12 <= h < 16:
            return "Londres-NuevaYork"
        if 7 <= h < 12:
            return "Londres"
        if 16 <= h < 21:
            return "NuevaYork"
        return "Asia"

    # ------------------------------------------------------------- tarjeta rica
    def build_card(self, pair: str, result: Dict[str, Any]) -> str:
        """
        Tarjeta como la del bot anterior: divisa, direccion (arriba/abajo), hora
        de entrada y vencimiento, sesion, pago, confirmaciones, acierto reciente
        y aviso demo. Los tiempos van en hora LOCAL de la PC.
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

        es_call = result["signal"] == "CALL"
        flecha = "🟩 CALL (poner ARRIBA)" if es_call else "🟥 PUT (poner ABAJO)"
        divisa = pair.replace("/", "")
        sesion = self._sesion_fx(datetime.now(timezone.utc).hour)
        indic = ", ".join(result["confirming"])
        prioridad = " ⭐" if self.learning.is_prioritized(result["setup_id"]) else ""

        # ATR en pips (volatilidad reciente real).
        ps = pip_size(pair)
        atr_pips = round(result["atr"] / ps, 1) if ps else 0.0

        # Acierto reciente del setup (aprendizaje). Honesto: solo con muestra.
        st = self.store.setup_stats(result["setup_id"])
        if st["trades"] >= 1:
            acierto = f"{st['win_pct']:.0f}%  ({st['trades']} señales medidas)"
        else:
            acierto = "sin muestra aún (recién aprende)"

        return (
            f"🤖 *{self.name}*{prioridad}\n"
            f"🌐 Zona Horaria: UTC{horas_off:+d}:00\n"
            f"📊 DIVISA: *{divisa}*\n"
            f"{flecha}\n"
            f"⏰ HORA DE ENTRADA: *{entrada.strftime('%H:%M')}*\n"
            f"⌛ VENCE: {vence.strftime('%H:%M')}  ({self.card_label})\n"
            f"🌍 Mercado: {sesion}\n"
            f"💰 Pago del activo: {self.payout_pct}%\n"
            f"🎯 Confirmaciones: {result['confirmations']} ({indic})\n"
            f"📈 Acierto reciente: {acierto}\n"
            f"📊 Volatilidad (ATR): {atr_pips} pips\n"
            f"⚠️ Demo · señal educativa · el acierto no está garantizado")

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

            # ANTI-DUPLICADO: avisar SOLO si la direccion cambio respecto al ultimo
            # aviso del par (una alerta por setup nuevo, no cada minuto).
            if self._last_dir.get(pair) == result["signal"]:
                continue

            ok, motivo = self.risk.can_trade(pair)
            if not ok:
                self.log.debug("Riesgo bloquea %s: %s", pair, motivo)
                continue

            if not self.learning.should_emit(result["setup_id"]):
                self.log.debug("Aprendizaje descarta setup %s", result["setup_id"])
                continue

            # Emitir: persistir + notificar (tarjeta + grafico) + contadores.
            rec = {"ts": int(now), "pair": pair, "timeframe": self.timeframe,
                   "direction": result["signal"], "setup_id": result["setup_id"],
                   "confirmations": result["confirmations"],
                   "price": result["price"], "atr": result["atr"]}
            sid = self.store.save_signal(rec)
            rec["id"] = sid
            card = self.build_card(pair, result)
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
            self._emitted_ts.append(now)
            emitidas.append(rec)
            self.log.info("Senal emitida: %s %s (setup %s)", pair,
                          result["signal"], result["setup_id"])

        return emitidas

    # ------------------------------------------------- feedback loop (aprendizaje)
    PAYOUT_ASUMIDO = 0.80          # payout tipico para el PnL sintetico de aprendizaje

    def resolve_pending(self, now: Optional[float] = None) -> int:
        """
        Cierra el loop de aprendizaje: para cada senal ya vencida, lee el precio
        al vencimiento (vela en po_candles) y decide win/loss. Actualiza el store
        (que alimenta al LearningEngine) y el riesgo (recovery/circuit breaker
        reaccionan al desempeno reciente de las senales). Devuelve cuantas resolvio.

        PnL SINTETICO (senal, no dinero real del usuario): +stake*payout si acierta,
        -stake si falla; sirve para que el bot mida su propio rendimiento y aprenda.
        """
        now = time.time() if now is None else now
        if not hasattr(self.feed, "price_at"):
            return 0
        cutoff = now - self.timeframe_seconds        # solo las ya vencidas
        n = 0
        for s in self.store.pending_older_than(int(cutoff)):
            expiry = int(s["ts"]) + self.timeframe_seconds
            exit_price = self.feed.price_at(s["pair"], self.timeframe_seconds, expiry)
            if exit_price is None:
                continue                             # aun sin vela de vencimiento
            entry = float(s["price"])
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
            n += 1
        if n:
            self.log.info("Resueltas %d senales (feedback de aprendizaje)", n)
        return n

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
