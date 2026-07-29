"""
bot/test_autocorrector.py
=========================
Valida sin red el corrector: el punto de equilibrio por pago y la decisión de
silenciar un par que viene fallando (sin arrastrar el error), respetando la
muestra mínima. Incluye la integración con SignalTracker.win_rate_reciente.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.autocorrector import break_even, debe_enviar
from bot.signal_log import SignalTracker
from bot.history import HistoryRepository


def test_break_even_por_pago():
    # 1/(1+p): pago 72% -> 0.581 ; pago 100% -> 0.5.
    assert abs(break_even(72) - 0.5814) < 1e-3
    assert abs(break_even(100) - 0.5) < 1e-6
    assert break_even(0) == 1.0                     # sin pago: imposible


def test_silencia_par_que_falla_con_muestra():
    enviar, _ = debe_enviar(0.50, 30, 72)           # 50% < 58.1% y muestra suficiente
    assert enviar is False


def test_envia_par_que_acierta():
    enviar, _ = debe_enviar(0.65, 30, 72)           # 65% > 58.1%
    assert enviar is True


def test_poca_muestra_no_silencia():
    # Sin evidencia en vivo (menos de min_muestra) se confía en el histórico y envía.
    enviar, _ = debe_enviar(0.10, 5, 72, min_muestra=20)
    assert enviar is True


def test_margen_extra_exige_mas():
    # Con margen 0.05 el umbral sube ~63%: un 60% ya no pasa.
    enviar, _ = debe_enviar(0.60, 30, 72, margen=0.05)
    assert enviar is False


def _tracker_tmp(d):
    return SignalTracker(HistoryRepository(os.path.join(d, "h.db")))


def test_win_rate_reciente_desde_tracker():
    with tempfile.TemporaryDirectory() as d:
        repo = HistoryRepository(os.path.join(d, "h.db"))
        tk = SignalTracker(repo)
        # 3 velas M1: la de vencimiento a ts=180000 con precio 1.0790 (bajó).
        repo.record_candle("EURCHF", "M1", {"timestamp": 180_000, "open": 1.079,
            "high": 1.0795, "low": 1.0788, "close": 1.0790, "volume": 1.0})
        # Señal PUT desde 1.0800 con vencimiento 120s (vence en 120000, resuelve con
        # la primera M1 >= 120000 -> la de 180000, precio 1.0790 < 1.0800 -> win).
        tk.record("EURCHF", "M2", "PUT", 1.0800, 0, 120)
        tk.resolve_pending(200_000)
        wr, muestra = tk.win_rate_reciente("EURCHF", "M2", ultimas=20)
        assert muestra == 1 and wr == 1.0           # 1 de 1 acertada


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
