"""
tests/test_vigilante.py (fuzion_fx)
===================================
Valida el nucleo de decision del vigilante (evaluar_salud): reinicia procesos
caidos, reinicia el colector si quedo MUDO, y alerta por falta de pagos tras la
gracia. SIN red ni SO (todo con snapshots mock).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts.vigilante import evaluar_salud                       # noqa: E402

_UMBRALES = {"mudo_seg": 180, "gracia_pagos_seg": 120}


def _snap(procesos, age=10.0, pagos=22, uptime=1000.0):
    return {"procesos": procesos, "db_mtime_age": age, "pagos": pagos,
            "uptime": uptime}


def test_todo_sano_no_hace_nada() -> None:
    procesos = {"collector": True, "f1_m1": True, "f2_m2": True,
                "f3_m3": True, "f4_m5": True}
    plan = evaluar_salud(_snap(procesos), _UMBRALES)
    assert plan["reiniciar"] == [] and plan["alertas"] == []


def test_reinicia_proceso_caido() -> None:
    procesos = {"collector": True, "f1_m1": False, "f2_m2": True,
                "f3_m3": True, "f4_m5": True}
    plan = evaluar_salud(_snap(procesos), _UMBRALES)
    assert plan["reiniciar"] == ["f1_m1"]
    assert any("f1_m1" in a for a in plan["alertas"])


def test_colector_mudo_se_reinicia() -> None:
    procesos = {"collector": True, "f1_m1": True, "f2_m2": True,
                "f3_m3": True, "f4_m5": True}
    plan = evaluar_salud(_snap(procesos, age=400.0), _UMBRALES)   # 400 > 180
    assert plan["reiniciar"] == ["collector"]
    assert any("MUDO" in a for a in plan["alertas"])


def test_colector_caido_no_duplica_reinicio() -> None:
    # Colector muerto y ademas mtime viejo: se reinicia UNA sola vez.
    procesos = {"collector": False, "f1_m1": True, "f2_m2": True,
                "f3_m3": True, "f4_m5": True}
    plan = evaluar_salud(_snap(procesos, age=999.0), _UMBRALES)
    assert plan["reiniciar"].count("collector") == 1


def test_alerta_pagos_solo_tras_gracia() -> None:
    procesos = {"collector": True, "f1_m1": True, "f2_m2": True,
                "f3_m3": True, "f4_m5": True}
    # Sin pagos pero dentro de la gracia -> no alerta todavia.
    plan = evaluar_salud(_snap(procesos, pagos=0, uptime=60.0), _UMBRALES)
    assert not any("pagos" in a for a in plan["alertas"])
    # Sin pagos pasada la gracia -> alerta.
    plan = evaluar_salud(_snap(procesos, pagos=0, uptime=300.0), _UMBRALES)
    assert any("pagos" in a for a in plan["alertas"])


def test_db_sin_mtime_no_marca_mudo() -> None:
    # db_mtime_age None (archivo aun no existe): no se reinicia por "mudo".
    procesos = {"collector": True, "f1_m1": True, "f2_m2": True,
                "f3_m3": True, "f4_m5": True}
    plan = evaluar_salud(_snap(procesos, age=None), _UMBRALES)
    assert "collector" not in plan["reiniciar"]


def _run_all() -> None:
    tests = [test_todo_sano_no_hace_nada, test_reinicia_proceso_caido,
             test_colector_mudo_se_reinicia, test_colector_caido_no_duplica_reinicio,
             test_alerta_pagos_solo_tras_gracia, test_db_sin_mtime_no_marca_mudo]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
