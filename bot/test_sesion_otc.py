"""
bot/test_sesion_otc.py
======================
Valida SIN red que se descarte la sesión OTC VIEJA: Pocket Option reinicia el
precio sintético (salta de un nivel a otro). El bot mostraba 0.530 de una sesión
vieja mientras en vivo iba 0.544. `_recortar_sesion_otc` deja solo la sesión de
ahora (corta en el salto de reset).
"""

import pandas as pd
from bot.pocket_service import _recortar_sesion_otc, SALTO_SESION_OTC


def _bloque(precio, n, ts0):
    filas = []
    for i in range(n):
        c = precio + i * 0.0001            # micro-movimiento continuo dentro de sesión
        filas.append({"timestamp": (ts0 + i) * 1000, "open": c, "high": c + 0.0002,
                      "low": c - 0.0002, "close": c, "volume": 1})
    return filas


def test_corta_en_el_reset_de_sesion():
    # Sesión VIEJA en ~0.530 (50 velas) + reset + sesión NUEVA en ~0.544 (30 velas).
    vieja = _bloque(0.5300, 50, 1000)
    nueva = _bloque(0.5440, 30, 2000)      # salto 0.530 -> 0.544 (~2.6%) = reset
    df = pd.DataFrame(vieja + nueva)
    recortado = _recortar_sesion_otc(df)
    assert len(recortado) == 30, f"debe quedar solo la sesión nueva, quedó {len(recortado)}"
    assert abs(float(recortado["close"].iloc[0]) - 0.5440) < 0.001
    assert abs(float(recortado["close"].iloc[-1]) - 0.5440) < 0.01
    print("OK descarta la sesión vieja (0.530) y deja la actual (0.544)")


def test_sesion_continua_no_se_recorta():
    # Una sola sesión continua (sin salto) no se toca.
    df = pd.DataFrame(_bloque(0.5440, 60, 1000))
    assert len(_recortar_sesion_otc(df)) == 60
    print("OK una sesión continua no se recorta (no inventa cortes)")


def test_umbral_es_de_reinicio_no_de_movimiento_normal():
    # Un movimiento normal intra-sesión (< 1% entre velas) NO cuenta como reset.
    filas = _bloque(0.5440, 40, 1000)
    filas[20]["close"] = 0.5440 * (1 + SALTO_SESION_OTC * 0.5)   # medio umbral
    df = pd.DataFrame(filas)
    assert len(_recortar_sesion_otc(df)) == 40
    print("OK un movimiento normal no se confunde con un reinicio de sesión")


if __name__ == "__main__":
    test_corta_en_el_reset_de_sesion()
    test_sesion_continua_no_se_recorta()
    test_umbral_es_de_reinicio_no_de_movimiento_normal()
    print("\nTODOS OK — descarte de sesión OTC vieja (gráfico coincide con lo vivo)")
