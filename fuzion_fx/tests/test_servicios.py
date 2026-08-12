"""
tests/test_servicios.py (fuzion_fx)
===================================
Valida el registro unico de servicios y su integracion: estan el colector, los 4
bots y el panel; el panel corre con --no-open; y start_all/vigilante leen de aca
(crecer = agregar una entrada). SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts import servicios                                    # noqa: E402
from scripts import start_all                                    # noqa: E402


def test_registro_tiene_todo() -> None:
    nombres = [s["nombre"] for s in servicios.SERVICIOS]
    for n in ("collector", "f1_m1", "f2_m2", "f3_m3", "f4_m5", "panel"):
        assert n in nombres
    # cada servicio tiene script existente y campos completos.
    for s in servicios.SERVICIOS:
        assert s["script"].endswith(".py") and os.path.isfile(s["script"])
        assert isinstance(s["args"], list) and isinstance(s["supervisar"], bool)


def test_panel_corre_sin_abrir_navegador() -> None:
    panel = servicios.POR_NOMBRE["panel"]
    assert "--no-open" in panel["args"]             # el server no abre pestana


def test_supervisados_incluye_panel() -> None:
    nombres = [s["nombre"] for s in servicios.supervisados()]
    assert "panel" in nombres and "collector" in nombres


def test_start_all_deriva_del_registro() -> None:
    # PROCESOS y SCRIPT_DE de start_all salen del registro unico.
    assert len(start_all.PROCESOS) == len(servicios.SERVICIOS)
    assert "panel" in start_all.SCRIPT_DE
    assert start_all.SCRIPT_DE["panel"]["args"] == ["--no-open"]


def _run_all() -> None:
    tests = [test_registro_tiene_todo, test_panel_corre_sin_abrir_navegador,
             test_supervisados_incluye_panel, test_start_all_deriva_del_registro]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
