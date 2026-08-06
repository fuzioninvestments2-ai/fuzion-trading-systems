"""
src/core/trading_system.py
==========================
FASE 2: orquestador de alto nivel. Formaliza la separacion de los DOS flujos de
resultado, que es la regla que evita autoengano:

  - SIGNAL performance (auto, sintetico): entry vs expiry del propio motor. Sirve
    para ANALYTICS/calidad (win-rate, calibracion). NUNCA toca el RiskManager: no
    hubo dinero real en juego.
  - USER performance (manual, boton Telegram): la plata REAL del usuario. SOLO
    esto alimenta el RiskManager (equity/drawdown/circuit breaker/recovery), y
    solo si el usuario REALMENTE opero (stake > 0).

Regla 1 (no duplicar): compone RiskManager; la persistencia (db) y el tracker de
senales (bot.signal_log.SignalTracker) se INYECTAN, no se reimplementan aqui. Si
no se inyectan, guarda las analytics en memoria (`signal_results`).

Metodos sincronos y sin red: se prueban sin internet. El caller async puede
envolver la persistencia si su `db` es asincrona.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.risk.manager import RiskManager


def calculate_pnl(entry_price: float, expiry_price: float,
                  direction: str) -> Tuple[str, float]:
    """
    Resultado SINTETICO de una senal (para stats, no para riesgo).

    Binaria: se acierta si el precio se movio a favor de la direccion.
      - CALL acierta si expiry > entry ; PUT acierta si expiry < entry.
    Devuelve (outcome, pnl_proxy):
      - outcome: "win" | "loss" | "tie" (empate si no se movio).
      - pnl_proxy: delta de precio A FAVOR (positivo = acierto). Es una MAGNITUD
        de calidad, NO dinero (el bot no coloca ordenes).
    """
    d = str(direction).upper()
    delta = float(expiry_price) - float(entry_price)
    if d in ("CALL", "BUY", "UP"):
        favor = delta
    elif d in ("PUT", "SELL", "DOWN"):
        favor = -delta
    else:
        raise ValueError(f"direccion invalida: {direction}")
    if favor > 0:
        return "win", round(favor, 8)
    if favor < 0:
        return "loss", round(favor, 8)
    return "tie", 0.0


class FuzionTradingSystem:
    """
    Orquestador: mantiene el RiskManager y enruta los dos flujos de resultado a
    su destino correcto. `db` y `tracker` son opcionales (inyeccion).
    """

    def __init__(self, risk_manager: Optional[RiskManager] = None,
                 db: Any = None, tracker: Any = None) -> None:
        self.risk_manager = risk_manager or RiskManager()
        self.db = db                 # opcional: expone save_signal_result / get_signal_pair
        self.tracker = tracker       # opcional: bot.signal_log.SignalTracker
        # Registro de PERFORMANCE DE SENALES (auto + user) para analytics.
        self.signal_results: List[Dict[str, Any]] = []

    def _persist(self, signal_id: str, pnl: float, source: str) -> None:
        """Guarda en la db inyectada si expone save_signal_result; si no, no-op."""
        if self.db is not None and hasattr(self.db, "save_signal_result"):
            self.db.save_signal_result(signal_id, pnl, source=source)

    def on_signal_expired(self, signal_id: str, entry_price: float,
                          expiry_price: float, direction: str) -> Dict[str, Any]:
        """
        Auto-detecta el resultado SINTETICO de una senal vencida. Para stats,
        NO para riesgo (no toca el RiskManager).
        """
        outcome, pnl = calculate_pnl(entry_price, expiry_price, direction)
        rec: Dict[str, Any] = {"signal_id": signal_id, "outcome": outcome,
                               "pnl": pnl, "source": "auto"}
        self.signal_results.append(rec)
        self._persist(signal_id, pnl, source="auto")
        return rec

    def on_user_reported_result(self, signal_id: str, pair: str, user_won: bool,
                                user_stake: float,
                                user_pnl: float) -> Dict[str, Any]:
        """
        Resultado REAL reportado por el usuario (boton Telegram). ESTO alimenta al
        RiskManager, pero SOLO si el usuario realmente opero (stake > 0): si solo
        miro la senal sin entrar, no hubo perdida/ganancia de capital que
        gestionar (recovery/drawdown no deben reaccionar a plata inexistente).

        `pair` puede venir dado o resolverse de la db (get_signal_pair).
        """
        if not pair and self.db is not None and hasattr(self.db, "get_signal_pair"):
            pair = self.db.get_signal_pair(signal_id)

        traded = float(user_stake) > 0
        if traded:
            self.risk_manager.registrar_trade(pair, float(user_pnl))

        rec: Dict[str, Any] = {"signal_id": signal_id, "pair": pair,
                               "outcome": "win" if user_won else "loss",
                               "pnl": float(user_pnl), "stake": float(user_stake),
                               "traded": traded, "source": "user"}
        self.signal_results.append(rec)
        self._persist(signal_id, float(user_pnl), source="user")
        return rec
