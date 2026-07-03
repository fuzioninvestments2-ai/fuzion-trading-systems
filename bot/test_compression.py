"""
bot/test_compression.py
=======================
Valida el detector de COMPRESIÓN (squeeze de Bollinger) SIN red: un tramo de
mercado comprimido (rango estrecho) debe marcar comprimido=True; un tramo
volátil/ancho debe marcar comprimido=False.
"""

import numpy as np
import pandas as pd

from bot.scoring_strategy import compression


def _serie(valores):
    return pd.Series(valores, dtype=float)


def test_compresion_detecta_rango_estrecho():
    # Primero volátil (bandas anchas), luego se comprime (rango plano al final).
    volatil = [1.10 + 0.02 * np.sin(i) for i in range(80)]
    plano = [1.10 + 0.0002 * np.sin(i) for i in range(40)]   # casi sin rango
    close = _serie(volatil + plano)
    comprimido, ancho_rel = compression(close, lookback=120)
    assert comprimido is True, (comprimido, ancho_rel)
    assert 0.0 <= ancho_rel <= 0.25, ancho_rel
    print(f"OK detecta compresión al final (ancho_rel={ancho_rel})")


def test_no_comprimido_cuando_es_ancho():
    # Ancho creciente: el último tramo es el MÁS ancho -> percentil alto.
    close = _serie([1.10 + (i / 100.0) * np.sin(i) for i in range(120)])
    comprimido, ancho_rel = compression(close, lookback=120)
    assert comprimido is False, (comprimido, ancho_rel)
    print(f"OK no marca compresión en mercado ancho (ancho_rel={ancho_rel})")


def test_pocas_velas_no_rompe():
    comprimido, ancho_rel = compression(_serie([1.1, 1.1, 1.1]))
    assert comprimido is False and ancho_rel is None
    print("OK con pocas velas devuelve (False, None) sin error")


if __name__ == "__main__":
    test_compresion_detecta_rango_estrecho()
    test_no_comprimido_cuando_es_ancho()
    test_pocas_velas_no_rompe()
    print("\nTODOS OK — detector de compresión (squeeze)")
