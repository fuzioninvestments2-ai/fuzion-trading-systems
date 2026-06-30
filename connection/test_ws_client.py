"""
connection/test_ws_client.py
============================
Prueba de validación del cliente WebSocket robusto (Regla 4).

Estrategia: levantamos un SERVIDOR WebSocket LOCAL que simula un feed OTC
inestable: en cada conexión envía un par de mensajes y luego CIERRA el socket
a propósito (simula un micro-corte). El cliente debe RECONECTARSE solo varias
veces gracias al backoff, y seguir recibiendo mensajes.

Verifica:
  (A) Reconexión: el servidor recibe varias conexiones (el cliente reconectó).
  (B) Continuidad: se reciben mensajes a pesar de los cortes.
  (C) Backoff acotado: los retardos calculados nunca superan max_delay.
"""

import asyncio
import websockets
from ws_client import ReconnectingWebSocketClient

# Contador de cuántas veces el servidor aceptó una conexión nueva. Si el cliente
# reconecta, este número crece (señal de que la reconexión funciona).
connection_count = 0


async def server_handler(websocket, *args):
    """Simula un feed que envía 2 mensajes y corta (micro-corte OTC)."""
    global connection_count
    connection_count += 1
    my_id = connection_count
    for i in range(2):
        await websocket.send(f"conn{my_id}-tick{i}")
        await asyncio.sleep(0.01)
    await websocket.close()          # corte deliberado -> fuerza reconexión


async def test_reconexion():
    received = []
    done = asyncio.Event()

    async def on_message(msg):
        # Handler inyectado (inyección de dependencias): solo acumula mensajes.
        received.append(msg)
        if len(received) >= 6:       # ~3 conexiones * 2 mensajes
            done.set()

    server = await websockets.serve(server_handler, "localhost", 8771)
    client = ReconnectingWebSocketClient(
        "ws://localhost:8771", on_message,
        base_delay=0.05, max_delay=0.4, log_file="ws_client_test.log")

    task = asyncio.create_task(client.run())
    try:
        # Si en 10s no recibimos lo esperado, algo va mal -> fallo de prueba.
        await asyncio.wait_for(done.wait(), timeout=10)
    finally:
        client.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        server.close()
        await server.wait_closed()

    print("Mensajes recibidos:", received)
    print("Conexiones aceptadas por el servidor:", connection_count)

    # (A) y (B)
    assert len(received) >= 6, "❌ No se recibieron suficientes mensajes"
    assert connection_count >= 3, "❌ El cliente no reconectó varias veces"
    print("✅ (A) Reconexión automática verificada.")
    print("✅ (B) Continuidad de mensajes verificada.")


def test_backoff_acotado():
    """El retardo del backoff nunca debe exceder max_delay."""
    client = ReconnectingWebSocketClient(
        "ws://localhost:9999", lambda m: None,
        base_delay=1.0, max_delay=30.0, log_file="ws_client_test.log")
    for attempt in range(1, 20):
        d = client._backoff(attempt)
        assert 0 <= d <= client.max_delay, \
            f"❌ Backoff fuera de rango en intento {attempt}: {d}"
    print("✅ (C) Backoff siempre acotado por max_delay.")


if __name__ == "__main__":
    asyncio.run(test_reconexion())
    print("-" * 60)
    test_backoff_acotado()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
