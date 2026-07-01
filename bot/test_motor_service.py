"""
bot/test_motor_service.py
=========================
Prueba del servicio del motor conectado al controlador de Telegram (Regla 4).

Arranca el motor REAL en un hilo (con feed simulado, sin red), lo deja correr un
instante, consulta estado por los comandos de Telegram y lo detiene.

Verifica:
  (A) /start arranca el motor (el hilo queda vivo).
  (B) Tras correr, /estado devuelve estadísticas y /stop lo detiene limpio.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.motor_service import MotorService
from bot.telegram_controller import BotController


def test_arranque_estado_parada():
    # Base de datos en memoria y sin pausa entre ticks -> test rápido.
    motor = MotorService(preset="moderado", db_path=":memory:", tick_delay=0.0)
    ctrl = BotController(start_fn=motor.start, stop_fn=motor.stop,
                         status_fn=motor.status, signal_fn=motor.last_signal)

    # (A) Arrancar.
    r_start = ctrl.handle("/start")
    assert "ARRANCADO" in r_start
    assert motor.is_running(), "❌ El hilo del motor debía estar vivo"

    # Dejar correr un instante para que procese velas.
    time.sleep(0.3)

    # (B) Estado y parada.
    r_estado = ctrl.handle("/estado")
    assert "Estado" in r_estado
    r_stop = ctrl.handle("/stop")
    assert "DETENIDO" in r_stop
    time.sleep(0.1)
    assert not motor.is_running(), "❌ El motor debía detenerse"

    print("✅ (A)(B) Telegram arranca, consulta estado y detiene el motor.")
    print("     estado:", r_estado.replace(chr(10), " | "))


if __name__ == "__main__":
    test_arranque_estado_parada()
    print("-" * 60)
    print("✅ PRUEBA PASADA.")
