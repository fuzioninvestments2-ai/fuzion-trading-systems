"""
tests/test_store_learning_bot.py (fuzion_fx)
============================================
Valida ResultsStore + LearningEngine + el loop de BaseBot (scan_once) de punta a
punta, SIN red (sqlite en memoria, feed en memoria, sin notifier=dry-run).
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                     # noqa: E402
from core.learning_engine import LearningEngine, DISCARD, PRIORITIZE  # noqa: E402
from core.signal_engine import CALL                             # noqa: E402
from data.price_feed import InMemoryPriceFeed, StubPriceFeed    # noqa: E402
from bots.base_bot import BaseBot                               # noqa: E402


def test_store_guarda_resuelve_y_winrate() -> None:
    st = ResultsStore(":memory:")
    sid = st.save_signal({"pair": "EUR/USD", "timeframe": "1m", "direction": "CALL",
                          "setup_id": "CALL|ema,macd,rsi", "confirmations": 3,
                          "price": 1.10, "atr": 0.001})
    st.resolve_signal(sid, "win", pnl=8.0)
    assert st.win_rate("EUR/USD")["win_pct"] == 100.0
    assert st.setup_stats("CALL|ema,macd,rsi")["trades"] == 1


def test_learning_descarta_y_prioriza() -> None:
    st = ResultsStore(":memory:")
    setup = "CALL|ema,macd,rsi"
    # 10 trades, 3 wins (30%) -> por debajo de 40 -> DISCARD.
    for i in range(10):
        sid = st.save_signal({"pair": "EUR/USD", "direction": "CALL",
                              "setup_id": setup, "confirmations": 3})
        st.resolve_signal(sid, "win" if i < 3 else "loss")
    lrn = LearningEngine(st, {"min_trades_for_setup_evaluation": 10,
                              "discard_setup_below_win_pct": 40,
                              "prioritize_setup_above_win_pct": 70})
    assert lrn.evaluate_setup(setup)["verdict"] == DISCARD
    assert lrn.should_emit(setup) is False

    # Otro setup 8/10 (80%) -> PRIORITIZE.
    bueno = "CALL|ema,macd,bollinger"
    for i in range(10):
        sid = st.save_signal({"pair": "EUR/USD", "direction": "CALL",
                              "setup_id": bueno, "confirmations": 3})
        st.resolve_signal(sid, "win" if i < 8 else "loss")
    assert lrn.evaluate_setup(bueno)["verdict"] == PRIORITIZE
    assert lrn.is_prioritized(bueno) is True


def test_learning_muestra_insuficiente_deja_pasar() -> None:
    st = ResultsStore(":memory:")
    lrn = LearningEngine(st, {"min_trades_for_setup_evaluation": 10,
                              "discard_setup_below_win_pct": 40,
                              "prioritize_setup_above_win_pct": 70})
    # Sin datos: no se juzga, se deja emitir.
    assert lrn.should_emit("CALL|ema,macd,rsi") is True


class _FakeEngine:
    """Devuelve CALL para el primer par y NEUTRAL para el resto."""
    def __init__(self, par_call):
        self.par_call = par_call
        self.n = 0

    def analyze(self, candles):
        # El primer par consultado dispara CALL; los demas NEUTRAL.
        self.n += 1
        # CALL en la 1a (scan) y la 2a (pre-filtro) llamada del primer par; luego
        # NEUTRAL. Asi el pre-filtro confirma y se emite una sola senal.
        if self.n <= 2:
            return {"signal": CALL, "confirmations": 3, "votes": {},
                    "confirming": ["ema", "macd", "rsi"],
                    "setup_id": "CALL|ema,macd,rsi", "atr": 0.001, "price": 1.10,
                    "readings": {"rsi": 25.0, "macd_hist": 0.0001}}
        return {"signal": "NEUTRAL", "confirmations": 0, "votes": {},
                "confirming": [], "setup_id": None, "atr": 0.0, "price": 1.10,
                "readings": {"rsi": 50.0, "macd_hist": 0.0}}


def _candles():
    c = list(np.linspace(1.10, 1.11, 60))
    return {"open": c, "high": c, "low": c, "close": c}


def test_base_bot_stub_no_emite() -> None:
    # Con el feed placeholder (None) el bot no emite nada (seguro).
    bot = BaseBot("f1_m1", price_feed=StubPriceFeed(), store=ResultsStore(":memory:"))
    assert bot.scan_once() == []


def test_base_bot_emite_y_persiste() -> None:
    feed = InMemoryPriceFeed()
    st = ResultsStore(":memory:")
    bot = BaseBot("f1_m1", price_feed=feed, store=st)   # sin notifier -> dry-run
    bot.pairs = ["AUD/CAD"]                              # un solo par para el test
    bot.prefilter_seconds = 0                           # sin espera real
    bot._schedule_enabled = False                       # sin timers de fondo
    for p in bot.pairs:
        feed.set_candles(p, _candles())
    bot.engine = _FakeEngine(bot.pairs[0])              # fuerza un CALL controlado

    emitidas = bot.scan_once(now=1000.0)
    assert len(emitidas) == 1                            # solo el primer par
    assert emitidas[0]["direction"] == "CALL"
    # Persistio en el store.
    assert st.win_rate()["trades"] == 0                 # aun sin resolver
    assert st.setup_stats("CALL|ema,macd,rsi")["trades"] == 0   # no resuelto
    # El rate-limit cuenta la emision.
    assert len(bot._emitted_ts) == 1


def _run_all() -> None:
    tests = [test_store_guarda_resuelve_y_winrate, test_learning_descarta_y_prioriza,
             test_learning_muestra_insuficiente_deja_pasar,
             test_base_bot_stub_no_emite, test_base_bot_emite_y_persiste]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
