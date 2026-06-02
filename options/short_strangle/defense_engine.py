from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class DefenseSignal:
    symbol: str
    action: str
    reason: str
    urgency: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"


class DefenseEngine:
    MAX_DELTA = 0.30
    MAX_SD_MOVE = 1.5
    CIRCUIT_BREAKER_LOSSES = 3

    def __init__(self):
        self._loss_streak: int = 0

    def check_defense(self, symbol: str, current_delta: float,
                      underlying_price: float, entry_price: float,
                      iv: float, dte: int) -> DefenseSignal:
        if self._loss_streak >= self.CIRCUIT_BREAKER_LOSSES:
            return DefenseSignal(symbol, "CIRCUIT_BREAKER",
                                 f"{self._loss_streak} consecutive losses — halt trading",
                                 "CRITICAL")

        daily_sd = entry_price * iv / math.sqrt(252)
        total_sd = daily_sd * math.sqrt(max(dte, 1))
        move = abs(underlying_price - entry_price)
        sd_move = move / total_sd if total_sd > 0 else 0

        if abs(current_delta) > self.MAX_DELTA:
            return DefenseSignal(symbol, "CLOSE",
                                 f"Delta {current_delta:.2f} breached {self.MAX_DELTA}",
                                 "HIGH")

        if sd_move > self.MAX_SD_MOVE:
            return DefenseSignal(symbol, "CLOSE",
                                 f"Underlying moved {sd_move:.1f} SD from entry",
                                 "HIGH")

        if abs(current_delta) > 0.22:
            return DefenseSignal(symbol, "ROLL",
                                 f"Delta {current_delta:.2f} approaching threshold",
                                 "MEDIUM")

        return DefenseSignal(symbol, "HOLD", "Within parameters", "LOW")

    def record_loss(self) -> None:
        self._loss_streak += 1

    def record_win(self) -> None:
        self._loss_streak = 0

    def reset_circuit_breaker(self) -> None:
        self._loss_streak = 0
