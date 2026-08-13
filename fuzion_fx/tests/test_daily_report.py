"""
tests/test_daily_report.py (fuzion_fx)
======================================
Valida DailyReport: conteos por par, acierto del dia, mejor/peor par, modo
recuperacion DERIVADO de la DB (perdidas consecutivas al cierre) y acumulado.
SIN red ni reloj (ventana del dia pasada explicita, sqlite en memoria).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                    # noqa: E402
from core.daily_report import DailyReport                      # noqa: E402

DIA = 1_700_000_000            # inicio del dia (epoch arbitrario, sin reloj)
FIN = DIA + 86_400


def _sig(st, pair, ts_off, result=None, direction="CALL"):
    """Inserta una senal en el dia; si result no es None, la resuelve."""
    sid = st.save_signal({"pair": pair, "timeframe": "1m", "direction": direction,
                          "setup_id": f"{direction}|ema,macd,rsi", "confirmations": 3,
                          "price": 1.10, "atr": 0.001, "ts": DIA + ts_off})
    if result is not None:
        pnl = 8.0 if result == "win" else (-10.0 if result == "loss" else 0.0)
        st.resolve_signal(sid, result, pnl)
    return sid


def _store():
    st = ResultsStore(":memory:")
    # EUR/USD: 3 win, 1 loss  -> 75%
    for k in range(3):
        _sig(st, "EUR/USD", 100 + k, "win")
    _sig(st, "EUR/USD", 200, "loss")
    # GBP/JPY: 1 win, 3 loss (las 3 perdidas AL FINAL) -> 25%, en recuperacion
    _sig(st, "GBP/JPY", 300, "win")
    for k in range(3):
        _sig(st, "GBP/JPY", 400 + k, "loss")
    # AUD/USD: 1 pendiente (sin resolver) -> no cuenta en acierto
    _sig(st, "AUD/USD", 500, None)
    return st


def test_conteos_y_pares() -> None:
    rep = DailyReport(_store(), bot_name="FUZION FX 1M", card_label="1 min - M1",
                      recovery_after=3)
    s = rep.build(DIA, FIN)
    assert s["total"] == 9                          # 4 + 4 + 1
    assert s["pares"] == ["AUD/USD", "EUR/USD", "GBP/JPY"]
    assert s["por_par"]["EUR/USD"]["wins"] == 3
    assert s["por_par"]["EUR/USD"]["losses"] == 1
    assert s["por_par"]["EUR/USD"]["win_pct"] == 75.0
    assert s["por_par"]["AUD/USD"]["pending"] == 1
    assert s["por_par"]["AUD/USD"]["win_pct"] is None


def test_acierto_del_dia() -> None:
    rep = DailyReport(_store(), bot_name="b", card_label="1m", recovery_after=3)
    s = rep.build(DIA, FIN)
    # wins=4 (3 EUR + 1 GBP), losses=4 (1 EUR + 3 GBP) -> 50%
    assert s["wins"] == 4 and s["losses"] == 4
    assert s["day_win_pct"] == 50.0


def test_mejor_y_peor_par() -> None:
    rep = DailyReport(_store(), bot_name="b", card_label="1m", recovery_after=3)
    s = rep.build(DIA, FIN)
    assert s["best"] == "EUR/USD"                   # 75%
    assert s["worst"] == "GBP/JPY"                  # 25%


def test_recuperacion_derivada() -> None:
    rep = DailyReport(_store(), bot_name="b", card_label="1m", recovery_after=3)
    s = rep.build(DIA, FIN)
    # GBP/JPY: 3 perdidas consecutivas al final -> en recuperacion.
    # EUR/USD: ultima fue loss pero solo 1 seguida -> NO.
    assert s["recuperacion"] == ["GBP/JPY"]


def test_recuperacion_umbral_2() -> None:
    # Con recovery_after=2, EUR/USD (1 perdida final) sigue fuera; GBP/JPY dentro.
    rep = DailyReport(_store(), bot_name="b", card_label="1m", recovery_after=2)
    s = rep.build(DIA, FIN)
    assert s["recuperacion"] == ["GBP/JPY"]


def test_acumulado() -> None:
    rep = DailyReport(_store(), bot_name="b", card_label="1m", recovery_after=3)
    s = rep.build(DIA, FIN)
    ac = s["acumulado"]
    assert ac["emitidas"] == 9                       # incluye la pendiente
    assert ac["resueltas"] == 8                      # win/loss resueltas
    assert ac["win_pct"] == 50.0


def test_dia_vacio() -> None:
    st = ResultsStore(":memory:")
    rep = DailyReport(st, bot_name="FUZION FX 5M", card_label="5 min - M5",
                      recovery_after=2)
    s = rep.build(DIA, FIN)
    assert s["total"] == 0
    md = rep.to_markdown(s, "2026-08-11")
    assert "Sin señales hoy." in md
    tg = rep.to_telegram(s, "2026-08-11")
    assert "Sin señales hoy." in tg


def test_markdown_y_telegram_completos() -> None:
    rep = DailyReport(_store(), bot_name="FUZION FX 1M", card_label="1 min - M1",
                      recovery_after=3)
    s = rep.build(DIA, FIN)
    md = rep.to_markdown(s, "2026-08-11")
    assert "Resumen diario — FUZION FX 1M" in md
    assert "EUR/USD" in md and "GBP/JPY" in md
    assert "Acierto del día:" in md and "50%" in md
    assert "Mejor par:" in md and "Peor par:" in md
    assert "Modo recuperación:** SÍ — GBP/JPY" in md
    assert "el acierto no está garantizado" in md

    tg = rep.to_telegram(s, "2026-08-11")
    assert "Resumen 2026-08-11" in tg
    assert "Mejor:" in tg and "Peor:" in tg
    assert "Recuperación: GBP/JPY" in tg


def test_acierto_por_fuerza_en_resumen() -> None:
    st = ResultsStore(":memory:")
    # Fuertes (0.7) ganan; debiles (0.2) pierden -> el resumen lo muestra.
    for k in range(3):
        sid = st.save_signal({"pair": "EUR/USD", "direction": "CALL",
                              "setup_id": "s", "fuerza": 0.7, "ts": DIA + k})
        st.resolve_signal(sid, "win")
    for k in range(2):
        sid = st.save_signal({"pair": "EUR/USD", "direction": "CALL",
                              "setup_id": "s", "fuerza": 0.2, "ts": DIA + 50 + k})
        st.resolve_signal(sid, "loss")
    rep = DailyReport(st, bot_name="FUZION FX 1M", card_label="1 min - M1",
                      recovery_after=3)
    s = rep.build(DIA, FIN)
    assert s["por_fuerza"]["fuertes"]["win_pct"] == 100.0
    assert s["por_fuerza"]["debiles"]["win_pct"] == 0.0
    tg = rep.to_telegram(s, "2026-08-13")
    assert "Por fuerza:" in tg and "🔥 100%" in tg and "➖ 0%" in tg


def _run_all() -> None:
    tests = [test_conteos_y_pares, test_acierto_del_dia, test_mejor_y_peor_par,
             test_recuperacion_derivada, test_recuperacion_umbral_2,
             test_acumulado, test_dia_vacio, test_markdown_y_telegram_completos,
             test_acierto_por_fuerza_en_resumen]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
