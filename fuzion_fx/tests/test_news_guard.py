"""
tests/test_news_guard.py (fuzion_fx)
====================================
Valida el motor de bloqueo por noticias: parseo de fechas, ventana +/- buffer,
alcance por moneda vs global, y solo bloquea alto impacto. SIN red.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.news_guard import (_iso_a_epoch, cargar_eventos, en_bloqueo,   # noqa: E402
                             proximo_evento)

# 2026-08-12T12:30:00Z -> epoch fijo (referencia de las pruebas).
_T = _iso_a_epoch("2026-08-12T12:30:00Z")


def test_parseo_iso_con_z() -> None:
    assert _T is not None
    assert _iso_a_epoch("2026-08-12T12:30:00+00:00") == _T
    assert _iso_a_epoch("basura") is None
    assert _iso_a_epoch(None) is None


def _eventos(monedas=None, impacto="alto"):
    return [{"ts": _T, "impacto": impacto, "titulo": "US CPI",
             "monedas": monedas or []}]


def test_bloquea_dentro_de_la_ventana() -> None:
    ev = _eventos()
    # 5 min antes del evento, buffer 10 -> bloquea.
    assert en_bloqueo(_T - 5 * 60, ev, 10)[0] is True
    # 20 min antes, buffer 10 -> NO bloquea.
    assert en_bloqueo(_T - 20 * 60, ev, 10)[0] is False


def test_alcance_por_moneda() -> None:
    ev = _eventos(monedas=["USD"])
    # USD/CHF incluye USD -> bloquea; EUR/GBP no -> no bloquea.
    assert en_bloqueo(_T, ev, 10, pair="USD/CHF")[0] is True
    assert en_bloqueo(_T, ev, 10, pair="EUR/GBP")[0] is False


def test_evento_global_bloquea_todo() -> None:
    ev = _eventos(monedas=[])          # sin monedas -> global
    assert en_bloqueo(_T, ev, 10, pair="EUR/GBP")[0] is True


def test_solo_alto_impacto() -> None:
    ev = _eventos(impacto="medio")
    assert en_bloqueo(_T, ev, 10)[0] is False


def test_cargar_eventos_desde_archivo() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({"eventos": [
        {"cuando": "2026-08-12T12:30:00Z", "impacto": "alto", "titulo": "CPI",
         "monedas": ["USD"]},
        {"cuando": "malo", "impacto": "alto", "titulo": "x"}]}, tmp)
    tmp.close()
    try:
        evs = cargar_eventos(tmp.name)
        assert len(evs) == 1 and evs[0]["ts"] == _T   # el malo se descarta
        assert cargar_eventos("/no/existe.json") == []
        assert proximo_evento(_T - 100, evs)["titulo"] == "CPI"
        assert proximo_evento(_T + 100, evs) is None
    finally:
        os.unlink(tmp.name)


def _run_all() -> None:
    tests = [test_parseo_iso_con_z, test_bloquea_dentro_de_la_ventana,
             test_alcance_por_moneda, test_evento_global_bloquea_todo,
             test_solo_alto_impacto, test_cargar_eventos_desde_archivo]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
