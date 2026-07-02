"""
bot/test_market_hours.py
========================
Prueba del horario de mercado (Regla 4), con fechas inyectadas (deterministas).
"""

import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.market_hours import is_open


def _dt(y, m, d, h=12):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


def test_otc_siempre_abierto():
    # Un sábado: OTC sigue abierto.
    ab, _ = is_open("EURUSD_otc", _dt(2026, 7, 4))   # 2026-07-04 es sábado
    assert ab, "❌ OTC debería estar abierto siempre"
    print("✅ (A) OTC abierto 24/7 (incluso sábado).")


def test_real_cerrado_finde():
    ab_sab, motivo_s = is_open("EURUSD", _dt(2026, 7, 4))   # sábado
    ab_dom, _ = is_open("EURUSD", _dt(2026, 7, 5, 10))      # domingo mañana
    assert not ab_sab and not ab_dom, f"❌ Real debería estar cerrado: {motivo_s}"
    print("✅ (B) Real CERRADO el fin de semana.")


def test_real_abierto_semana():
    ab, _ = is_open("EURUSD", _dt(2026, 7, 1, 12))   # 2026-07-01 es miércoles
    assert ab, "❌ Real debería estar abierto entre semana"
    print("✅ (C) Real abierto entre semana.")


if __name__ == "__main__":
    test_otc_siempre_abierto()
    test_real_cerrado_finde()
    test_real_abierto_semana()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
