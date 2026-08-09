"""
tests/test_signal_card.py (fuzion_fx)
=====================================
Valida SignalCardFormatter.format_signal: regla de la estrella (>=80% y >=10
medidas), "sin muestra" con N<5, acierto visible con N>=5, flechas CALL/PUT
(verde/rojo), sesion por hora UTC y divisa sin barra. Puro, SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from telegram.signal_formatter import SignalCardFormatter    # noqa: E402


def _base(**over):
    """Diccionario de señal valido; se sobreescriben campos por test."""
    d = {"bot_name": "Fuzion F1 (1M)", "pair": "EUR/USD", "direction": "CALL",
         "card_label": "1M", "entry_time": "14:30", "expiry_time": "14:31",
         "tz_offset": -5, "utc_hour": 14, "payout_pct": 85, "confirmations": 3,
         "indicators": ["ema", "macd", "rsi"], "win_pct": None, "measured": 0,
         "atr_pips": 1.2}
    d.update(over)
    return d


def test_estrella_con_80_y_10_medidas() -> None:
    # Regla: estrella SOLO con acierto >= 80% Y >= 10 señales medidas.
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(win_pct=80.0, measured=10))
    assert "⭐" in txt


def test_sin_estrella_bajo_umbral() -> None:
    fmt = SignalCardFormatter()
    # 79% con 12 medidas -> sin estrella (falla el % aunque sobre muestra).
    assert "⭐" not in fmt.format_signal(_base(win_pct=79.0, measured=12))
    # 90% con 9 medidas -> sin estrella (falla la muestra aunque sobre %).
    assert "⭐" not in fmt.format_signal(_base(win_pct=90.0, measured=9))


def test_sin_muestra_debajo_de_5() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(win_pct=100.0, measured=4))
    assert "sin muestra aún (recién aprende)" in txt


def test_acierto_visible_desde_5() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(win_pct=72.0, measured=6))
    assert "72%  (6 señales medidas)" in txt
    assert "sin muestra" not in txt


def test_flecha_call_verde() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(direction="CALL"))
    assert "🟩 CALL (poner ARRIBA)" in txt


def test_flecha_put_roja() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(direction="PUT"))
    assert "🟥 PUT (poner ABAJO)" in txt


def test_sesion_por_hora_utc() -> None:
    fmt = SignalCardFormatter()
    assert fmt.session_from_utc_hour(9) == "Europe"
    assert fmt.session_from_utc_hour(15) == "America"
    assert fmt.session_from_utc_hour(2) == "Asia"
    # Sin session explicita, la tarjeta usa utc_hour.
    txt = fmt.format_signal(_base(session=None, utc_hour=9))
    assert "Mercado: Europe" in txt


def test_sesion_explicita_manda() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(session="America", utc_hour=2))
    assert "Mercado: America" in txt


def test_divisa_sin_barra() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(pair="EUR/USD"))
    assert "DIVISA: *EURUSD*" in txt
    assert "EUR/USD" not in txt


def test_zona_horaria_y_disclaimer() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(tz_offset=-5))
    assert "UTC-5:00" in txt
    assert "Demo · señal educativa · el acierto no está garantizado" in txt


def _run_all() -> None:
    tests = [test_estrella_con_80_y_10_medidas, test_sin_estrella_bajo_umbral,
             test_sin_muestra_debajo_de_5, test_acierto_visible_desde_5,
             test_flecha_call_verde, test_flecha_put_roja,
             test_sesion_por_hora_utc, test_sesion_explicita_manda,
             test_divisa_sin_barra, test_zona_horaria_y_disclaimer]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
