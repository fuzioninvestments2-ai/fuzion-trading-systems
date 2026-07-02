"""
bot/pocket_client.py
====================
Cliente REAL de Pocket Option (lectura de precios en vivo), descubierto con la
sonda. Protocolo socket.io v4:

  handshake:  <-0{sid}  ->40  <-40{sid}  ->42["auth",{...}]  <-451-["successauth"]
  precios:    <-451-["updateStream",...] + BINARIO [["ASSET", ts, precio]]
  historial:  <-451-["updateHistoryNewFast",...] + BINARIO {asset,period,history}
  balance:    <-451-["successupdateBalance",...] + BINARIO {isDemo,balance}
  ping:       <-2   ->3

SOLO LECTURA: este cliente NO envía órdenes. Reconexión automática incluida.

Diseño (SOLID): recibe callbacks (on_tick/on_history/on_balance) por inyección,
así no está acoplado a la estrategia ni al historial ni a Telegram.
"""

import asyncio
import json
import logging

import websockets

URL_DEMO = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
URL_REAL = "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket"

_HEADERS = {"Origin": "https://pocketoption.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


class PocketOptionClient:
    """
    Cliente de lectura en vivo.

    Parámetros
    ----------
    ssid : str   -> la línea COMPLETA 42["auth",{...}] capturada del navegador.
    on_tick(asset, ts, price)     -> se llama en cada precio nuevo.
    on_history(dict)              -> {asset, period, history:[[t,p],...]} al suscribir.
    on_balance(dict)              -> {isDemo, balance}.
    demo : bool                   -> True usa el servidor demo.
    logger, base_delay, max_delay -> reconexión con backoff.
    """

    def __init__(self, ssid, on_tick=None, on_history=None, on_balance=None,
                 on_assets=None, demo=True, logger=None, base_delay=1.0,
                 max_delay=30.0):
        self.ssid = ssid.strip()
        self.on_tick = on_tick
        self.on_history = on_history
        self.on_balance = on_balance
        self.on_assets = on_assets       # lista de activos con su payout
        self.url = URL_DEMO if demo else URL_REAL
        self.log = logger or logging.getLogger("pocket_client")
        self.base_delay = base_delay
        self.max_delay = max_delay

        self._stopped = False
        self._pending_event = None      # nombre del evento cuyo binario esperamos
        self._asset = "EURUSD_otc"
        self._period = 60
        self._ws = None                 # websocket activo (para cambiar de activo)

    def stop(self):
        self._stopped = True

    async def set_asset(self, asset, period=60):
        """Cambia el activo escuchado en caliente (si hay conexión)."""
        self._asset, self._period = asset, period
        if self._ws is not None:
            await self.change_asset(self._ws, asset, period)

    async def run(self, asset="EURUSD_otc", period=60):
        """Conecta y escucha, reconectando con backoff ante caídas."""
        self._asset, self._period = asset, period
        attempt = 0
        while not self._stopped:
            try:
                async with websockets.connect(
                        self.url, additional_headers=_HEADERS,
                        ping_interval=None, max_size=None) as ws:
                    attempt = 0
                    self._ws = ws
                    self.log.info("Conectado a Pocket Option (%s).",
                                  "demo" if "demo" in self.url else "real")
                    await self._listen(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stopped:
                    break
                attempt += 1
                delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
                self.log.warning("Desconexión (%s). Reintento en %.0fs",
                                 exc, delay)
                await asyncio.sleep(delay)

    async def change_asset(self, ws, asset, period=60):
        """Cambia el activo que se está escuchando."""
        self._asset, self._period = asset, period
        await ws.send(f'42["subfor","{asset}"]')
        await ws.send(f'42["changeSymbol",{{"asset":"{asset}","period":{period}}}]')

    async def _listen(self, ws):
        async for raw in ws:
            if isinstance(raw, bytes):
                self._handle_binary(raw)
                continue
            await self._handle_text(ws, raw)

    async def _handle_text(self, ws, msg):
        if msg == "2":                                  # ping
            await ws.send("3")                          # pong
        elif msg.startswith("0") and not msg.startswith("40"):
            await ws.send("40")                         # abrir namespace
        elif msg.startswith("40"):
            await ws.send(self.ssid)                    # autenticar
        elif msg.startswith("451-"):
            # Evento con adjunto binario: guardamos el nombre para el binario.
            try:
                event = json.loads(msg[msg.index("["):])[0]
            except Exception:
                event = None
            self._pending_event = event
            if event == "successauth":
                # Autenticados -> pedir el flujo del activo actual.
                await self.change_asset(ws, self._asset, self._period)

    def _handle_binary(self, data):
        event = self._pending_event
        self._pending_event = None
        try:
            obj = json.loads(data.decode("utf-8"))
        except Exception:
            return

        if event == "updateStream":
            # obj = [["EURUSD_otc", ts_segundos, precio], ...]
            for row in obj:
                try:
                    asset, ts, price = row[0], float(row[1]), float(row[2])
                except (IndexError, TypeError, ValueError):
                    continue
                if self.on_tick:
                    self.on_tick(asset, ts, price)
        elif event == "updateHistoryNewFast":
            if self.on_history:
                self.on_history(obj)
        elif event == "successupdateBalance":
            if self.on_balance:
                self.on_balance(obj)
        elif event == "updateAssets":
            # Lista completa de activos; de aquí sacamos el PAYOUT de cada uno.
            if self.on_assets:
                self.on_assets(obj)
