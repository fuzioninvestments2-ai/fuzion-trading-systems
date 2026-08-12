"""
tests/test_integracion_e2e.py (fuzion_fx)
=========================================
Prueba de COORDINACION de la automatizacion, de punta a punta y SIN red:

    colector real -> po_candles.db real -> bot real (feed real) -> EMITE -> RESUELVE

Usa las piezas REALES (PocketOptionCollector, CandleStore, CandleStoreFeed,
BaseBot), no mocks del nucleo. Inyecta los payloads que Pocket Option manda
(updateAssets con el pago, on_history con las velas) y verifica que:

  1) el colector guarda pago + velas reales en la base compartida,
  2) el bot LEE esa base y EMITE una senal (la cadena completa funciona),
  3) la senal se RESUELVE contra la vela operada con el resultado correcto.

Esto es lo que fallaba en vivo: aunque hubiera datos y pago, con
min_confirmations=3 el motor casi nunca juntaba 3 votos (0.6% de los patrones) y
la cadena quedaba muda. Con 2, fluye. Este test lo deja clavado.
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)
_REPO_ROOT = os.path.dirname(_RAIZ)
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

from collector.po_collector import PocketOptionCollector, _po_code   # noqa: E402
from data.price_feed import CandleStoreFeed                          # noqa: E402
from core.results_store import ResultsStore                          # noqa: E402
from bots.base_bot import BaseBot                                    # noqa: E402


def _payload_assets(code: str, pago: int):
    """updateAssets tal como PO lo manda: [id, SYMBOL, nombre, ..., pago, ...].
    El pago cae en el indice 5 (uno de los preferidos de bot/payout.py)."""
    return [[1, code, "par", 0, 0, pago, 1]]


def _payload_history(code: str, period: int, base_ts: int, closes):
    """on_history con velas OHLC (dicts) — subida/bajada suave segun `closes`."""
    velas = []
    for i, c in enumerate(closes):
        velas.append({"time": base_ts + period * i, "open": c,
                      "high": c + 2e-4, "low": c - 2e-4, "close": c, "volume": 1})
    return {"asset": code, "period": period, "candles": velas}


def test_cadena_completa_emite_y_resuelve() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        # --- 1) COLECTOR real escribe pago + velas reales en la base compartida ---
        col = PocketOptionCollector('42["auth",{"session":"x"}]', db_path=tmp.name)
        tf = 60
        code = _po_code("EUR/USD", col.mercado)          # 'EURUSD' o 'EURUSD_otc'

        col._on_assets(_payload_assets(code, 85))        # pago 85% (en banda 72-92)
        assert col.store.get_payout("EUR/USD") == 85.0

        base_ts = 60_000_000                              # multiplo de tf (bucket=time)
        closes = [1.1000 + 0.00006 * i for i in range(40)]   # subida suave -> CALL
        col._on_history(_payload_history(code, tf, base_ts, closes))
        reales = col.store.get_real_candles("EUR/USD", tf)
        assert reales is not None and len(reales["close"]) == 40

        # --- 2) BOT real LEE esa base (feed real) y EMITE ---
        bot = BaseBot("f1_m1", price_feed=CandleStoreFeed(tmp.name),
                      store=ResultsStore(":memory:"))     # sin notifier -> dry-run
        bot.pairs = ["EUR/USD"]
        bot.timeframe_seconds = tf
        bot.timeframe = "1m"
        bot.prefilter_seconds = 0                         # sin espera real
        bot._schedule_enabled = False                     # sin timers de fondo

        emitidas = bot.scan_once()
        assert len(emitidas) == 1, f"la cadena no emitio: {emitidas}"
        senal = emitidas[0]
        assert senal["direction"] == "CALL"
        assert senal["pair"] == "EUR/USD"
        assert senal.get("entry_ts")                      # borde de entrada guardado

        # --- 3) RESUELVE contra la vela operada (open->close). Sube -> CALL = WIN ---
        entry_border = int(senal["entry_ts"])
        col.store.upsert_real_candle("EUR/USD", tf, entry_border,
                                     o=1.10500, h=1.10600, l=1.10480, c=1.10560)
        n = bot.resolve_pending(now=entry_border + 10 * tf)
        assert n == 1, "no resolvio la senal vencida"
        assert bot.store.win_rate("EUR/USD")["win_pct"] == 100.0   # subio -> WIN

        col.store.close()
    finally:
        os.unlink(tmp.name)


def test_cadena_bloquea_por_pago_fuera_de_banda() -> None:
    """Coordinacion inversa: si el pago esta FUERA de 72-92, la cadena NO emite."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = PocketOptionCollector('42["auth",{"session":"x"}]', db_path=tmp.name)
        tf = 60
        code = _po_code("EUR/USD", col.mercado)
        col._on_assets(_payload_assets(code, 40))         # 40% -> por debajo de 53
        base_ts = 60_000_000
        closes = [1.1000 + 0.00006 * i for i in range(40)]
        col._on_history(_payload_history(code, tf, base_ts, closes))

        bot = BaseBot("f1_m1", price_feed=CandleStoreFeed(tmp.name),
                      store=ResultsStore(":memory:"))
        bot.pairs = ["EUR/USD"]
        bot.timeframe_seconds = tf
        bot.prefilter_seconds = 0
        bot._schedule_enabled = False
        assert bot.scan_once() == []                       # pago bajo -> no emite
        col.store.close()
    finally:
        os.unlink(tmp.name)


def test_tarjeta_salud_refleja_estado() -> None:
    """La tarjeta de salud dice, en claro, si busca o que lo frena."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = PocketOptionCollector('42["auth",{"session":"x"}]', db_path=tmp.name)
        tf = 60
        code = _po_code("EUR/USD", col.mercado)
        bot = BaseBot("f1_m1", price_feed=CandleStoreFeed(tmp.name),
                      store=ResultsStore(":memory:"))
        bot.pairs = ["EUR/USD"]
        bot.timeframe_seconds = tf

        # Sin nada aun: sin datos.
        e0 = bot.estado_operativo()
        assert e0["con_datos"] == 0 and e0["en_banda"] == []
        assert "Sin velas" in bot._tarjeta_salud("arranque")

        # Con pago en banda + velas: operativo.
        col._on_assets(_payload_assets(code, 85))
        col._on_history(_payload_history(
            code, tf, 60_000_000, [1.1000 + 0.00006 * i for i in range(40)]))
        e1 = bot.estado_operativo()
        assert e1["con_datos"] == 1
        assert any(p == "EUR/USD" for p, _ in e1["en_banda"])
        assert "Operativo" in bot._tarjeta_salud("latido (1h)")
        col.store.close()
    finally:
        os.unlink(tmp.name)


def _run_all() -> None:
    tests = [test_cadena_completa_emite_y_resuelve,
             test_cadena_bloquea_por_pago_fuera_de_banda,
             test_tarjeta_salud_refleja_estado]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
