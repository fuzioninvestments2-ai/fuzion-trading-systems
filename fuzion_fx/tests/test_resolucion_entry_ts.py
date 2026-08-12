"""
tests/test_resolucion_entry_ts.py (fuzion_fx)
=============================================
Valida la CORRECCION del bug "da win y es loss + horarios/niveles cruzados":

  1) La senal guarda el borde de entrada (entry_ts) que ANUNCIA la tarjeta.
  2) resolve_pending liquida contra la vela del entry_ts GUARDADO, no contra un
     borde recalculado desde ts (que podia caer en OTRA vela tras el pre-filtro).
  3) El win/loss se decide por la vela real operada (open=entrada, close=cierre).

Antes, la tarjeta calculaba el borde con datetime.now() (post pre-filtro) y
resolve_pending lo recalculaba desde ts (inicio del escaneo): si un borde de vela
caia en el medio, se anunciaba una vela y se liquidaba otra -> WIN cuando era LOSS
y horarios distintos a los de la operacion. SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                     # noqa: E402
from bots.base_bot import BaseBot                               # noqa: E402


class _FeedLiquidacion:
    """Feed con real_candle_at por bucket exacto (lo que usa resolve_pending)."""

    def __init__(self, reales):
        # reales = {(pair, tf, bucket): (open, close)}
        self._reales = reales

    def get_candles(self, pair, tf, count=200):
        return None                                # no se emite en estos tests

    def get_payout(self, pair):
        return 85.0

    def real_candle_at(self, pair, tf, bucket):
        return self._reales.get((pair, int(tf), int(bucket)))


def _bot(feed) -> BaseBot:
    bot = BaseBot("f1_m1", price_feed=feed, store=ResultsStore(":memory:"))
    bot.null_grace_seconds = 600
    return bot


def test_liquida_contra_entry_ts_guardado_no_recalculado() -> None:
    """
    Senal con ts=1000 pero entry_ts=1200 (como si un borde hubiera caido durante
    el pre-filtro). El borde legado desde ts seria 1020. La vela real existe SOLO
    en 1200. resolve_pending DEBE usar 1200 (guardado) y resolver; si usara 1020
    (bug), no encontraria vela y no resolveria.
    """
    tf = 60
    # Vela operada en 1200: abre 1.10000, cierra 1.09000 (BAJO) -> CALL = LOSS.
    feed = _FeedLiquidacion({("EUR/USD", tf, 1200): (1.10000, 1.09000)})
    bot = _bot(feed)
    bot.timeframe_seconds = tf
    bot.timeframe = "1m"
    sid = bot.store.save_signal({
        "ts": 1000, "pair": "EUR/USD", "timeframe": "1m", "direction": "CALL",
        "setup_id": "CALL|ema", "confirmations": 3, "price": 1.10, "atr": 0.001,
        "entry_ts": 1200})

    n = bot.resolve_pending(now=2000.0)
    assert n == 1                                  # resolvio (uso el 1200 guardado)
    # CALL con cierre por debajo de la entrada = LOSS (antes daba WIN).
    assert bot.store.win_rate("EUR/USD") == {"trades": 1, "wins": 0, "win_pct": 0.0}
    st = bot.store.setup_stats("CALL|ema")
    assert st["losses"] == 1 and st["wins"] == 0
    _ = sid


def test_call_gana_si_sube_pierde_si_baja() -> None:
    """La direccion se decide por la vela real: CALL gana si close>open."""
    tf = 60
    feed = _FeedLiquidacion({
        ("EUR/USD", tf, 1200): (1.10000, 1.10050),   # sube -> CALL win
        ("GBP/USD", tf, 1200): (1.30000, 1.29950),   # baja -> CALL loss
    })
    bot = _bot(feed)
    bot.timeframe_seconds = tf
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s1", "confirmations": 3,
                           "price": 1.10, "atr": 0.001, "entry_ts": 1200})
    bot.store.save_signal({"ts": 1000, "pair": "GBP/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s2", "confirmations": 3,
                           "price": 1.30, "atr": 0.001, "entry_ts": 1200})
    bot.resolve_pending(now=2000.0)
    assert bot.store.win_rate("EUR/USD")["win_pct"] == 100.0
    assert bot.store.win_rate("GBP/USD")["win_pct"] == 0.0


def test_put_gana_si_baja() -> None:
    tf = 60
    feed = _FeedLiquidacion({("EUR/USD", tf, 1200): (1.10000, 1.09900)})  # baja
    bot = _bot(feed)
    bot.timeframe_seconds = tf
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "PUT", "setup_id": "s", "confirmations": 3,
                           "price": 1.10, "atr": 0.001, "entry_ts": 1200})
    bot.resolve_pending(now=2000.0)
    assert bot.store.win_rate("EUR/USD")["win_pct"] == 100.0   # PUT + bajo = win


def test_sin_vela_real_no_resuelve_pasado_grace_nula() -> None:
    """Sin vela real de la operacion: pasado el grace, NULA (no inventa un cierre)."""
    tf = 60
    feed = _FeedLiquidacion({})                      # ninguna vela real
    bot = _bot(feed)
    bot.timeframe_seconds = tf
    bot.null_grace_seconds = 10
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s", "confirmations": 3,
                           "price": 1.10, "atr": 0.001, "entry_ts": 1200})
    # expiry = 1260; now muy posterior -> supera el grace -> NULA.
    n = bot.resolve_pending(now=5000.0)
    assert n == 0                                    # las nulas no cuentan como reales
    assert bot.store.win_rate("EUR/USD")["trades"] == 0   # NULL fuera de win-rate


def test_fallback_legado_sin_entry_ts() -> None:
    """Senales viejas sin entry_ts: se recalcula el borde desde ts (compat)."""
    tf = 60
    # ts=1000 -> borde legado = 1020. Vela real en 1020.
    feed = _FeedLiquidacion({("EUR/USD", tf, 1020): (1.10000, 1.10050)})
    bot = _bot(feed)
    bot.timeframe_seconds = tf
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s", "confirmations": 3,
                           "price": 1.10, "atr": 0.001})    # sin entry_ts
    n = bot.resolve_pending(now=2000.0)
    assert n == 1 and bot.store.win_rate("EUR/USD")["win_pct"] == 100.0


def _run_all() -> None:
    tests = [test_liquida_contra_entry_ts_guardado_no_recalculado,
             test_call_gana_si_sube_pierde_si_baja,
             test_put_gana_si_baja,
             test_sin_vela_real_no_resuelve_pasado_grace_nula,
             test_fallback_legado_sin_entry_ts]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
