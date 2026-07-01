"""
bot/risk_manager.py
===================
Gestión de riesgo: la pieza que PROTEGE tu capital (lo más importante).

Responsabilidades (SRP):
  - Decidir el tamaño de cada operación (position sizing), con Martingale
    OPCIONAL y con TOPE (nunca infinito).
  - Cortar la sesión si se cruzan límites: pérdida máxima, pérdidas seguidas o
    drawdown (caída desde el pico).

EL PORQUÉ del tope de Martingale y del stop diario:
El Martingale (doblar tras perder) puede recuperar pérdidas pequeñas, pero una
racha mala hace crecer la apuesta hasta reventar la cuenta. Por eso: (1) se
limita a `martingale_max_steps` pasos y (2) existe un stop de sesión que apaga
todo. Son los cinturones de seguridad que evitan el desastre.
"""

import logging


class RiskManager:
    def __init__(self, cfg, logger=None):
        self.cfg = cfg
        self.log = logger or logging.getLogger("risk_manager")

        # Apuesta base: una fracción pequeña del capital de sesión (2%), con
        # mínimo de 1.0. El porqué: arriesgar poco por operación alarga la vida
        # de la cuenta y da margen a la estadística.
        self.base_amount = max(1.0, cfg.trade_capital * 0.02)

        self.reset_session()

    def reset_session(self):
        """Reinicia el estado para una nueva sesión."""
        self.session_profit = 0.0
        self.consecutive_losses = 0
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.peak_profit = 0.0        # mayor ganancia acumulada vista (para drawdown)

    def next_amount(self, confidence=1.0):
        """
        Calcula el monto de la próxima operación.

        - Sin Martingale: monto base ajustado por confianza.
        - Con Martingale: tras N pérdidas seguidas, multiplica el base por
          `multiplier^N`, pero SOLO hasta `martingale_max_steps` pasos; pasado
          ese tope, vuelve al base (no seguimos doblando hacia el abismo).
        - Nunca supera `trade_capital` (tope duro de seguridad).
        """
        amount = self.base_amount * max(0.5, min(confidence, 1.0))

        if self.cfg.martingale_enabled and self.consecutive_losses > 0:
            step = min(self.consecutive_losses, self.cfg.martingale_max_steps)
            if self.consecutive_losses <= self.cfg.martingale_max_steps:
                amount = self.base_amount * (self.cfg.martingale_multiplier ** step)
            else:
                # Superado el tope: dejamos de doblar (protección).
                amount = self.base_amount

        # Tope duro: jamás arriesgar más que el capital de la sesión.
        return min(amount, self.cfg.trade_capital)

    def check_risk_limits(self):
        """
        Devuelve (permitido, motivo). Si permitido=False, la sesión debe parar.
        """
        # 1) Pérdida de sesión (session_profit negativo que supera el límite).
        if self.cfg.stop_loss_enabled and self.session_profit <= -self.cfg.max_loss_per_session:
            return False, "stop de sesión: pérdida máxima alcanzada"

        # 2) Pérdidas consecutivas.
        if self.consecutive_losses >= self.cfg.max_consecutive_losses:
            return False, "demasiadas pérdidas consecutivas"

        # 3) Drawdown: cuánto hemos caído desde el pico de ganancia de la sesión.
        if self.peak_profit > 0:
            drawdown = (self.peak_profit - self.session_profit) / self.peak_profit
            if drawdown > self.cfg.max_drawdown_percent:
                return False, f"drawdown {drawdown:.0%} supera el máximo"

        return True, "ok"

    def register_result(self, is_win, pnl):
        """
        Registra el resultado de una operación.
          is_win: True si ganó.
          pnl: variación de dinero (positiva si ganó, negativa si perdió).
        """
        self.trades += 1
        self.session_profit += pnl
        if is_win:
            self.wins += 1
            self.consecutive_losses = 0        # se rompe la racha de pérdidas
        else:
            self.losses += 1
            self.consecutive_losses += 1

        # Actualizamos el pico de ganancia para medir el drawdown.
        if self.session_profit > self.peak_profit:
            self.peak_profit = self.session_profit

    def win_rate(self):
        return (self.wins / self.trades) if self.trades else 0.0
