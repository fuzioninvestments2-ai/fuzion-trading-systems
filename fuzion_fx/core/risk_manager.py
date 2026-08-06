"""
core/risk_manager.py (fuzion_fx)
================================
Proteccion de capital por bot, configurada desde la seccion `risk` del yaml:

  - max_daily_trades_per_pair: tope de trades/dia por par (no sobre-operar).
  - max_daily_loss_pct: circuit breaker; si la perdida del dia supera ese % del
    capital, se corta TODO hasta reset.
  - recovery_after_consecutive_losses: tras N perdidas seguidas en un par, ese
    par entra en RECOVERY (se pausa el dia) para cortar la mala racha.
  - default_stake_pct: tamano sugerido por trade (% del capital).
  - news_buffer_minutes: minutos alrededor de una noticia en que no se opera
    (lo aplica quien tenga el calendario; aca se guarda el parametro).

ADVISORY: el bot da SENALES, no coloca ordenes. Esto disciplina que senal se
emite y cuando parar. Sin red. Se prueba sin internet.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


class RiskManager:
    def __init__(self, risk_cfg: Dict[str, Any], capital: float = 1000.0) -> None:
        self.max_trades_par = int(risk_cfg.get("max_daily_trades_per_pair", 10))
        self.max_daily_loss_pct = float(risk_cfg.get("max_daily_loss_pct", 5.0))
        self.recovery_after = int(risk_cfg.get("recovery_after_consecutive_losses", 3))
        self.default_stake_pct = float(risk_cfg.get("default_stake_pct", 1.0))
        self.news_buffer_minutes = int(risk_cfg.get("news_buffer_minutes", 5))
        self.capital = float(capital)
        self.reset_day()

    def reset_day(self) -> None:
        """Reinicia el estado del dia (pnl, contadores y rachas por par)."""
        self.day_pnl = 0.0
        self.trades_por_par: Dict[str, int] = {}
        self.perdidas_seguidas: Dict[str, int] = {}
        self.recovery: Dict[str, bool] = {}

    def set_capital(self, capital: float) -> None:
        if capital > 0:
            self.capital = float(capital)

    def position_size(self) -> float:
        """Stake sugerido = default_stake_pct % del capital."""
        return round(self.capital * self.default_stake_pct / 100.0, 2)

    def in_recovery(self, pair: str) -> bool:
        return self.recovery.get(pair, False)

    def circuit_breaker(self) -> Tuple[bool, str]:
        """(permitido, motivo). Corta si la perdida del dia supera el % del capital."""
        limite = -self.capital * self.max_daily_loss_pct / 100.0
        if self.day_pnl <= limite:
            return False, (f"circuit breaker: perdida del dia {self.day_pnl:.2f} "
                           f"<= {limite:.2f} ({self.max_daily_loss_pct:.0f}%)")
        return True, "ok"

    def can_trade(self, pair: str) -> Tuple[bool, str]:
        """
        Chequeo previo a emitir una senal del par: circuit breaker (global) ->
        recovery del par -> tope de trades/dia del par.
        """
        ok, motivo = self.circuit_breaker()
        if not ok:
            return False, motivo
        if self.in_recovery(pair):
            return False, f"{pair} en recovery (racha de {self.recovery_after} perdidas)"
        if self.trades_por_par.get(pair, 0) >= self.max_trades_par:
            return False, f"tope de {self.max_trades_par} trades/dia en {pair}"
        return True, "ok"

    def register_result(self, pair: str, pnl: float, won: bool) -> None:
        """
        Registra el resultado real (reportado): actualiza pnl del dia, contador
        del par y la racha de perdidas (que dispara recovery).
        """
        self.day_pnl += float(pnl)
        self.trades_por_par[pair] = self.trades_por_par.get(pair, 0) + 1
        if won:
            self.perdidas_seguidas[pair] = 0
            self.recovery[pair] = False          # una ganadora saca del recovery
        else:
            n = self.perdidas_seguidas.get(pair, 0) + 1
            self.perdidas_seguidas[pair] = n
            if n >= self.recovery_after:
                self.recovery[pair] = True
