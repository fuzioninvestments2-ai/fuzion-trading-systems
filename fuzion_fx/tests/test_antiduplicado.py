"""
tests/test_antiduplicado.py (fuzion_fx)
=======================================
Valida el anti-duplicado RE-ARMADO de scan_once:
  - misma direccion DENTRO del ciclo del timeframe -> NO re-emite,
  - misma direccion una vez VENCIDA (paso un ciclo) -> re-emite,
  - direccion OPUESTA -> emite al toque.
SIN red (feed en memoria, sin notifier real, timers off).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                    # noqa: E402
from core.signal_engine import CALL, PUT                       # noqa: E402
from data.price_feed import InMemoryPriceFeed                  # noqa: E402
from bots.base_bot import BaseBot                              # noqa: E402


class _FixedEngine:
    """Devuelve SIEMPRE la misma direccion (configurable en .dir)."""
    def __init__(self, direction):
        self.dir = direction

    def analyze(self, candles):
        return {"signal": self.dir, "confirmations": 3, "votes": {},
                "confirming": ["ema", "macd", "rsi"],
                "setup_id": f"{self.dir}|ema,macd,rsi", "atr": 0.0004,
                "price": 1.10, "readings": {"rsi": 25.0, "macd_hist": 0.0001}}


def _bot():
    feed = InMemoryPriceFeed()
    c = [1.10 + 0.0001 * i for i in range(40)]
    feed.set_candles("EUR/USD", {"open": c, "high": [x + 0.0002 for x in c],
                                 "low": [x - 0.0002 for x in c], "close": c})
    bot = BaseBot("f1_m1", price_feed=feed, store=ResultsStore(":memory:"))
    bot.pairs = ["EUR/USD"]
    bot.prefilter_seconds = 0
    bot._schedule_enabled = False
    bot.engine = _FixedEngine(CALL)
    return bot


def test_misma_direccion_dentro_del_ciclo_no_reemite() -> None:
    bot = _bot()                                   # timeframe_seconds = 60
    assert len(bot.scan_once(now=1000.0)) == 1     # primera CALL: emite
    assert bot.scan_once(now=1030.0) == []         # +30s (<60): NO re-emite
    assert bot.scan_once(now=1059.0) == []         # +59s (<60): NO re-emite


def test_misma_direccion_vencida_reemite() -> None:
    bot = _bot()
    assert len(bot.scan_once(now=1000.0)) == 1     # emite
    assert len(bot.scan_once(now=1060.0)) == 1     # +60s (>=ciclo): re-emite


def test_direccion_opuesta_emite_al_toque() -> None:
    bot = _bot()
    assert len(bot.scan_once(now=1000.0)) == 1     # CALL emite
    bot.engine.dir = PUT                            # gira a PUT
    emit = bot.scan_once(now=1010.0)               # +10s (<ciclo) pero opuesta
    assert len(emit) == 1 and emit[0]["direction"] == PUT


def test_tendencia_varias_seguidas() -> None:
    # Tendencia CALL: emite una por ciclo, no se calla del todo.
    bot = _bot()
    emitidas = 0
    for k in range(3):                             # 3 ciclos de 60s
        emitidas += len(bot.scan_once(now=1000.0 + 60.0 * k))
    assert emitidas == 3                           # una CALL por ciclo


def _run_all() -> None:
    tests = [test_misma_direccion_dentro_del_ciclo_no_reemite,
             test_misma_direccion_vencida_reemite,
             test_direccion_opuesta_emite_al_toque,
             test_tendencia_varias_seguidas]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
