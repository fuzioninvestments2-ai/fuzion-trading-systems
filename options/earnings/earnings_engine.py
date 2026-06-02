"""Earnings plays: straddle/strangle alrededor de earnings."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import date

from options.common.chain_models import OptionContract


@dataclass
class EarningsSetup:
    symbol: str
    strategy: str           # "long_straddle" | "long_strangle" | "iron_condor"
    earnings_date: str
    entry_dte: int          # días antes de earnings para entrar
    exit_before_dte: int    # salir N días antes (evitar IV crush)
    expected_move: float    # movimiento esperado basado en opciones ATM
    net_debit: float
    legs: List[OptionContract]
    max_loss: float
    notes: str = ""


class EarningsEngine:
    """
    Earnings plays: aprovecha expansión de IV previa a earnings.
    IMPORTANTE: salir ANTES del anuncio para evitar IV crush, a menos que
    la estrategia sea explícitamente post-earnings.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.entry_dte = self.config.get("entry_dte", 7)          # entrar 7 días antes
        self.exit_before_dte = self.config.get("exit_before_dte", 1)   # salir 1 día antes
        self.min_iv_rank = self.config.get("min_iv_rank", 30)

    def compute_expected_move(self, atm_call: OptionContract, atm_put: OptionContract) -> float:
        """Movimiento esperado = precio straddle ATM."""
        return atm_call.mid_price + atm_put.mid_price

    def build_long_straddle(
        self,
        symbol: str,
        earnings_date: str,
        atm_call: OptionContract,
        atm_put: OptionContract,
        quantity: int = 1,
    ) -> EarningsSetup:
        expected_move = self.compute_expected_move(atm_call, atm_put)
        net_debit = (atm_call.ask + atm_put.ask) * 100 * quantity

        return EarningsSetup(
            symbol=symbol,
            strategy="long_straddle",
            earnings_date=earnings_date,
            entry_dte=self.entry_dte,
            exit_before_dte=self.exit_before_dte,
            expected_move=expected_move,
            net_debit=net_debit,
            legs=[atm_call, atm_put],
            max_loss=net_debit,
            notes=f"Expected move: ±{expected_move:.2f}",
        )

    def build_iron_condor_post_earnings(
        self,
        symbol: str,
        earnings_date: str,
        call_spread_legs: List[OptionContract],
        put_spread_legs: List[OptionContract],
        credit: float,
        quantity: int = 1,
    ) -> EarningsSetup:
        """Iron condor DESPUÉS de earnings cuando IV está alta."""
        max_loss = (call_spread_legs[0].strike - call_spread_legs[1].strike) * 100 * quantity - credit

        return EarningsSetup(
            symbol=symbol,
            strategy="iron_condor",
            earnings_date=earnings_date,
            entry_dte=0,
            exit_before_dte=0,
            expected_move=0.0,
            net_debit=-credit,
            legs=call_spread_legs + put_spread_legs,
            max_loss=max_loss,
            notes="Post-earnings IV crush play",
        )

    def find_earnings_plays(self, candidates: List[dict]) -> List[EarningsSetup]:
        """
        Scans candidates for 3 strategies:
        1. Pre-earnings IV expansion (long straddle 7 DTE before, exit day before)
        2. Through-earnings iron condor (sell condor into earnings, capture IV crush)
        3. Post-earnings direction (debit spread after announcement)
        Always close by morning after announcement.
        """
        plays = []
        for c in candidates:
            symbol = c.get("symbol")
            earnings_date = c.get("earnings_date", "")
            days_until = c.get("days_until", 0)
            atm_call = c.get("atm_call")
            atm_put = c.get("atm_put")
            if atm_call is None or atm_put is None:
                continue

            expected_move = self.compute_expected_move(atm_call, atm_put)
            hist_avg = c.get("historical_avg_move", expected_move)
            iv_rank = c.get("iv_rank", 0)

            if 5 <= days_until <= self.entry_dte and iv_rank >= 20:
                plays.append(self.build_long_straddle(symbol, earnings_date, atm_call, atm_put))

            call_spread = c.get("call_spread_legs")
            put_spread = c.get("put_spread_legs")
            credit = c.get("condor_credit", 0)
            if call_spread and put_spread and credit > 0 and days_until <= 2:
                plays.append(self.build_iron_condor_post_earnings(
                    symbol, earnings_date, call_spread, put_spread, credit))

        return plays

    def should_exit(self, setup: EarningsSetup, dte: int, current_pnl: float) -> tuple[bool, str]:
        if dte <= setup.exit_before_dte:
            return True, "approaching_earnings_exit"
        if current_pnl >= abs(setup.net_debit) * 0.5:
            return True, "profit_target"
        if current_pnl <= -abs(setup.net_debit) * 0.7:
            return True, "stop_loss"
        return False, ""
