"""
tests/test_scheduler.py (fuzion_fx)
===================================
Valida el scheduler del resumen diario SIN dormir ni red:
  - aritmetica de tiempo (proxima medianoche UTC-4, ventana del dia cerrado),
  - emitir_bot escribe el .md y llama al notifier (falso).
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                        # noqa: E402
from core.daily_report import DailyReport                          # noqa: E402
from scripts.daily_summary_scheduler import (                      # noqa: E402
    segundos_hasta_medianoche, ventana_dia_cerrado, emitir_bot, TZ_UTC4)

TZ = timezone(timedelta(hours=-4))


def test_segundos_hasta_medianoche() -> None:
    now = datetime(2026, 8, 11, 15, 30, 0, tzinfo=TZ).timestamp()
    # 15:30 -> 24:00 = 8h30m = 30600s
    assert abs(segundos_hasta_medianoche(now) - 30600) < 1


def test_ventana_dia_cerrado_en_medianoche() -> None:
    fire = datetime(2026, 8, 11, 0, 0, 0, tzinfo=TZ).timestamp()
    inicio, fin, fecha = ventana_dia_cerrado(fire)
    assert fecha == "2026-08-10"                    # el dia que cerro
    assert fin - inicio == 86400
    assert datetime.fromtimestamp(fin, TZ) == datetime(2026, 8, 11, 0, 0, tzinfo=TZ)
    assert datetime.fromtimestamp(inicio, TZ) == datetime(2026, 8, 10, 0, 0, tzinfo=TZ)


def test_ventana_tolera_disparo_tarde() -> None:
    # Si dispara unos segundos DESPUES de medianoche, el dia cerrado sigue siendo ayer.
    fire = datetime(2026, 8, 11, 0, 0, 5, tzinfo=TZ).timestamp()
    _, _, fecha = ventana_dia_cerrado(fire)
    assert fecha == "2026-08-10"


class _Notif:
    def __init__(self):
        self.textos = []

    def send_text(self, msg, parse_mode="Markdown", reply_to=None):
        self.textos.append(msg); return True


def test_emitir_bot_escribe_y_notifica() -> None:
    dia = 1_700_000_000
    fin = dia + 86_400
    st = ResultsStore(":memory:")
    sid = st.save_signal({"pair": "EUR/USD", "timeframe": "1m", "direction": "CALL",
                          "setup_id": "CALL|ema,macd,rsi", "confirmations": 3,
                          "price": 1.10, "atr": 0.001, "ts": dia + 100})
    st.resolve_signal(sid, "win", 8.0)
    rep = DailyReport(st, bot_name="FUZION FX 1M", card_label="1 min - M1",
                      recovery_after=3)
    stats = rep.build(dia, fin)

    notif = _Notif()
    out = tempfile.mkdtemp()
    path = emitir_bot("f1_m1", rep, stats, "2026-08-10", out, notif)

    assert os.path.exists(path)
    assert path.endswith("resumen_f1_m1_2026-08-10.md")
    with open(path, encoding="utf-8") as fh:
        contenido = fh.read()
    assert "FUZION FX 1M" in contenido and "EUR/USD" in contenido
    assert len(notif.textos) == 1
    assert "Resumen 2026-08-10" in notif.textos[0]


def test_emitir_bot_sin_notifier_igual_guarda() -> None:
    dia = 1_700_000_000
    st = ResultsStore(":memory:")
    rep = DailyReport(st, bot_name="FUZION FX 5M", card_label="5 min - M5",
                      recovery_after=2)
    stats = rep.build(dia, dia + 86_400)           # dia vacio
    out = tempfile.mkdtemp()
    path = emitir_bot("f4_m5", rep, stats, "2026-08-10", out, None)
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        assert "Sin señales hoy." in fh.read()


def _run_all() -> None:
    tests = [test_segundos_hasta_medianoche, test_ventana_dia_cerrado_en_medianoche,
             test_ventana_tolera_disparo_tarde, test_emitir_bot_escribe_y_notifica,
             test_emitir_bot_sin_notifier_igual_guarda]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
