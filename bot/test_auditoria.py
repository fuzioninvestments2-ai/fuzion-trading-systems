"""
bot/test_auditoria.py
=====================
Valida el auditor de completitud SIN red: las 5 pasadas (existe, no basura, sin
huecos, sin duplicados, completo), y la detección de activo×tf sin archivo.
"""

import csv
import gzip
import os
import tempfile

from bot.auditoria import (auditar_serie, auditar_carpeta,
                           faltantes_por_activo, _huecos, _segundos_de_tf)

_COLS = ["timestamp", "open", "high", "low", "close", "volume"]


def _escribir(carpeta, activo, tf, velas):
    """Crea datasets/{activo}__{tf}.csv.gz con las velas dadas."""
    ruta = os.path.join(carpeta, f"{activo}__{tf}.csv.gz")
    with gzip.open(ruta, "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_COLS)
        for v in velas:
            w.writerow([v["timestamp"], v["open"], v["high"], v["low"],
                        v["close"], v.get("volume", 1)])
    return ruta


def _serie_sana(n, period_s=60, base_ms=1_700_000_000_000, precio=1.10):
    """Serie contigua, con pequeña variación (no plana) y sin duplicados."""
    velas = []
    paso = period_s * 1000
    for i in range(n):
        p = precio + (i % 10) * 0.0001            # variación -> no plana
        velas.append({"timestamp": base_ms + i * paso, "open": p,
                      "high": p + 0.0002, "low": p - 0.0002, "close": p,
                      "volume": 1})
    return velas


def test_segundos_de_tf():
    assert _segundos_de_tf("M1") == 60
    assert _segundos_de_tf("tf300") == 300
    assert _segundos_de_tf("raro") is None
    print("OK _segundos_de_tf mapea M1/tf<N>")


def test_huecos_detecta_agujeros():
    ts = [0, 60_000, 120_000, 180_000]            # contigua a 60s
    assert _huecos(ts, 60) == 0.0
    ts_hueco = [0, 60_000, 600_000]               # falta un tramo grande
    assert _huecos(ts_hueco, 60) > 0.5
    print("OK _huecos mide la fracción faltante")


def test_serie_completa_pasa_las_5():
    with tempfile.TemporaryDirectory() as d:
        ruta = _escribir(d, "EURUSD_otc", "M1", _serie_sana(3200, 60))
        res = auditar_serie(ruta, "M1")
        assert res["completo"] is True, res["motivos"]
        assert res["sana"] and res["sin_huecos"] and res["sin_duplicados"]
        assert res["suficientes"]
        print("OK serie sana y suficiente pasa las 5 pasadas")


def test_pocas_velas_queda_pendiente():
    with tempfile.TemporaryDirectory() as d:
        ruta = _escribir(d, "EURUSD_otc", "M1", _serie_sana(50, 60))
        res = auditar_serie(ruta, "M1")
        assert res["completo"] is False
        assert not res["suficientes"]             # 50 < umbral M1
        print("OK pocas velas -> pendiente (pasada 5)")


def test_duplicados_queda_pendiente():
    with tempfile.TemporaryDirectory() as d:
        velas = _serie_sana(2100, 5)              # tf5 umbral 2000
        velas.append(dict(velas[-1]))             # timestamp repetido
        ruta = _escribir(d, "EURUSD_otc", "tf5", velas)
        res = auditar_serie(ruta, "tf5")
        assert res["duplicados"] >= 1
        assert res["completo"] is False           # duplicados -> no pasa
        print("OK duplicados -> pendiente (pasada 4)")


def test_auditar_carpeta_separa_completos_y_pendientes():
    with tempfile.TemporaryDirectory() as d:
        _escribir(d, "EURUSD_otc", "M1", _serie_sana(3200, 60))   # completo
        _escribir(d, "GBPUSD_otc", "M1", _serie_sana(30, 60))     # pendiente
        completos, pendientes = auditar_carpeta(d)
        assert len(completos) == 1 and len(pendientes) == 1
        print("OK auditar_carpeta separa completos de pendientes")


def test_faltantes_detecta_sin_archivo():
    with tempfile.TemporaryDirectory() as d:
        _escribir(d, "EURUSD_otc", "M1", _serie_sana(100, 60))
        faltan = faltantes_por_activo(d, ["EURUSD_otc"], [60, 300])
        # M1 existe; tf300 falta.
        assert "EURUSD_otc" in faltan
        assert "tf300" in faltan["EURUSD_otc"]
        assert "M1" not in faltan["EURUSD_otc"]
        print("OK faltantes_por_activo detecta activo×tf sin archivo")


if __name__ == "__main__":
    test_segundos_de_tf()
    test_huecos_detecta_agujeros()
    test_serie_completa_pasa_las_5()
    test_pocas_velas_queda_pendiente()
    test_duplicados_queda_pendiente()
    test_auditar_carpeta_separa_completos_y_pendientes()
    test_faltantes_detecta_sin_archivo()
    print("\nTODOS OK — auditor de completitud (5 pasadas)")
