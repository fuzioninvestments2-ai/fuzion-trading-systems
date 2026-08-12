"""
tests/test_payout_filter.py (fuzion_fx)
=======================================
Valida el filtro de PAGO (Paso 5): el store guarda/lee el pago real; el bot NO
emite si el pago del activo esta por debajo del minimo (72%) o si no hay dato y
require=True; y la tarjeta muestra el pago REAL. SIN red.
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from collector.candle_store import CandleStore                 # noqa: E402
from core.results_store import ResultsStore                    # noqa: E402
from core.signal_engine import CALL                            # noqa: E402
from data.price_feed import InMemoryPriceFeed, CandleStoreFeed  # noqa: E402
from bots.base_bot import BaseBot                              # noqa: E402


class _FakeEngine:
    """CALL para el primer par (scan + pre-filtro), NEUTRAL despues."""
    def __init__(self):
        self.n = 0

    def analyze(self, candles):
        self.n += 1
        if self.n <= 2:
            return {"signal": CALL, "confirmations": 3, "votes": {},
                    "confirming": ["ema", "macd", "rsi"],
                    "setup_id": "CALL|ema,macd,rsi", "atr": 0.001, "price": 1.10,
                    "readings": {"rsi": 25.0, "macd_hist": 0.0001}}
        return {"signal": "NEUTRAL", "confirmations": 0, "votes": {},
                "confirming": [], "setup_id": None, "atr": 0.0, "price": 1.10,
                "readings": {"rsi": 50.0}}


def _candles():
    c = list(np.linspace(1.10, 1.11, 60))
    return {"open": c, "high": c, "low": c, "close": c}


def _bot(feed):
    bot = BaseBot("f1_m1", price_feed=feed, store=ResultsStore(":memory:"))
    bot.pairs = ["AUD/CAD"]
    bot.prefilter_seconds = 0
    bot._schedule_enabled = False
    bot.engine = _FakeEngine()
    feed_candles = _candles()
    if isinstance(feed, InMemoryPriceFeed):
        feed.set_candles("AUD/CAD", feed_candles)
    return bot


def test_store_payout_upsert_y_get() -> None:
    s = CandleStore(":memory:")
    assert s.get_payout("EUR/USD") is None
    s.upsert_payout("EUR/USD", 84.0, 1000)
    assert s.get_payout("EUR/USD") == 84.0
    s.upsert_payout("EUR/USD", 76.5, 1100)          # actualiza
    assert s.get_payout("EUR/USD") == 76.5
    s.close()


def test_pago_ok_logica() -> None:
    bot = _bot(InMemoryPriceFeed())
    bot.payout_min, bot.payout_max, bot.payout_require = 72.0, 100.0, True
    assert bot._pago_ok(72.0) is True
    assert bot._pago_ok(71.9) is False              # bajo el piso
    assert bot._pago_ok(95.0) is True
    assert bot._pago_ok(None) is False              # sin dato y require -> no
    bot.payout_require = False
    assert bot._pago_ok(None) is True               # sin dato y no require -> si


def test_no_emite_con_pago_bajo() -> None:
    feed = InMemoryPriceFeed()
    feed.set_payout("AUD/CAD", 40.0)                # bajo el minimo (banda 53-92)
    bot = _bot(feed)
    assert bot.scan_once(now=1000.0) == []          # filtrado por pago


def test_emite_con_pago_ok_y_tarjeta_muestra_real() -> None:
    feed = InMemoryPriceFeed()
    feed.set_payout("AUD/CAD", 88.0)                # pago bueno
    bot = _bot(feed)
    emitidas = bot.scan_once(now=1000.0)
    assert len(emitidas) == 1
    card = bot.build_card("AUD/CAD", {"signal": "CALL", "confirming": ["ema"],
                                      "atr": 0.001}, payout=88.0)
    assert "88%" in card                            # pago REAL, no el 85 fijo


def test_no_emite_sin_dato_de_pago_si_require() -> None:
    feed = InMemoryPriceFeed()
    feed.set_payout("AUD/CAD", None)                # sin dato
    bot = _bot(feed)
    bot.payout_require = True
    assert bot.scan_once(now=1000.0) == []


def test_feed_get_payout_desde_store() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        s = CandleStore(tmp.name)
        s.upsert_payout("EUR/USD", 80.0, 1000)
        s.close()
        feed = CandleStoreFeed(tmp.name)
        assert feed.get_payout("EUR/USD") == 80.0
        assert feed.get_payout("GBP/USD") is None
    finally:
        os.unlink(tmp.name)


def _run_all() -> None:
    tests = [test_store_payout_upsert_y_get, test_pago_ok_logica,
             test_no_emite_con_pago_bajo, test_emite_con_pago_ok_y_tarjeta_muestra_real,
             test_no_emite_sin_dato_de_pago_si_require, test_feed_get_payout_desde_store]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
