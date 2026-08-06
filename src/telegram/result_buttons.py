"""
src/telegram/result_buttons.py
==============================
FASE 2: reporte MANUAL del resultado del usuario (botones de la tarjeta) y su
enrutado UNICO hacia el orquestador.

Flujo unificado (una sola via, sin caminos paralelos):

    [Boton: Gane / Perdi / No entre]
        -> route_user_result(system, callback)
        -> FuzionTradingSystem.on_user_reported_result()
            |- user_stake > 0 ? -> RiskManager.registrar_trade()  (equity+recovery)
            |- siempre          -> db.save_signal_result(source="user")
            |- siempre          -> signal_results.append(...)

USER performance (plata real) es lo unico que llega al RiskManager. El acierto
SINTETICO del motor va por otro lado (SignalTracker / on_signal_expired).

Nota de alcance: el bot es de SENALES, no coloca ordenes ni conoce el STAKE real;
si el usuario no lo informa, se usa el tamano sugerido por el gestor como proxy.
"No entre" = no opero -> stake 0 -> no toca capital, solo queda en analytics.

Funciones PURAS salvo `route_user_result`, que solo llama metodos del `system`
(duck-typing, sin red): se prueban sin internet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Prefijo del callback_data de los botones de resultado.
PREFIX = "res"
# Desenlaces validos: gano / perdio / no entro (no opero).
OUTCOMES = ("win", "loss", "skip")


def result_buttons_row(pair: str, payout: float) -> List[Tuple[str, str]]:
    """
    Fila de botones para la tarjeta: (label, callback_data). Se codifica el par y
    el payout en el callback para reconstruir el PnL al hacer clic (el mensaje del
    boton llega despues, sin el `result` original a mano).

    callback_data: "res:<outcome>:<pair>:<payout_int>" (cabe en 64 bytes).
    """
    p = int(round(float(payout)))
    return [
        ("✅ Gané", f"{PREFIX}:win:{pair}:{p}"),
        ("❌ Perdí", f"{PREFIX}:loss:{pair}:{p}"),
        ("➖ No entré", f"{PREFIX}:skip:{pair}:{p}"),
    ]


def parse_result_callback(data: str) -> Optional[Dict[str, object]]:
    """
    Parsea "res:<outcome>:<pair>:<payout>". Devuelve dict o None si no es un
    callback de resultado / esta mal formado (asi el handler lo ignora seguro).
    """
    if not data or not data.startswith(f"{PREFIX}:"):
        return None
    partes = data.split(":")
    if len(partes) != 4:
        return None
    _, outcome, pair, payout_s = partes
    if outcome not in OUTCOMES or not pair:
        return None
    try:
        payout = float(payout_s)
    except ValueError:
        return None
    return {"outcome": outcome, "pair": pair, "payout": payout}


def user_pnl(outcome: str, stake: float, payout: float) -> float:
    """
    PnL neto de una opcion binaria segun el resultado reportado:
      - win : +stake * payout%   (la ganancia paga el % del payout).
      - loss: -stake             (se pierde lo apostado).
      - skip: 0.0                (no entro: no hubo dinero en juego).
    payout se acepta en % (92) o fraccion (0.92).
    """
    if stake < 0:
        raise ValueError("stake no puede ser negativo")
    if outcome == "skip":
        return 0.0
    pay = float(payout)
    pay = pay / 100.0 if pay > 1.0 else pay
    if outcome == "win":
        return round(stake * pay, 2)
    if outcome == "loss":
        return round(-stake, 2)
    raise ValueError(f"outcome invalido: {outcome}")


def route_user_result(system: Any, data: str, signal_id: Optional[str] = None,
                      stake: Optional[float] = None) -> Optional[Dict[str, object]]:
    """
    Via UNICA del boton -> orquestador. Parsea el callback, calcula stake/pnl y
    delega en `system.on_user_reported_result(...)`, que decide si toca el
    RiskManager (solo si el usuario opero) y persiste analytics.

    - "skip" (No entre): stake efectivo 0 y pnl 0 -> el sistema NO toca capital.
    - win/loss: si no se da stake, se usa el tamano sugerido por el gestor.
    Devuelve el registro del sistema o None si el callback no es valido.
    """
    info = parse_result_callback(data)
    if info is None:
        return None
    outcome = info["outcome"]
    pair = info["pair"]

    if outcome == "skip":
        eff_stake = 0.0
        pnl = 0.0
        won = False
    else:
        if stake is None:
            stake = system.risk_manager.position_size()
        eff_stake = float(stake)
        pnl = user_pnl(outcome, eff_stake, info["payout"])
        won = outcome == "win"

    sid = signal_id if signal_id is not None else pair
    return system.on_user_reported_result(sid, pair, won, eff_stake, pnl)
