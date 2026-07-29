"""
bot/test_vigilante_reversion.py
===============================
Valida sin red el núcleo del robot: dispara señal al cerrar una vela con pico, no
repite aviso para la misma vela, respeta el horario, e ignora pares no vigilados.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.vigilante_reversion import VigilanteReversion


def test_pico_dispara_senal():
    v = VigilanteReversion(["EURCHF"])
    v.nueva_vela("EURCHF", 1.0800, ts=1)
    s = v.nueva_vela("EURCHF", 1.0810, ts=2)       # +10 pips -> PUT
    assert s is not None
    assert s["direccion"] == "PUT"
    assert "ABAJO" in s["tarjeta"] and "EURCHF" in s["tarjeta"]


def test_sin_pico_no_avisa():
    v = VigilanteReversion(["EURCHF"])
    v.nueva_vela("EURCHF", 1.0800, ts=1)
    s = v.nueva_vela("EURCHF", 1.08005, ts=2)      # 0.5 pips -> nada
    assert s is None


def test_no_repite_misma_vela():
    v = VigilanteReversion(["EURCHF"])
    v.nueva_vela("EURCHF", 1.0800, ts=1)
    s1 = v.nueva_vela("EURCHF", 1.0810, ts=2)      # dispara
    s2 = v.nueva_vela("EURCHF", 1.0810, ts=2)      # misma vela (mismo ts) -> None
    assert s1 is not None and s2 is None


def test_respeta_horario_cerrado():
    v = VigilanteReversion(["EURCHF"], is_open=lambda par: False)   # siempre cerrado
    v.nueva_vela("EURCHF", 1.0800, ts=1)
    s = v.nueva_vela("EURCHF", 1.0810, ts=2)
    assert s is None                                # cerrado -> calla


def test_par_no_vigilado_se_ignora():
    v = VigilanteReversion(["EURCHF"])
    assert v.nueva_vela("GBPUSD", 1.2500, ts=1) is None


def test_precargar_da_contexto():
    v = VigilanteReversion(["EURCHF"])
    v.precargar("EURCHF", [1.0800, 1.0800, 1.0800])
    s = v.nueva_vela("EURCHF", 1.0790, ts=9)       # bajó 10 pips -> CALL, ya con contexto
    assert s is not None and s["direccion"] == "CALL"


def test_usa_tabla_por_par():
    tabla = {"EURCHF": [[5, 70.0]]}
    v = VigilanteReversion(["EURCHF"], tabla=tabla)
    v.nueva_vela("EURCHF", 1.0800, ts=1)
    s = v.nueva_vela("EURCHF", 1.0806, ts=2)       # +6 pips
    assert s is not None and s["probabilidad"] == 70.0


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
