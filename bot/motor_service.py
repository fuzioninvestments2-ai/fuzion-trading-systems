"""
bot/motor_service.py
====================
Servicio que ejecuta el MOTOR en segundo plano (hilo), controlable por Telegram.

Permite arrancar/parar el motor sin bloquear el bot de Telegram. En este modo el
feed es SIMULADO (moneda al aire, sin ventaja real) para que puedas ver el
control funcionando de forma segura, sin red ni dinero. Cuando conectemos Pocket
Option, se sustituye el feed simulado por el real sin cambiar esta estructura.

SRP: gestiona el ciclo de vida del hilo del motor y expone estado/última señal.
Thread-safe con un lock para leer estado desde el hilo de Telegram.
"""

import math
import os
import random
import threading
import time

from bot.config import get_preset
from bot.candles import CandleBuilder
from bot.scoring_strategy import ScoringStrategy, CALL, PUT
from bot.risk_manager import RiskManager
from bot.session import SessionManager
from bot.trade_logger import TradeLogger


class MotorService:
    def __init__(self, preset="moderado", payout=0.92,
                 db_path="logs/telegram_motor.db", tick_delay=0.02):
        self.preset = preset
        self.cfg = get_preset(preset)
        self.payout = payout
        self.db_path = db_path
        self.tick_delay = tick_delay        # pausa entre ticks (simula "vivo")

        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_signal = None
        self._logger = None

    # --- Control (lo que Telegram llama) ---

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        # Asegurar carpeta de la base de datos.
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def last_signal(self):
        with self._lock:
            return self._last_signal

    def status(self):
        with self._lock:
            logger = self._logger
        return logger.get_statistics() if logger else {}

    # --- Bucle del motor (en el hilo) ---

    def _run_loop(self):
        logger = TradeLogger(self.db_path)
        with self._lock:
            self._logger = logger

        cb = CandleBuilder(self.cfg.timeframe_seconds())
        strat = ScoringStrategy(self.cfg)
        risk = RiskManager(self.cfg)
        rng = random.Random()

        # Resultado simulado (moneda al aire). En real, aquí iría la orden.
        def execute_fn(signal, amount):
            return rng.random() < 0.5

        # Cada operación se registra en la base de datos y actualiza la señal.
        def on_trade(signal, amount, is_win, pnl, confidence):
            with self._lock:
                self._last_signal = signal
            logger.log_trade({
                "asset": self.cfg.current_asset, "direction": signal,
                "amount": amount, "result": "win" if is_win else "loss",
                "profit": pnl, "confidence": confidence, "strategy": "scoring",
            })

        session = SessionManager(self.cfg, strat, risk, execute_fn,
                                 payout=self.payout, on_trade=on_trade)
        session.start()

        i = ts = 0
        while not self._stop.is_set():
            price = 100 + 3 * math.sin(i / 25.0) + rng.uniform(-0.4, 0.4)
            closed = cb.add_tick(price, ts)
            ts += 20_000
            i += 1
            if closed is not None:
                session.on_candle(cb.to_dataframe())
                if not session.active:
                    # Sesión terminada -> registrar y empezar otra.
                    s = session.summary()
                    logger.log_session({
                        "target_profit": self.cfg.target_profit,
                        "actual_profit": s["profit"], "total_trades": s["trades"],
                        "wins": s["wins"], "losses": s["losses"],
                        "win_rate": s["win_rate"], "stop_reason": s["stop_reason"],
                    })
                    session.start()
            if self.tick_delay:
                time.sleep(self.tick_delay)
