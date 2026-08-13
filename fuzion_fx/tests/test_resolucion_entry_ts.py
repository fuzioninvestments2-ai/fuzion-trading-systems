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


def test_no_resuelve_antes_de_vencer() -> None:
    """No liquidar antes de que la vela operada CIERRE (aunque ya haya vela real):
    si PO mando la vela en formacion, esperar hasta el vencimiento."""
    tf = 60
    feed = _FeedLiquidacion({("EUR/USD", tf, 1200): (1.10000, 1.10050)})
    bot = _bot(feed)
    bot.timeframe_seconds = tf
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s", "confirmations": 3,
                           "price": 1.10, "atr": 0.001, "entry_ts": 1200})
    # expiry = 1260. now=1250 (< expiry) -> NO resuelve todavia.
    assert bot.resolve_pending(now=1250.0) == 0
    assert bot.store.win_rate("EUR/USD")["trades"] == 0
    # now=1300 (>= expiry) -> ahora si resuelve.
    assert bot.resolve_pending(now=1300.0) == 1


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


def test_entry_border_anclado_a_grilla_de_po() -> None:
    """El borde de entrada se ancla a la ULTIMA vela real (reloj de PO), no al
    reloj del PC. Si el PC va atrasado, igual se opera la vela siguiente a la
    ultima real -> hora anunciada y vela liquidada en el MISMO reloj (sin desfase).
    """
    tf = 60
    bot = _bot(_FeedLiquidacion({}))
    bot.timeframe_seconds = tf
    # Ultima vela real conocida en PO: bucket 6000 (cerrada). PC atrasado: emitido
    # cae en la grilla 3000 (borde local 3060), MUY por detras de PO.
    candles = {"ts": [5880, 5940, 6000], "close": [1.1, 1.1, 1.1]}
    eb = bot._entry_border(candles, emitido=3000.0)
    assert eb == 6060                              # 6000 + tf (siguiente a la real)
    # Sin 'ts' (feed viejo/tests): cae a la grilla del reloj local.
    eb2 = bot._entry_border({"close": [1.1]}, emitido=3000.0)
    assert eb2 == 3060                             # 3000 - 0 + 60


def test_entry_border_reloj_local_adelantado_no_elige_pasado() -> None:
    """Si el borde local es mayor que el de PO (reloj adelantado o colector con
    lag), toma el MAX -> nunca anuncia una vela anterior al proximo borde local."""
    tf = 60
    bot = _bot(_FeedLiquidacion({}))
    bot.timeframe_seconds = tf
    # Ultima real vieja (bucket 1000); borde local 9060 -> gana el local.
    candles = {"ts": [1000], "close": [1.1]}
    assert bot._entry_border(candles, emitido=9000.0) == 9060


def test_tarjeta_muestra_hora_local_no_el_grid_de_po() -> None:
    """La tarjeta muestra la hora del reloj LOCAL (show_ts), no el grid de PO
    (entry_ts, que va +2h). Antes se mostraba entry_ts -> hora +2h de la real."""
    from datetime import datetime
    bot = _bot(_FeedLiquidacion({}))
    bot.timeframe_seconds = 60
    po_border = 1_000_000 + 7200                   # grid de PO adelantado 2h
    local_border = 1_000_000                       # reloj local real
    result = {"signal": "CALL", "atr": 0.0010, "confirming": ["ema"],
              "confirmations": 1, "price": 1.10, "votes": {"ema": 1}}
    card = bot.build_card("EUR/USD", result, payout=85,
                          entry_ts=po_border, show_ts=local_border)
    hh_local = datetime.fromtimestamp(local_border).astimezone().strftime("%H:%M")
    hh_po = datetime.fromtimestamp(po_border).astimezone().strftime("%H:%M")
    assert f"HORA DE ENTRADA: *{hh_local}*" in card
    assert hh_po not in card                       # NO la hora de PO (+2h)


def test_entry_show_ts_persiste_y_vuelve() -> None:
    """entry_show_ts se guarda aparte de entry_ts y vuelve en pending_older_than
    (para que el RESULTADO muestre la hora local, no el grid de PO)."""
    bot = _bot(_FeedLiquidacion({}))
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s", "confirmations": 2,
                           "price": 1.10, "atr": 0.001,
                           "entry_ts": 1_008_200, "entry_show_ts": 1_001_000})
    p = bot.store.pending_older_than(2_000_000)[0]
    assert p["entry_ts"] == 1_008_200 and p["entry_show_ts"] == 1_001_000


def test_nula_avisa_no_desaparece_en_silencio() -> None:
    """Una señal que vence SIN vela real (pasado el margen) se resuelve NULA y AVISA
    (antes se resolvia NULL en silencio y el humano no recibia resultado)."""
    import bots.base_bot as bb
    tf = 60
    bot = _bot(_FeedLiquidacion({}))                # feed sin ninguna vela real
    bot.timeframe_seconds = tf
    bot.null_grace_seconds = 0                       # sin margen -> NULA al vencer
    bot.store.save_signal({"ts": 1000, "pair": "EUR/USD", "timeframe": "1m",
                           "direction": "CALL", "setup_id": "s", "confirmations": 2,
                           "price": 1.10, "atr": 0.001, "entry_ts": 1200,
                           "entry_show_ts": 1200})
    capturado = []

    class _FakeNotifier:
        def send_text(self, t):
            capturado.append(t)

    bot.notifier = _FakeNotifier()
    orig = bb.control.telegram_activo
    bb.control.telegram_activo = lambda _id: True
    try:
        n = bot.resolve_pending(now=2000.0)          # 2000 >> expiry 1260
    finally:
        bb.control.telegram_activo = orig
    assert n == 0                                    # NULA no cuenta como resuelta real
    assert capturado and "NULA" in capturado[0]      # pero SI avisa


def _run_all() -> None:
    tests = [test_liquida_contra_entry_ts_guardado_no_recalculado,
             test_call_gana_si_sube_pierde_si_baja,
             test_put_gana_si_baja,
             test_sin_vela_real_no_resuelve_pasado_grace_nula,
             test_no_resuelve_antes_de_vencer,
             test_fallback_legado_sin_entry_ts,
             test_entry_border_anclado_a_grilla_de_po,
             test_entry_border_reloj_local_adelantado_no_elige_pasado,
             test_tarjeta_muestra_hora_local_no_el_grid_de_po,
             test_entry_show_ts_persiste_y_vuelve,
             test_nula_avisa_no_desaparece_en_silencio]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
