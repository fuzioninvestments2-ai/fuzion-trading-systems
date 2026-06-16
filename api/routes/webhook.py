"""
Receptor de webhooks de TradingView (QUANT BOT v5 Pine).

Flujo:  Pine alert (JSON)  →  /api/webhook/tradingview  →  Risk Manager (VETO)
        →  (paper: solo valida y registra | live: ejecuta vía OrderExecutor)

Seguridad: por defecto NO ejecuta en real. Requiere broker conectado + paper=off
y, si se configura, un `secret` que coincida con WEBHOOK_SECRET.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.models.signal_models import TradingViewWebhook
from core.risk_manager import RiskManager, TradeRequest, RiskDecision

router = APIRouter()

# Risk Manager persistente para el flujo de webhooks (veto absoluto)
_risk = RiskManager({})
_log: list = []   # últimas señales recibidas (para depurar desde el frontend)


def _resp(data, t0):
    return {"success": True, "data": data,
            "meta": {"timestamp": datetime.utcnow().isoformat() + "Z",
                     "processing_time_ms": round((time.time() - t0) * 1000),
                     "version": "1.0.0"}, "errors": []}


def _f(d: dict, key: str):
    """Extrae un número de un dict anidado del JSON (vienen como string)."""
    try:
        return float(d.get(key)) if d and d.get(key) is not None else None
    except (TypeError, ValueError):
        return None


@router.post("/tradingview")
async def tradingview_webhook(wh: TradingViewWebhook):
    t0 = time.time()

    # 1) Token opcional anti-suplantación
    secret = os.getenv("WEBHOOK_SECRET", "")
    if secret and wh.secret != secret:
        raise HTTPException(status_code=401, detail="secret inválido")

    entry = wh.entry or {}
    risk = wh.risk or {}
    record = {"received_at": datetime.utcnow().isoformat() + "Z", "payload": wh.model_dump()}
    _log.append(record)
    del _log[:-50]   # conserva solo las últimas 50

    action = (wh.action or "").lower()

    # 2) Cierres (no pasan por sizing de riesgo)
    if action in ("close", "close_percent"):
        _risk.close_position(wh.ticker)
        return _resp({"status": "close_signal", "ticker": wh.ticker,
                      "percent": wh.percent or 100}, t0)

    # 3) Aperturas: mapea action → dirección
    if action == "buy":
        direction = "LONG"
    elif action == "sell":
        direction = "SHORT"
    else:
        raise HTTPException(status_code=400, detail=f"action no soportada: {wh.action}")

    entry_price = _f(entry, "price")
    stop_loss = _f(risk, "stop_loss")
    take_profit = _f(risk, "take_profit_1")
    if entry_price is None or stop_loss is None:
        raise HTTPException(status_code=400,
                            detail="Faltan entry.price o risk.stop_loss en el JSON")

    # 4) Tamaño base por confianza (más confianza → algo más de tamaño, con tope)
    base_pct = 0.05
    conf = wh.confidence if wh.confidence is not None else 70.0
    size_pct = max(0.02, min(0.10, base_pct * (conf / 70.0)))

    # 5) Risk Manager — VETO ABSOLUTO
    equity = float(os.getenv("ACCOUNT_EQUITY", "10000"))
    req = TradeRequest(
        symbol=wh.ticker, direction=direction, entry_price=entry_price,
        stop_loss=stop_loss, position_size_pct=size_pct,
        take_profit=take_profit, strategy_name=f"QBv5-{wh.engine}",
        correlation_group=_corr_group(wh.ticker),
    )
    decision = _risk.validate_trade(req, equity)

    result = {
        "ticker": wh.ticker, "direction": direction, "engine": wh.engine,
        "confidence": conf, "requested_size_pct": round(size_pct, 4),
        "risk_decision": decision.decision.value,
        "approved_size_pct": round(decision.approved_size_pct, 4),
        "rejection_reason": decision.rejection_reason,
        "warnings": decision.warnings,
        "entry": entry_price, "stop_loss": stop_loss, "take_profit": take_profit,
    }

    if decision.decision == RiskDecision.REJECTED:
        result["status"] = "rejected_by_risk"
        return _resp(result, t0)

    # 6) Ejecución real solo si hay broker live conectado (import diferido)
    executed = await _maybe_execute(req, decision, equity)
    result["status"] = "executed" if executed.get("ok") else "validated_paper"
    result["execution"] = executed
    _risk.record_trade(wh.ticker, direction, decision.approved_size_pct,
                       entry_price, stop_loss, _corr_group(wh.ticker))
    return _resp(result, t0)


async def _maybe_execute(req: TradeRequest, decision, equity: float) -> dict:
    """Ejecuta en el broker activo solo si está en modo live. Si no, paper."""
    try:
        from api.routes.broker import _active_broker
    except Exception:
        _active_broker = None
    if _active_broker is None or _active_broker.is_paper():
        return {"ok": False, "mode": "paper", "note": "Sin broker live: solo validación."}
    try:
        from broker.order_executor import OrderExecutor
        executor = OrderExecutor(_active_broker, _risk)
        out = await executor.execute_signal(
            symbol=req.symbol, direction=req.direction, entry_price=req.entry_price,
            stop_loss=req.stop_loss, position_size_pct=decision.approved_size_pct,
            equity=equity, take_profit=req.take_profit,
            strategy_name=req.strategy_name, correlation_group=req.correlation_group)
        return {"ok": out.get("status") not in ("error", "rejected"), "mode": "live", **out}
    except Exception as e:
        return {"ok": False, "mode": "live", "error": str(e)}


def _corr_group(ticker: str) -> str:
    """Agrupa por correlación para el límite MAX_CORRELATED_EXPOSURE."""
    t = ticker.upper()
    if any(t.startswith(x) for x in ("BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX")):
        return "crypto"
    if t.endswith("=X") or len(t) == 6 and t.isalpha():
        return "forex"
    if t.endswith("=F"):
        return "futures"
    return "equities"


@router.get("/log")
async def webhook_log():
    t0 = time.time()
    return _resp({"recent": _log[-20:], "risk_status": _risk.status()}, t0)
