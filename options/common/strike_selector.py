"""Strike Selector — selección óptima de strikes por estrategia."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .chain_models import ChainData, OptionContract


@dataclass
class SelectedStrikes:
    strategy_type: str
    legs: List[OptionContract]
    total_credit: float = 0.0
    total_debit: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    pop: float = 0.0
    notes: List[str] = field(default_factory=list)


class StrikeSelector:
    def __init__(self, min_volume: int = 100, min_oi: int = 500,
                 max_spread_pct: float = 0.10):
        self._min_volume = min_volume
        self._min_oi = min_oi
        self._max_spread_pct = max_spread_pct

    def select_strike(self, chain: ChainData, strategy_type: str,
                      delta_target: float, dte_range: Tuple[int, int],
                      iv_environment: str = "normal") -> Optional[SelectedStrikes]:
        if not (dte_range[0] <= chain.dte <= dte_range[1]):
            return None

        liquid_calls = self._filter_liquid(chain.calls)
        liquid_puts = self._filter_liquid(chain.puts)

        strategy_type = strategy_type.lower()

        if strategy_type == "single_call":
            leg = self._nearest_delta(liquid_calls, delta_target)
            return SelectedStrikes("single_call", [leg]) if leg else None

        if strategy_type == "single_put":
            leg = self._nearest_delta(liquid_puts, delta_target)
            return SelectedStrikes("single_put", [leg]) if leg else None

        if strategy_type in ("bull_put", "bear_call", "bull_call", "bear_put"):
            return self._vertical_spread(chain, strategy_type, delta_target,
                                          liquid_calls, liquid_puts)

        if strategy_type == "iron_condor":
            return self._iron_condor(chain, delta_target, liquid_calls, liquid_puts)

        if strategy_type in ("straddle", "strangle"):
            return self._straddle_strangle(chain, strategy_type, delta_target,
                                            liquid_calls, liquid_puts)

        return None

    def _filter_liquid(self, contracts: List[OptionContract]) -> List[OptionContract]:
        return [c for c in contracts
                if c.volume >= self._min_volume
                and c.open_interest >= self._min_oi
                and not c.low_liquidity]

    @staticmethod
    def _nearest_delta(contracts: List[OptionContract], target: float) -> Optional[OptionContract]:
        if not contracts:
            return None
        return min(contracts, key=lambda c: abs(abs(c.delta_estimate) - abs(target)))

    def _vertical_spread(self, chain, strategy_type, delta_target,
                          liquid_calls, liquid_puts) -> Optional[SelectedStrikes]:
        if strategy_type == "bull_put":
            short = self._nearest_delta(liquid_puts, -delta_target)
            if not short:
                return None
            long_candidates = [p for p in liquid_puts if p.strike < short.strike]
            if not long_candidates:
                return None
            long = min(long_candidates, key=lambda p: abs(p.strike - (short.strike - 5)))
            credit = short.mid_price - long.mid_price
            width = short.strike - long.strike
            return SelectedStrikes("bull_put", [short, long],
                                   total_credit=round(credit * 100, 2),
                                   max_profit=round(credit * 100, 2),
                                   max_loss=round((width - credit) * 100, 2),
                                   pop=round(1 - abs(short.delta_estimate), 2))

        if strategy_type == "bear_call":
            short = self._nearest_delta(liquid_calls, delta_target)
            if not short:
                return None
            long_candidates = [c for c in liquid_calls if c.strike > short.strike]
            if not long_candidates:
                return None
            long = min(long_candidates, key=lambda c: abs(c.strike - (short.strike + 5)))
            credit = short.mid_price - long.mid_price
            width = long.strike - short.strike
            return SelectedStrikes("bear_call", [short, long],
                                   total_credit=round(credit * 100, 2),
                                   max_profit=round(credit * 100, 2),
                                   max_loss=round((width - credit) * 100, 2),
                                   pop=round(1 - delta_target, 2))
        return None

    def _iron_condor(self, chain, delta_target, liquid_calls, liquid_puts) -> Optional[SelectedStrikes]:
        put_short = self._nearest_delta(liquid_puts, -delta_target)
        call_short = self._nearest_delta(liquid_calls, delta_target)
        if not put_short or not call_short:
            return None

        put_longs = [p for p in liquid_puts if p.strike < put_short.strike]
        call_longs = [c for c in liquid_calls if c.strike > call_short.strike]
        if not put_longs or not call_longs:
            return None

        put_long = min(put_longs, key=lambda p: abs(p.strike - (put_short.strike - 5)))
        call_long = min(call_longs, key=lambda c: abs(c.strike - (call_short.strike + 5)))

        credit = (put_short.mid_price - put_long.mid_price +
                  call_short.mid_price - call_long.mid_price)
        put_width = put_short.strike - put_long.strike
        call_width = call_long.strike - call_short.strike
        max_loss = (max(put_width, call_width) - credit) * 100

        return SelectedStrikes("iron_condor", [put_long, put_short, call_short, call_long],
                               total_credit=round(credit * 100, 2),
                               max_profit=round(credit * 100, 2),
                               max_loss=round(max_loss, 2),
                               pop=round(1 - 2 * delta_target, 2))

    def _straddle_strangle(self, chain, strategy_type, delta_target,
                            liquid_calls, liquid_puts) -> Optional[SelectedStrikes]:
        if strategy_type == "straddle":
            atm_call = min(liquid_calls, key=lambda c: abs(c.delta_estimate - 0.5), default=None)
            atm_put = min(liquid_puts, key=lambda p: abs(p.delta_estimate + 0.5), default=None)
            if not atm_call or not atm_put:
                return None
            debit = (atm_call.mid_price + atm_put.mid_price) * 100
            return SelectedStrikes("straddle", [atm_call, atm_put],
                                   total_debit=round(debit, 2), max_loss=round(debit, 2))
        else:
            otm_call = self._nearest_delta(liquid_calls, delta_target)
            otm_put = self._nearest_delta(liquid_puts, -delta_target)
            if not otm_call or not otm_put:
                return None
            debit = (otm_call.mid_price + otm_put.mid_price) * 100
            return SelectedStrikes("strangle", [otm_call, otm_put],
                                   total_debit=round(debit, 2), max_loss=round(debit, 2))
