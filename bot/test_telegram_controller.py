"""
bot/test_telegram_controller.py
===============================
Prueba de la lógica de comandos de Telegram (Regla 4), SIN red ni token.

Verifica:
  (A) /start y /stop cambian el estado y llaman a las funciones inyectadas.
  (B) /estado refleja el estado y las estadísticas.
  (C) /preset cambia el preset; uno inválido no rompe.
  (D) Un comando desconocido devuelve la ayuda.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.telegram_controller import BotController


def test_start_stop():
    llamadas = {"start": 0, "stop": 0}
    ctrl = BotController(start_fn=lambda: llamadas.__setitem__("start", llamadas["start"] + 1),
                         stop_fn=lambda: llamadas.__setitem__("stop", llamadas["stop"] + 1))

    r1 = ctrl.handle("/start")
    assert ctrl.running and "ARRANCADO" in r1 and llamadas["start"] == 1
    # Arrancar de nuevo no debe re-llamar start_fn.
    r2 = ctrl.handle("/start")
    assert "ya está en marcha" in r2 and llamadas["start"] == 1

    r3 = ctrl.handle("/stop")
    assert (not ctrl.running) and "DETENIDO" in r3 and llamadas["stop"] == 1
    print("✅ (A) /start y /stop funcionan y llaman a las funciones inyectadas.")


def test_estado_con_stats():
    ctrl = BotController(status_fn=lambda: {"total_trades": 5, "win_rate": 0.6,
                                            "total_profit": 3.2})
    r = ctrl.handle("/estado")
    assert "Detenido" in r and "5" in r and "60%" in r
    print("✅ (B) /estado muestra estado y estadísticas.")


def test_preset():
    ctrl = BotController()
    assert "agresivo" in ctrl.handle("/preset agresivo")
    assert ctrl.preset == "agresivo"
    # Preset inválido: mensaje de error, sin romper.
    r = ctrl.handle("/preset inexistente")
    assert "❌" in r
    print("✅ (C) /preset cambia el preset y maneja errores.")


def test_desconocido():
    ctrl = BotController()
    assert "no reconocido" in ctrl.handle("/loquesea")
    assert "Comandos disponibles" in ctrl.handle("/help")
    print("✅ (D) Comando desconocido -> ayuda.")


if __name__ == "__main__":
    test_start_stop()
    test_estado_con_stats()
    test_preset()
    test_desconocido()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
