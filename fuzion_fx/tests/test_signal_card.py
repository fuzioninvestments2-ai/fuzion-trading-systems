"""
tests/test_signal_card.py (fuzion_fx)
=====================================
Valida SignalCardFormatter.format_signal (datos POR PAR): regla de la estrella
(>=80% y >=10 medidas), "sin muestra" con N<5, acierto visible con N>=5, flechas
CALL/PUT (verde/rojo), mercado explicito/por hora UTC y divisa sin barra. Puro,
SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from telegram.signal_formatter import SignalCardFormatter    # noqa: E402


def _base(**over):
    """Diccionario de señal valido (por par); se sobreescriben campos por test."""
    d = {"bot_name": "Fuzion FX 1M", "par": "EUR/USD", "direccion": "CALL",
         "card_label": "1M", "hora_entrada": "14:30", "hora_vencimiento": "14:31",
         "tz_offset": -5, "mercado": "America", "payout": 85,
         "confirmaciones": ["ema", "macd", "rsi"], "acierto_pct": None,
         "n_muestras": 0, "atr": 1.2}
    d.update(over)
    return d


def test_estrella_con_80_y_10_medidas() -> None:
    # Regla: estrella SOLO con acierto >= 80% Y >= 10 señales medidas (por par).
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(acierto_pct=80.0, n_muestras=10))
    assert "⭐" in txt


def test_sin_estrella_bajo_umbral() -> None:
    fmt = SignalCardFormatter()
    # 79% con 12 medidas -> sin estrella (falla el % aunque sobre muestra).
    assert "⭐" not in fmt.format_signal(_base(acierto_pct=79.0, n_muestras=12))
    # 90% con 9 medidas -> sin estrella (falla la muestra aunque sobre %).
    assert "⭐" not in fmt.format_signal(_base(acierto_pct=90.0, n_muestras=9))


def test_sin_muestra_debajo_de_5() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(acierto_pct=100.0, n_muestras=4))
    assert "sin muestra aún (recién aprende)" in txt


def test_acierto_visible_desde_5() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(acierto_pct=72.0, n_muestras=6))
    assert "72%  (6 señales medidas)" in txt
    assert "sin muestra" not in txt


def test_acierto_por_par_no_se_mezcla() -> None:
    # Ejemplo real: NZDUSD 100% (11) lleva estrella; GBPCHF con poca muestra no.
    fmt = SignalCardFormatter()
    nzd = fmt.format_signal(_base(par="NZD/USD", acierto_pct=100.0, n_muestras=11))
    gbp = fmt.format_signal(_base(par="GBP/CHF", acierto_pct=100.0, n_muestras=3))
    assert "NZDUSD" in nzd and "⭐" in nzd
    assert "GBPCHF" in gbp and "⭐" not in gbp
    assert "sin muestra aún (recién aprende)" in gbp


def test_flecha_call_verde() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(direccion="CALL"))
    assert "🟩 CALL (poner ARRIBA)" in txt


def test_flecha_put_roja() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(direccion="PUT"))
    assert "🟥 PUT (poner ABAJO)" in txt


def test_mercado_explicito() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(mercado="Asia"))
    assert "Mercado: Asia" in txt


def test_mercado_por_hora_utc_fallback() -> None:
    fmt = SignalCardFormatter()
    assert fmt.session_from_utc_hour(9) == "Europe"
    assert fmt.session_from_utc_hour(15) == "America"
    assert fmt.session_from_utc_hour(2) == "Asia"
    # Sin mercado explicito, la tarjeta cae a utc_hour.
    txt = fmt.format_signal(_base(mercado=None, utc_hour=9))
    assert "Mercado: Europe" in txt


def test_divisa_sin_barra() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(par="EUR/USD"))
    assert "DIVISA: *EURUSD*" in txt
    assert "EUR/USD" not in txt


def test_divisa_otc_muestra_sufijo() -> None:
    # Con es_otc la tarjeta muestra "EURUSD OTC": el usuario debe abrir el MISMO
    # activo OTC en PO (el analisis y la liquidacion son sobre el OTC sintetico).
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(par="EUR/USD", es_otc=True))
    assert "DIVISA: *EURUSD OTC*" in txt


def test_bot_name_de_yaml() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(bot_name="Fuzion FX 1M"))
    assert "🤖 *Fuzion FX 1M*" in txt


def test_confirmaciones_cuenta_por_lista() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(confirmaciones=["ema", "macd", "rsi", "bollinger"]))
    assert "Confirmaciones: 4 (ema, macd, rsi, bollinger)" in txt


def test_zona_horaria_y_disclaimer() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_signal(_base(tz_offset=-5))
    assert "UTC-5:00" in txt
    assert "Demo · señal educativa · el acierto no está garantizado" in txt


def _run_all() -> None:
    tests = [test_estrella_con_80_y_10_medidas, test_sin_estrella_bajo_umbral,
             test_sin_muestra_debajo_de_5, test_acierto_visible_desde_5,
             test_acierto_por_par_no_se_mezcla, test_flecha_call_verde,
             test_flecha_put_roja, test_mercado_explicito,
             test_mercado_por_hora_utc_fallback, test_divisa_sin_barra,
             test_divisa_otc_muestra_sufijo,
             test_bot_name_de_yaml, test_confirmaciones_cuenta_por_lista,
             test_zona_horaria_y_disclaimer]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
