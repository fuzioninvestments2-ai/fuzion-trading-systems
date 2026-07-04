"""
bot/test_data_quality.py
========================
Valida la barrera de seguridad de datos SIN red: reconoce basura (plana, NaN,
corrupta, pocas velas, saltos imposibles) y deja pasar solo lo sano.
"""

import gzip
import os
import tempfile

import numpy as np
import pandas as pd

from bot.data_quality import (calidad_serie, frames_limpios, escanear_datasets,
                              limpiar_datasets)


def _serie(precios):
    c = pd.Series(precios, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 0.1, "low": c - 0.1, "close": c})


def test_serie_sana_pasa():
    df = _serie([100 + i * 0.2 for i in range(40)])
    ok, motivo = calidad_serie(df)
    assert ok, motivo
    print("OK serie con movimiento normal = válida")


def test_serie_plana_es_basura():
    ok, motivo = calidad_serie(_serie([100.0] * 40))
    assert not ok and "plana" in motivo
    print(f"OK serie plana rechazada ({motivo})")


def test_pocas_velas_es_basura():
    ok, motivo = calidad_serie(_serie([100, 101, 102]))
    assert not ok and "pocas" in motivo
    print("OK pocas velas rechazadas")


def test_nan_y_corrupta():
    df = _serie([100 + i for i in range(40)])
    df.loc[5, "close"] = np.nan
    assert not calidad_serie(df)[0]
    # high < low (corrupta)
    df2 = _serie([100 + i for i in range(40)])
    df2.loc[3, "high"] = 50.0
    assert not calidad_serie(df2)[0]
    print("OK NaN y vela invertida rechazadas")


def test_salto_imposible():
    p = [100 + i * 0.1 for i in range(20)] + [500.0] + [100 + i * 0.1 for i in range(20)]
    assert not calidad_serie(_serie(p))[0]
    print("OK salto imposible (>50%) rechazado")


def test_frames_limpios_separa():
    frames = {60: _serie([100 + i * 0.2 for i in range(40)]),   # sana
              300: _serie([100.0] * 40),                          # plana
              900: _serie([100, 101])}                            # pocas
    limpios, descartados = frames_limpios(frames)
    assert set(limpios) == {60}
    assert set(descartados) == {300, 900}
    print(f"OK frames_limpios deja solo el sano; descarta {list(descartados)}")


def test_escanear_datasets_basura():
    d = tempfile.mkdtemp()
    # archivo bueno
    with gzip.open(os.path.join(d, "EURUSD_otc__M1.csv.gz"), "wt") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for i in range(50):
            f.write(f"{i},1,1,1,1,0\n")
    # archivo basura (solo cabecera)
    with gzip.open(os.path.join(d, "AMD_otc__M1.csv.gz"), "wt") as f:
        f.write("timestamp,open,high,low,close,volume\n")
    basura = escanear_datasets(d)
    assert len(basura) == 1 and basura[0]["archivo"].startswith("AMD")
    # limpiar de verdad
    limpiar_datasets(d, borrar=True)
    assert not os.path.exists(os.path.join(d, "AMD_otc__M1.csv.gz"))
    assert os.path.exists(os.path.join(d, "EURUSD_otc__M1.csv.gz"))
    print("OK escanea y limpia archivos basura del disco (deja los buenos)")


if __name__ == "__main__":
    test_serie_sana_pasa()
    test_serie_plana_es_basura()
    test_pocas_velas_es_basura()
    test_nan_y_corrupta()
    test_salto_imposible()
    test_frames_limpios_separa()
    test_escanear_datasets_basura()
    print("\nTODOS OK — barrera de seguridad de datos (anti-basura)")
