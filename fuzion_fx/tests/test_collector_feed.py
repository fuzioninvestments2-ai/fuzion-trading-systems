"""
tests/test_collector_feed.py (fuzion_fx)
========================================
Valida CandleStore, CandleAggregator, CandleStoreFeed y el feedback loop de
BaseBot (resolve_pending). SIN red (sqlite temporal + velas sinteticas).
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from collector.candle_store import CandleStore                 # noqa: E402
from collector.aggregator import CandleAggregator              # noqa: E402
from data.price_feed import CandleStoreFeed                    # noqa: E402
from core.results_store import ResultsStore                    # noqa: E402
from bots.base_bot import BaseBot                              # noqa: E402


def test_aggregator_arma_y_cierra_velas() -> None:
    agg = CandleAggregator([60])
    # Ticks dentro del bucket [0,60): no cierra; en 60 cierra la primera.
    assert agg.add_tick("EUR/USD", 0, 1.10) == []
    agg.add_tick("EUR/USD", 10, 1.12)          # high
    agg.add_tick("EUR/USD", 20, 1.09)          # low
    cerradas = agg.add_tick("EUR/USD", 60, 1.11)   # nuevo bucket -> cierra [0,60)
    assert len(cerradas) == 1
    pair, tf, bucket, ohlc = cerradas[0]
    # close = ULTIMO tick del bucket [0,60) = 1.09 (ts=20); el 1.11 abre la nueva.
    assert bucket == 0 and ohlc["open"] == 1.10 and ohlc["high"] == 1.12
    assert ohlc["low"] == 1.09 and ohlc["close"] == 1.09
    # La vela en formacion ahora es la de bucket 60, con open=close=1.11.
    b2, cur = agg.current("EUR/USD", 60)
    assert b2 == 60 and cur["open"] == 1.11


def test_candle_store_upsert_y_get() -> None:
    st = CandleStore(":memory:")
    for i, c in enumerate([1.10, 1.11, 1.12]):
        st.upsert_candle("EUR/USD", 60, i * 60, c, c, c, c, 5)
    got = st.get_candles("EUR/USD", 60, 10)
    assert got["close"] == [1.10, 1.11, 1.12]          # cronologico
    # upsert sobre la misma (pair,tf,ts) reescribe, no duplica.
    st.upsert_candle("EUR/USD", 60, 0, 1.10, 1.20, 1.05, 1.15, 9)
    assert st.get_candles("EUR/USD", 60, 10)["close"][0] == 1.15
    # price_at: primer cierre con ts >= pedido.
    assert st.price_at("EUR/USD", 60, 60) == 1.11


def test_feed_lee_del_store() -> None:
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "po_candles.db")
    st = CandleStore(db)
    for i, c in enumerate([1.10, 1.11, 1.12]):
        st.upsert_candle("EUR/USD", 60, i * 60, c, c, c, c, 1)
    feed = CandleStoreFeed(db)
    got = feed.get_candles("EUR/USD", 60)
    assert got["close"] == [1.10, 1.11, 1.12]
    # Par sin datos -> None.
    assert feed.get_candles("GBP/USD", 60) is None


def test_feed_sin_archivo_devuelve_none() -> None:
    feed = CandleStoreFeed("/ruta/que/no/existe/po_candles.db")
    assert feed.get_candles("EUR/USD", 60) is None       # colector no arranco


def test_resolve_pending_aprende() -> None:
    # Store de velas con un CALL que ACIERTA (precio sube al vencimiento).
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "po_candles.db")
    cs = CandleStore(db)
    cs.upsert_candle("EUR/USD", 60, 1000, 1.10, 1.10, 1.10, 1.10, 1)   # entrada
    cs.upsert_candle("EUR/USD", 60, 1060, 1.12, 1.12, 1.12, 1.12, 1)   # vencimiento (subio)

    st = ResultsStore(":memory:")
    bot = BaseBot("f1_m1", price_feed=CandleStoreFeed(db), store=st)
    # Registrar una senal CALL a las 1000 con precio 1.10 (vence en 1060).
    sid = st.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                          "direction": "CALL", "setup_id": "CALL|ema,macd,rsi",
                          "confirmations": 3, "price": 1.10, "atr": 0.001})
    # A las 1200 ya vencio -> resuelve como WIN.
    n = bot.resolve_pending(now=1200.0)
    assert n == 1
    assert st.setup_stats("CALL|ema,macd,rsi") == {"trades": 1, "wins": 1,
                                                    "losses": 0, "win_pct": 100.0}


def _run_all() -> None:
    tests = [test_aggregator_arma_y_cierra_velas, test_candle_store_upsert_y_get,
             test_feed_lee_del_store, test_feed_sin_archivo_devuelve_none,
             test_resolve_pending_aprende]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
