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
import time
from typing import Any, Dict, List, Optional

from core.config import get_bot_config, ROOT
from core.results_store import ResultsStore
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine, NEUTRAL
from core.learning_engine import LearningEngine
from data.price_feed import PriceFeed, StubPriceFeed
from telegram.notifier import TelegramNotifier


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
        self.feed = price_feed or StubPriceFeed()

        # Notifier: si hay token/canal, real; si no, None (modo dry-run: solo log).
        tg = cfg.get("telegram", {})
        if notifier is not None:
            self.notifier = notifier
        elif tg.get("bot_token") and tg.get("channel_id"):
            self.notifier = TelegramNotifier(tg["bot_token"], tg["channel_id"])
        else:
            self.notifier = None

        self._emitted_ts: List[float] = []     # timestamps de emisiones (rate limit)
        self._running = False
        self.log = self._setup_logger(cfg.get("log_level", "INFO"))

    def _setup_logger(self, level: str) -> logging.Logger:
        logger = logging.getLogger(f"bot.{self.id}")
        logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
        if not logger.handlers:
            logs_dir = os.path.join(ROOT, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            fh = logging.FileHandler(os.path.join(logs_dir, f"{self.id}.log"))
            fh.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s"))
            logger.addHandler(fh)
            logger.addHandler(logging.StreamHandler())
        return logger

    # ------------------------------------------------------------- rate limit
    def _rate_ok(self, now: float) -> bool:
        """True si no se supero el tope de senales/hora. Purga las viejas."""
        limite = now - 3600.0
        self._emitted_ts = [t for t in self._emitted_ts if t >= limite]
        return len(self._emitted_ts) < self.max_signals_per_hour

    # ------------------------------------------------------------- tarjeta
    def build_card(self, pair: str, result: Dict[str, Any]) -> str:
        """Tarjeta de senal para Telegram (texto Markdown)."""
        flecha = "⬆️ CALL" if result["signal"] == "CALL" else "⬇️ PUT"
        conf = result["confirmations"]
        indic = ", ".join(result["confirming"])
        prioridad = " ⭐" if self.learning.is_prioritized(result["setup_id"]) else ""
        return (f"*{self.name}*  ({self.card_label}){prioridad}\n"
                f"Par: *{pair}*\n"
                f"Senal: *{flecha}*\n"
                f"Confirmaciones: {conf} ({indic})\n"
                f"Precio: {result['price']:.5f}")

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
                continue

            ok, motivo = self.risk.can_trade(pair)
            if not ok:
                self.log.debug("Riesgo bloquea %s: %s", pair, motivo)
                continue

            if not self.learning.should_emit(result["setup_id"]):
                self.log.debug("Aprendizaje descarta setup %s", result["setup_id"])
                continue

            # Emitir: persistir + notificar + contar para el rate limit.
            rec = {"ts": int(now), "pair": pair, "timeframe": self.timeframe,
                   "direction": result["signal"], "setup_id": result["setup_id"],
                   "confirmations": result["confirmations"],
                   "price": result["price"], "atr": result["atr"]}
            sid = self.store.save_signal(rec)
            rec["id"] = sid
            card = self.build_card(pair, result)
            if self.notifier:
                self.notifier.send_text(card)
            else:
                self.log.info("[DRY-RUN sin token] %s", card.replace("\n", " | "))
            self._emitted_ts.append(now)
            emitidas.append(rec)
            self.log.info("Senal emitida: %s %s (setup %s)", pair,
                          result["signal"], result["setup_id"])

        return emitidas

    # ------------------------------------------------------------- loop
    def run(self) -> None:
        """Loop principal: una pasada cada `timeframe_seconds`. Ctrl+C para parar."""
        self._running = True
        self.log.info("%s arrancado (%d pares, cada %ds). Feed: %s | Telegram: %s",
                      self.name, len(self.pairs), self.timeframe_seconds,
                      type(self.feed).__name__, "ON" if self.notifier else "DRY-RUN")
        while self._running:
            try:
                self.scan_once()
            except Exception:
                self.log.exception("Error en la pasada; el bot sigue vivo")
            time.sleep(self.timeframe_seconds)

    def stop(self) -> None:
        self._running = False
