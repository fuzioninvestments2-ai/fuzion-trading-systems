"""
bot/session.py
==============
Motor de SESIONES: ejecuta operaciones hasta alcanzar el `target_profit` o hasta
que el riesgo obligue a parar (como Dewbot: se detiene al llegar al objetivo).

SRP: coordina estrategia + riesgo + ejecución. NO calcula indicadores ni habla
con el bróker directamente: la ejecución se INYECTA (`execute_fn`), lo que
permite:
  - En pruebas/simulación: inyectar un resultado determinista o simulado.
  - En real: inyectar la función que manda la orden a Pocket Option (demo).

EL PORQUÉ del payout: en opciones binarias, si ganas cobras `monto * payout`
(ej. 92%), y si pierdes, pierdes el `monto`. Por eso el resultado no es simétrico
y hay que modelarlo así.
"""

import logging

from bot.scoring_strategy import CALL, PUT, HOLD


class SessionManager:
    """
    Gestiona UNA sesión de trading.

    Parámetros
    ----------
    cfg : TradingConfig
    strategy : objeto con analyze(df) -> (señal, confianza, detalles)
    risk : RiskManager
    execute_fn : callable(signal, amount) -> (is_win: bool)
        Ejecuta (o simula) la operación y dice si ganó. La conversión a dinero
        (payout) la hace esta clase, para centralizar la regla.
    logger : logging.Logger (opcional)
    payout : float (ej. 0.92)
    """

    def __init__(self, cfg, strategy, risk, execute_fn, logger=None, payout=0.92,
                 on_trade=None):
        self.cfg = cfg
        self.strategy = strategy
        self.risk = risk
        self.execute_fn = execute_fn
        self.log = logger or logging.getLogger("session")
        self.payout = payout
        # Gancho opcional: se llama tras cada operación con su resultado. Sirve
        # para registrar/notificar (p. ej. base de datos o Telegram) sin acoplar
        # esta clase a esos detalles.
        self.on_trade = on_trade

        self.active = False
        self.stop_reason = None

    def start(self):
        self.risk.reset_session()
        self.active = True
        self.stop_reason = None
        self.log.info("Sesión iniciada | target=$%.2f capital=$%.2f",
                      self.cfg.target_profit, self.cfg.trade_capital)

    def on_candle(self, df):
        """
        Procesa una vela cerrada: analiza, y si hay señal válida y el riesgo lo
        permite, ejecuta una operación. Devuelve la señal finalmente operada
        (o HOLD). Si la sesión debe terminar, marca self.active = False.
        """
        if not self.active:
            return HOLD

        # 1) ¿El riesgo permite seguir? (se comprueba ANTES de operar).
        ok, motivo = self.risk.check_risk_limits()
        if not ok:
            self._stop(motivo)
            return HOLD

        # 2) La estrategia decide.
        signal, confidence, details = self.strategy.analyze(df)
        if signal not in (CALL, PUT):
            return HOLD

        # 3) Tamaño de la operación (con Martingale/tope si aplica).
        amount = self.risk.next_amount(confidence)

        # 4) Ejecutar (o simular). execute_fn dice solo si ganó o no.
        try:
            is_win = bool(self.execute_fn(signal, amount))
        except Exception:
            self.log.exception("Fallo ejecutando la operación (se omite)")
            return HOLD

        # 5) Convertir a dinero según payout de opciones binarias.
        pnl = amount * self.payout if is_win else -amount
        self.risk.register_result(is_win, pnl)
        self.log.info("%s $%.2f -> %s | profit sesión=$%.2f",
                      signal, amount, "WIN" if is_win else "LOSS",
                      self.risk.session_profit)

        # Notificar el resultado por el gancho (si se inyectó).
        if self.on_trade:
            try:
                self.on_trade(signal, amount, is_win, pnl, confidence)
            except Exception:
                self.log.exception("Fallo en on_trade (se ignora)")

        # 6) ¿Alcanzamos el objetivo de ganancia? -> fin de sesión.
        if self.risk.session_profit >= self.cfg.target_profit:
            self._stop("target de ganancia alcanzado")
            return signal

        # 7) ¿Se cruzó un límite tras esta operación? -> parar.
        ok, motivo = self.risk.check_risk_limits()
        if not ok:
            self._stop(motivo)

        return signal

    def _stop(self, reason):
        self.active = False
        self.stop_reason = reason
        self.log.info("Sesión terminada: %s | trades=%d win_rate=%.0f%% profit=$%.2f",
                      reason, self.risk.trades, self.risk.win_rate() * 100,
                      self.risk.session_profit)

    def summary(self):
        return {
            "trades": self.risk.trades,
            "wins": self.risk.wins,
            "losses": self.risk.losses,
            "win_rate": round(self.risk.win_rate(), 4),
            "profit": round(self.risk.session_profit, 2),
            "stop_reason": self.stop_reason,
        }
