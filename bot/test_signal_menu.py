"""
bot/test_signal_menu.py
=======================
Prueba de la lógica del menú interactivo de señales (Regla 4), sin Telegram.

Simula que un usuario navega: menú -> mercado -> activo -> tiempo -> analizar.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.signal_menu import SignalMenu, MARKETS, TIMEFRAMES


def test_flujo_completo():
    menu = SignalMenu()
    uid = 123

    # 1) Menú principal: un botón por mercado.
    text, rows = menu.main_menu()
    assert "mercado" in text.lower()
    datos = [b[1] for fila in rows for b in fila]
    assert "market:otc" in datos, datos

    # 2) Elegir OTC -> aparecen activos + Volver.
    text, rows = menu.handle_callback(uid, "market:otc")
    datos = [b[1] for fila in rows for b in fila]
    assert any(d.startswith("asset:") for d in datos), datos
    assert "back:main" in datos

    # 3) Elegir un activo -> aparecen los tiempos.
    text, rows = menu.handle_callback(uid, "asset:EUR/USD OTC")
    datos = [b[1] for fila in rows for b in fila]
    assert "tf:M1" in datos, datos

    # 4) Elegir tiempo -> botón Start Analysis.
    text, rows = menu.handle_callback(uid, "tf:M1")
    datos = [b[1] for fila in rows for b in fila]
    assert "analyze" in datos, datos

    # 5) Analizar -> devuelve una señal con dirección y aviso de simulado.
    text, rows = menu.handle_callback(uid, "analyze")
    assert ("UP" in text or "DOWN" in text or "Sin señal" in text), text
    assert "SIMULAD" in text.upper(), "❌ Debe avisar que los datos son simulados"
    print("✅ Flujo completo del menú OK. Ejemplo de señal:")
    print("   " + text.replace("\n", " | "))


def test_estado_por_usuario():
    # Dos usuarios distintos no deben pisarse el estado.
    menu = SignalMenu()
    menu.handle_callback(1, "market:otc")
    menu.handle_callback(1, "asset:EUR/USD OTC")
    menu.handle_callback(2, "market:crypto")
    menu.handle_callback(2, "asset:BTC/USD OTC")
    assert menu._st(1)["asset"] == "EUR/USD OTC"
    assert menu._st(2)["asset"] == "BTC/USD OTC"
    print("✅ El estado se mantiene separado por usuario.")


if __name__ == "__main__":
    test_flujo_completo()
    test_estado_por_usuario()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
