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

    def _persist(self, rec: Dict[str, Any]) -> None:
        """
        Guarda el registro en la db inyectada. Prefiere `save_result(rec)` (rico:
        par, outcome, stake); si no, cae a `save_signal_result(signal_id, pnl,
        source)` por compatibilidad. Si no hay db, no-op (solo memoria).
        """
        if self.db is None:
            return
        if hasattr(self.db, "save_result"):
            self.db.save_result(rec)
        elif hasattr(self.db, "save_signal_result"):
            self.db.save_signal_result(rec["signal_id"], rec["pnl"],
                                       source=rec["source"])

    def restore_state(self, since_ts: Optional[int] = None,
                      current_balance: Optional[float] = None) -> int:
        """
        Reconstruye el estado de riesgo del DIA tras un reinicio (CRITICO en
        produccion: sin esto, reiniciar borra recovery/drawdown/tope y el usuario
        podria perder mas de lo permitido).

        Lee del store los resultados OPERADOS del dia y los REPRODUCE por
        registrar_trade en orden cronologico, que reconstruye de una: equity,
        pico (drawdown), recovery por par y trades contados por par.

        Evita DOBLE CONTEO del equity: el balance real del broker YA incluye el
        PnL de hoy, asi que se rebasa la base al INICIO del dia
        (balance_actual - pnl_de_hoy) y el replay vuelve a llevar el equity al
        balance actual, con el pico correcto por el camino.

        Devuelve cuantos resultados se reprodujeron.
        """
        if self.db is None or not hasattr(self.db, "traded_results_since"):
            # Sin persistencia consultable: al menos alinea el capital si se dio.
            if current_balance is not None:
                self.risk_manager.set_capital(float(current_balance))
            return 0

        rows = self.db.traded_results_since(since_ts)
        pnl_hoy = sum(float(r["pnl"]) for r in rows)

        if current_balance is not None:
            base = float(current_balance) - pnl_hoy
            if base <= 0:                       # guarda ante datos inconsistentes
                base = float(current_balance)
            self.risk_manager.set_capital(base, reset=True)
        else:
            # Sin balance real: parte del capital ya fijado y solo reconstruye.
            self.risk_manager.reset_dia()

        for r in rows:
            self.risk_manager.registrar_trade(r["pair"], float(r["pnl"]))
        return len(rows)

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
        self._persist(rec)
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
        self._persist(rec)
        return rec
