"""
bot/test_evaluacion_riesgo.py
=============================
Valida sin red la evaluación de riesgo: en un mercado tranquilo con un pico aislado NO
hay zona de golpes (se opera); en un mercado martillado (muchos picos) SÍ (no se opera).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.evaluacion_riesgo import contar_golpes, en_golpes


def test_tranquilo_pocos_golpes():
    tranquilo = [1.0800 + 0.00005 * ((-1) ** i) for i in range(15)] + [1.0815]
    assert contar_golpes(tranquilo, "EURCHF") == 0
    assert en_golpes(tranquilo, "EURCHF") is False


def test_martillado_muchos_golpes():
    martillado = [1.0800 + 0.0012 * ((-1) ** i) for i in range(15)] + [1.0815]
    assert contar_golpes(martillado, "EURCHF") >= 4
    assert en_golpes(martillado, "EURCHF") is True


def test_piso_por_tiempo_cuenta_menos_en_5m():
    # Con un piso mayor (5m se mueve más), los mismos saltos ya no cuentan como golpe.
    serie = [1.0800 + 0.0006 * ((-1) ** i) for i in range(15)] + [1.0815]   # saltos ~12 pips
    assert contar_golpes(serie, "EURCHF", piso_pips=6) >= 4     # piso 6: son golpes
    assert contar_golpes(serie, "EURCHF", piso_pips=20) == 0    # piso 20: normales para 5m


def test_sin_muestra_no_marca():
    assert en_golpes([1.0800, 1.0810], "EURCHF") is False


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
