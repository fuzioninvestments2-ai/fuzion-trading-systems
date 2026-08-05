"""
src/telegram/result_buttons.py
==============================
FASE 2: reporte MANUAL del resultado del usuario (botones de la tarjeta).

Separa el flujo USER PERFORMANCE (plata real del usuario) del SIGNAL PERFORMANCE
(acierto sintetico del motor, que ya vive en bot/signal_log.SignalTracker y NO se
duplica aqui). Solo lo que el usuario reporta con un boton alimenta el
RiskManager (equity/drawdown/circuit breaker/recovery), porque son las unicas
perdidas/ganancias de capital REAL.

Nota de alcance: el bot es de SENALES, no coloca ordenes. No conoce el STAKE
real; el caller pasa el stake (por defecto, el tamano sugerido por el gestor).

Funciones PURAS (sin red, sin Telegram): se prueban sin internet.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Prefijo del callback_data de los botones de resultado.
PREFIX = "res"
# Desenlaces validos (ganó / perdió / empate-refund).
OUTCOMES = ("win", "loss", "tie")


def result_buttons_row(pair: str, payout: float) -> List[Tuple[str, str]]:
    """
    Fila de botones para la tarjeta: (label, callback_data). Se codifica el par y
    el payout en el propio callback para reconstruir el PnL al hacer clic (el
    mensaje del boton llega despues, sin el `result` original a mano).

    callback_data: "res:<outcome>:<pair>:<payout_int>". Cabe en el limite de 64
    bytes de Telegram para pares/payout normales.
    """
    p = int(round(float(payout)))
    return [
        ("✅ Gané", f"{PREFIX}:win:{pair}:{p}"),
        ("❌ Perdí", f"{PREFIX}:loss:{pair}:{p}"),
        ("➖ Empate", f"{PREFIX}:tie:{pair}:{p}"),
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
      - tie : 0.0                (empate/refund: devuelven el stake).
    payout se acepta en % (92) o fraccion (0.92).
    """
    if stake < 0:
        raise ValueError("stake no puede ser negativo")
    pay = float(payout)
    pay = pay / 100.0 if pay > 1.0 else pay
    if outcome == "win":
        return round(stake * pay, 2)
    if outcome == "loss":
        return round(-stake, 2)
    if outcome == "tie":
        return 0.0
    raise ValueError(f"outcome invalido: {outcome}")


def apply_user_result(risk_manager, data: str,
                      stake: Optional[float] = None) -> Optional[Dict[str, object]]:
    """
    Aplica el resultado reportado al RiskManager (registrar_trade), que actualiza
    equity/drawdown/recovery del par. Devuelve un resumen o None si el callback
    no es valido.

    stake: si es None se usa el tamano sugerido por el gestor (position_size),
    proxy razonable cuando el usuario no informa su apuesta real.
    """
    info = parse_result_callback(data)
    if info is None:
        return None
    if stake is None:
        stake = risk_manager.position_size()
    pnl = user_pnl(info["outcome"], float(stake), info["payout"])
    risk_manager.registrar_trade(info["pair"], pnl)
    return {"pair": info["pair"], "outcome": info["outcome"],
            "stake": round(float(stake), 2), "pnl": pnl}
