"""
bot/test_levels.py
==================
Valida la detección de soporte/resistencia (techo y piso). Sin red, determinista.
"""

import os
import pandas as pd

from bot.levels import detect_levels, _pivots_altos, _pivots_bajos, _agrupar


def _df(velas):
    return pd.DataFrame(velas, columns=["open", "high", "low", "close"])


def test_pivote_alto_y_bajo():
    # high con un pico claro en el índice 3; low con un valle en el índice 3.
    high = [1, 2, 3, 5, 3, 2, 1]
    low = [5, 4, 3, 1, 3, 4, 5]
    assert 3 in _pivots_altos(high, 2, 2)
    assert 3 in _pivots_bajos(low, 2, 2)
    print("OK detecta pivote alto (pico) y bajo (valle)")


def test_agrupar_niveles_cercanos():
    # Tres valores casi iguales -> un solo nivel (su promedio).
    g = _agrupar([100.0, 100.05, 100.1, 200.0], tol=0.5)
    assert len(g) == 2
    assert abs(g[0] - 100.05) < 1e-9
    print("OK agrupa niveles cercanos en uno")


def test_techo_encima_piso_debajo():
    # Serie con picos y valles; el techo debe quedar >= precio y el piso <=.
    velas = []
    for i in range(30):
        base = 100 + (2 if i % 6 == 3 else 0) - (2 if i % 6 == 0 else 0)
        velas.append((base, base + 1, base - 1, base))
    r = detect_levels(_df(velas))
    price = velas[-1][3]
    assert all(x >= price for x in r["resistencias"]) or r["resistencias"] == []
    assert all(x <= price for x in r["soportes"]) or r["soportes"] == []
    print(f"OK techo>=precio, piso<=precio "
          f"(techos={len(r['resistencias'])}, pisos={len(r['soportes'])})")


def test_pocas_velas_no_rompe():
    assert detect_levels(_df([(1, 1, 1, 1)])) == {"soportes": [], "resistencias": []}
    assert detect_levels(None) == {"soportes": [], "resistencias": []}
    print("OK pocas velas / None no rompen")


def test_chart_con_niveles_dibuja():
    # El gráfico debe aceptar `levels` y generar un PNG no vacío.
    try:
        from bot.chart import draw_candles
    except Exception as e:
        print(f"SALTADO chart (falta matplotlib): {e}")
        return
    velas = [(100 + (i % 3), 101 + (i % 3), 99 + (i % 3), 100 + (i % 3))
             for i in range(20)]
    df = _df(velas)
    lv = {"soportes": [99.0], "resistencias": [102.0]}
    path = os.path.join(os.path.dirname(__file__), "..", "charts_tmp_test.png")
    draw_candles(df, "TEST", "1m", path, direccion="⬆️ UP", levels=lv)
    assert os.path.exists(path) and os.path.getsize(path) > 1000
    os.remove(path)
    print("OK chart dibuja con líneas de soporte/resistencia")


if __name__ == "__main__":
    test_pivote_alto_y_bajo()
    test_agrupar_niveles_cercanos()
    test_techo_encima_piso_debajo()
    test_pocas_velas_no_rompe()
    test_chart_con_niveles_dibuja()
    print("\nTODOS OK — soporte/resistencia (techo y piso)")
