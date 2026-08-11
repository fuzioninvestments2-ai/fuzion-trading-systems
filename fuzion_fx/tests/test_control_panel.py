"""
tests/test_control_panel.py (fuzion_fx)
=======================================
Valida la LOGICA del panel de control (sin abrir la ventana Tkinter ni arrancar
procesos reales): composicion de PROCESOS, roundtrip de pids.json y el reporte de
estado. SIN red.
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts import control_panel as cp                         # noqa: E402


def test_procesos_incluye_todo() -> None:
    nombres = [n for n, _ in cp.PROCESOS]
    # colector + 4 bots + resumen = 6, en ese orden (colector primero).
    assert nombres[0] == "collector"
    assert nombres[-1] == "resumen"
    assert nombres == ["collector", "f1_m1", "f2_m2", "f3_m3", "f4_m5", "resumen"]
    # cada proceso apunta a un .py existente en el repo.
    for _, script in cp.PROCESOS:
        assert script.endswith(".py") and os.path.exists(script)


def test_pids_roundtrip(monkeypatch=None) -> None:
    tmp = tempfile.mkdtemp()
    ruta = os.path.join(tmp, "pids.json")
    orig = cp.PIDS_FILE
    cp.PIDS_FILE = ruta
    try:
        assert cp._cargar_pids() == {}                 # sin archivo
        cp._guardar_pids({"collector": 111, "f1_m1": 222})
        assert cp._cargar_pids() == {"collector": 111, "f1_m1": 222}
    finally:
        cp.PIDS_FILE = orig


def test_estado_sin_pids() -> None:
    tmp = tempfile.mkdtemp()
    orig = cp.PIDS_FILE
    cp.PIDS_FILE = os.path.join(tmp, "no_existe.json")
    try:
        txt = cp.estado_procesos()
        assert "nada arrancado" in txt
    finally:
        cp.PIDS_FILE = orig


def test_estado_lista_procesos() -> None:
    tmp = tempfile.mkdtemp()
    orig = cp.PIDS_FILE
    cp.PIDS_FILE = os.path.join(tmp, "pids.json")
    try:
        # PIDs que no existen -> deben figurar como DETENIDO, no romper.
        cp._guardar_pids({"collector": 999999, "f1_m1": 999998})
        txt = cp.estado_procesos()
        assert "collector" in txt and "DETENIDO" in txt
        assert "resumen" in txt and "NO LANZADO" in txt   # no estaba en pids
    finally:
        cp.PIDS_FILE = orig


def _run_all() -> None:
    tests = [test_procesos_incluye_todo, test_pids_roundtrip,
             test_estado_sin_pids, test_estado_lista_procesos]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
