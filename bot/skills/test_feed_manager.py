"""
bot/skills/test_feed_manager.py
===============================
Valida el failover del gestor de feed (sin red, reloj inyectado): PO vivo → PO;
silencio de PO → Dukascopy; PO vuelve → PO. Cuenta los cambios de fuente.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.skills.feed_manager import FeedManager, POCKET, DUKASCOPY


def test_pocket_vivo_usa_pocket():
    fm = FeedManager(silencio_seg=90)
    t = 1_000_000_000_000
    fm.registrar_tick_pocket(t)
    assert fm.revisar(t + 10_000) == POCKET          # 10s desde el tick


def test_silencio_activa_respaldo():
    fm = FeedManager(silencio_seg=90)
    t = 1_000_000_000_000
    fm.registrar_tick_pocket(t)
    # 120s sin ticks (> 90) → respaldo.
    assert fm.revisar(t + 120_000) == DUKASCOPY


def test_vuelta_a_pocket():
    fm = FeedManager(silencio_seg=90)
    t = 1_000_000_000_000
    fm.registrar_tick_pocket(t)
    assert fm.revisar(t + 120_000) == DUKASCOPY      # cae a respaldo
    fm.registrar_tick_pocket(t + 121_000)            # PO vuelve
    assert fm.revisar(t + 122_000) == POCKET
    assert fm.cambios == 2                            # pocket→duka→pocket


def test_estado_reporta_gap():
    fm = FeedManager()
    t = 1_000_000_000_000
    fm.registrar_tick_pocket(t)
    e = fm.estado(t + 30_000)
    assert e["pocket_silencio_seg"] == 30.0
    assert e["fuente_activa"] == POCKET


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
