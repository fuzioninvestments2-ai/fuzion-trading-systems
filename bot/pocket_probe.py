"""
bot/pocket_probe.py
===================
SONDA de conexión a Pocket Option (cuenta DEMO), solo para DESCUBRIR el protocolo.

Qué hace:
  - Se conecta al WebSocket demo de Pocket Option.
  - Hace el "saludo" (handshake) de socket.io y responde a los pings.
  - Envía tu autenticación (SSID).
  - IMPRIME todos los mensajes que llegan durante unos segundos.

Con esos mensajes reales, podremos decodificar el formato de los PRECIOS y
construir el cliente definitivo. Es 100% LECTURA: NO envía ninguna orden.

Uso:
  1. En tu .env añade tu SSID (ver instrucciones que te dará Claude):
       POCKET_OPTION_SSID=42["auth",{...}]      (la línea completa del navegador)
  2. python3 bot/pocket_probe.py
  3. Copia TODO lo que imprima y pásaselo a Claude.
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import websockets

# Endpoint DEMO de Pocket Option (socket.io v4).
DEMO_URL = "wss://demo-api-v3.po.market/socket.io/?EIO=4&transport=websocket"


def _build_auth(ssid):
    """
    Acepta el SSID en dos formas:
      - La línea COMPLETA capturada del navegador: 42["auth",{...}]  -> se usa tal cual.
      - Solo el token/session -> se intenta envolver (mejor esfuerzo).
    """
    ssid = ssid.strip()
    if ssid.startswith("42["):
        return ssid
    # Fallback (puede necesitar ajuste según lo que revele la sonda):
    return '42["auth",{"session":"%s","isDemo":1,"uid":0,"platform":2}]' % ssid


async def _listen(ws, auth_msg):
    """Lee mensajes, responde al handshake/ping, y los imprime todos."""
    async for raw in ws:
        texto = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
        print("<<", texto[:400])

        # socket.io v4:
        if texto == "2":                       # ping del servidor
            await ws.send("3")                 # pong
        elif texto.startswith("0") and not texto.startswith("40"):
            await ws.send("40")                # abrir namespace por defecto
            print(">> enviado: 40")
        elif texto.startswith("40"):
            await ws.send(auth_msg)            # autenticación (SSID)
            print(">> enviado: auth (SSID)")


async def probe(seconds=40):
    ssid = os.getenv("POCKET_OPTION_SSID", "")
    if not ssid:
        raise RuntimeError(
            "Falta POCKET_OPTION_SSID en tu .env. Pega la línea completa "
            "42[\"auth\",{...}] que capturaste del navegador.")

    auth_msg = _build_auth(ssid)
    headers = {"Origin": "https://pocketoption.com",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    print(f"Conectando a Pocket Option (demo)... escucharé {seconds}s.")
    try:
        async with websockets.connect(
                DEMO_URL, additional_headers=headers,
                ping_interval=None) as ws:
            print("✅ Conectado. Mensajes recibidos:")
            task = asyncio.create_task(_listen(ws, auth_msg))
            try:
                await asyncio.wait_for(task, timeout=seconds)
            except asyncio.TimeoutError:
                task.cancel()
    except Exception as e:
        print(f"❌ Error de conexión: {type(e).__name__}: {e}")
    print("--- Fin de la sonda. Copia TODO lo de arriba y pásaselo a Claude. ---")


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    asyncio.run(probe())


if __name__ == "__main__":
    main()
