"""Sistema de alertas — email + webhook (Discord/Slack/Telegram). Rate limiting 5min."""
from __future__ import annotations
import json
import time
from datetime import datetime
from enum import Enum
from typing import Dict, Optional
import httpx


class AlertType(Enum):
    TRADE_EXECUTED = "TRADE_EXECUTED"
    REGIME_CHANGE = "REGIME_CHANGE"
    CIRCUIT_BREAKER_ACTIVATED = "CIRCUIT_BREAKER_ACTIVATED"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    ERROR = "ERROR"
    POSITION_AT_RISK = "POSITION_AT_RISK"


class AlertManager:
    def __init__(self, config: dict):
        self._webhook_url: str = config.get("webhook_url", "")
        self._email_enabled: bool = config.get("email_enabled", False)
        self._rate_limit_seconds: int = config.get("rate_limit_minutes", 5) * 60
        self._last_sent: Dict[str, float] = {}

    def send_alert(self, alert_type: str, message: str, urgency: str = "normal",
                   **extra) -> bool:
        if not self._should_send(alert_type):
            return False

        payload = {
            "alert_type": alert_type,
            "message": message,
            "urgency": urgency,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **extra,
        }

        success = False
        if self._webhook_url:
            success = self._send_webhook(payload)
        if self._email_enabled:
            self._send_email(payload)

        self._last_sent[alert_type] = time.time()
        return success

    def trade_executed(self, symbol: str, direction: str, price: float, qty: float):
        self.send_alert(AlertType.TRADE_EXECUTED.value,
                        f"Trade ejecutado: {direction} {qty} {symbol} @ ${price}",
                        symbol=symbol, direction=direction, price=price, qty=qty)

    def regime_change(self, symbol: str, old_regime: str, new_regime: str, prob: float):
        self.send_alert(AlertType.REGIME_CHANGE.value,
                        f"Cambio de régimen {symbol}: {old_regime} → {new_regime} ({prob:.0%})",
                        urgency="high", symbol=symbol, old=old_regime, new=new_regime)

    def circuit_breaker(self, state: str, pnl_pct: float):
        self.send_alert(AlertType.CIRCUIT_BREAKER_ACTIVATED.value,
                        f"CIRCUIT BREAKER ACTIVADO: {state} | PnL: {pnl_pct:.2%}",
                        urgency="critical", state=state, pnl_pct=pnl_pct)

    def daily_summary(self, trades: int, pnl: float, equity: float):
        self.send_alert(AlertType.DAILY_SUMMARY.value,
                        f"Resumen diario — Trades: {trades} | PnL: ${pnl:,.2f} | Equity: ${equity:,.2f}",
                        trades=trades, pnl=pnl, equity=equity)

    def _should_send(self, alert_type: str) -> bool:
        last = self._last_sent.get(alert_type, 0)
        return (time.time() - last) >= self._rate_limit_seconds

    def _send_webhook(self, payload: dict) -> bool:
        try:
            text = f"[FUZION] {payload['alert_type']}: {payload['message']}"
            response = httpx.post(
                self._webhook_url,
                json={"content": text, "embeds": [{"description": json.dumps(payload, indent=2)[:2000]}]},
                timeout=10,
            )
            return response.status_code in (200, 204)
        except Exception:
            return False

    def _send_email(self, payload: dict) -> bool:
        # Implementación via SMTP cuando se configure
        return False
