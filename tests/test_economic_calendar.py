"""
tests/test_economic_calendar.py
===============================
Valida `src/market/economic_calendar.py`. SIN red, con `now` inyectado.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.market.economic_calendar import (                       # noqa: E402
    EconomicCalendar, NewsEvent, nfp_for_month,
)


def _utc(y, m, d, h, mi) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_nfp_primer_viernes() -> None:
    # Enero 2026: el primer viernes es el 2.
    nfp = nfp_for_month(2026, 1)
    assert nfp == _utc(2026, 1, 2, 13, 30)
    assert nfp.weekday() == 4                         # viernes


def test_otc_siempre_false() -> None:
    cal = EconomicCalendar()
    # Aun justo en el NFP, en OTC no aplica.
    now = _utc(2026, 1, 2, 13, 0)
    assert cal.is_news_event("EURUSD_otc", now, is_otc=True) is False


def test_bloquea_nfp_real_fx() -> None:
    cal = EconomicCalendar()
    # 13:00 UTC, NFP a las 13:30 -> a 30 min -> dentro de los 60 min -> True.
    now = _utc(2026, 1, 2, 13, 0)
    assert cal.is_news_event("EURUSD", now, is_otc=False) is True   # USD afecta EURUSD
    assert cal.is_news_event("GBPUSD", now, is_otc=False) is True
    # Un par sin USD/EUR/GBP a esa hora no se ve afectado por el NFP (USD).
    assert cal.is_news_event("AUDNZD", now, is_otc=False) is False


def test_ventana_antes_y_despues() -> None:
    cal = EconomicCalendar()
    # NFP 13:30. A las 12:00 (90 min antes) -> fuera de los 60 -> False.
    assert cal.is_news_event("EURUSD", _utc(2026, 1, 2, 12, 0)) is False
    # A las 13:40 (10 min despues) -> dentro de los 15 post -> True.
    assert cal.is_news_event("EURUSD", _utc(2026, 1, 2, 13, 40)) is True
    # A las 13:50 (20 min despues) -> fuera de los 15 post -> False.
    assert cal.is_news_event("EURUSD", _utc(2026, 1, 2, 13, 50)) is False


def test_evento_agendado_por_divisa() -> None:
    # Calendario propio: solo un ECB.
    ecb = NewsEvent("EUR", "ECB", _utc(2026, 3, 12, 13, 15))
    cal = EconomicCalendar(events=[ecb])
    now = _utc(2026, 3, 12, 12, 30)                   # 45 min antes
    assert cal.is_news_event("EURUSD", now) is True   # EUR afectado
    assert cal.is_news_event("USDJPY", now) is False  # sin EUR
    # Fuera de fecha -> nada.
    assert cal.is_news_event("EURUSD", _utc(2026, 3, 11, 12, 30)) is False


def test_upcoming_devuelve_evento() -> None:
    cal = EconomicCalendar()
    ups = cal.upcoming("EURUSD", _utc(2026, 1, 2, 13, 0))
    assert any(e.name == "NFP" and e.currency == "USD" for e in ups)


def _run_all() -> None:
    tests = [test_nfp_primer_viernes, test_otc_siempre_false,
             test_bloquea_nfp_real_fx, test_ventana_antes_y_despues,
             test_evento_agendado_por_divisa, test_upcoming_devuelve_evento]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
