"""
telegram/notifier.py (fuzion_fx)
================================
Envia las tarjetas al canal de Telegram usando la API HTTP del Bot con `requests`.

PORQUE se usa requests y NO `import telegram`: este paquete se llama `telegram`,
asi que importar la libreria homonima daria un choque de nombres. La API HTTP
(sendMessage / sendPhoto) es suficiente y evita el conflicto.

Robustez (Regla 3): reintentos con backoff ante fallos de red; nunca tumba el bot
si Telegram falla un envio.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

log = logging.getLogger("notifier")
_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    def __init__(self, bot_token: str, channel_id: str, timeout: int = 20) -> None:
        self.token = bot_token
        self.channel_id = channel_id
        self.timeout = timeout

    def _post(self, method: str, data: dict, files: dict = None):
        """POST con 3 reintentos y backoff (2s, 4s). Devuelve el JSON de Telegram
        (dict, con result.message_id) si acepto, o None. Truthy=exito para los
        `if notifier.send(...)` existentes (un dict no vacio es truthy)."""
        url = _API.format(token=self.token, method=method)
        espera = 2
        for intento in range(3):
            try:
                r = requests.post(url, data=data, files=files, timeout=self.timeout)
                if r.status_code == 200 and r.json().get("ok"):
                    return r.json()
                log.warning("Telegram %s respondio %s: %s", method, r.status_code,
                            r.text[:200])
            except requests.RequestException as e:
                log.warning("Fallo de red en %s (intento %d): %s", method,
                            intento + 1, e)
            time.sleep(espera)
            espera *= 2
        return None

    @staticmethod
    def _message_id(resp):
        """message_id (int) del JSON de Telegram, o None. Sirve para RESPONDER
        despues (poner el resultado JUSTO debajo de la señal)."""
        try:
            return int(resp["result"]["message_id"]) if resp else None
        except (KeyError, TypeError, ValueError):
            return None

    def send_text(self, text: str, parse_mode: str = "Markdown",
                  reply_to: Optional[int] = None):
        """Manda texto. Si reply_to viene, el mensaje va COMO RESPUESTA a ese id
        (hilo). Devuelve el message_id (int) o None."""
        data = {"chat_id": self.channel_id, "text": text, "parse_mode": parse_mode}
        if reply_to:
            data["reply_to_message_id"] = int(reply_to)
        return self._message_id(self._post("sendMessage", data))

    def send_alert(self, text: str, parse_mode: str = "Markdown",
                   reply_to: Optional[int] = None):
        """Alerta (auto-correccion). Igual que send_text, con marca visual."""
        return self.send_text(f"🚨 {text}", parse_mode, reply_to=reply_to)

    def send_photo(self, image_path: str, caption: str = "",
                   parse_mode: str = "Markdown", reply_to: Optional[int] = None):
        """Envia una foto (grafico) desde un ARCHIVO con pie. Devuelve message_id o
        None. Si falla, cae a texto."""
        data = {"chat_id": self.channel_id, "caption": caption,
                "parse_mode": parse_mode}
        if reply_to:
            data["reply_to_message_id"] = int(reply_to)
        try:
            with open(image_path, "rb") as fh:
                mid = self._message_id(self._post("sendPhoto", data,
                                                  files={"photo": fh}))
            if mid:
                return mid
        except OSError as e:
            log.warning("No se pudo abrir la imagen %s: %s", image_path, e)
        # Respaldo: al menos mandar el texto de la tarjeta.
        return self.send_text(caption, parse_mode, reply_to=reply_to)

    def enviar_a(self, chat_id: str, message: str, photo=None,
                 parse_mode: str = "Markdown") -> bool:
        """
        Manda la MISMA tarjeta a OTRO chat (un afiliado), con el mismo token. Para
        difundir a varios: `photo` en BYTES (no BytesIO), asi se puede reenviar a
        muchos sin que se consuma el puntero. Si falla la foto, cae a texto.
        """
        if photo is None:
            return self._post("sendMessage", {
                "chat_id": chat_id, "text": message, "parse_mode": parse_mode})
        ok = self._post("sendPhoto",
                        {"chat_id": chat_id, "caption": message,
                         "parse_mode": parse_mode}, files={"photo": photo})
        return ok or self._post("sendMessage", {
            "chat_id": chat_id, "text": message, "parse_mode": parse_mode})

    def send(self, message: str, photo_buffer=None,
             parse_mode: str = "Markdown", reply_to: Optional[int] = None):
        """
        Entrada unica de la tarjeta: si viene `photo_buffer` (PNG en memoria, p.
        ej. un grafico de matplotlib) manda foto+pie; si no, manda solo texto.
        `photo_buffer` puede ser bytes o un file-like (BytesIO). Devuelve el
        message_id (int) o None -> el bot lo guarda para colgar el RESULTADO debajo.
        """
        if photo_buffer is None:
            return self.send_text(message, parse_mode, reply_to=reply_to)
        data = {"chat_id": self.channel_id, "caption": message,
                "parse_mode": parse_mode}
        if reply_to:
            data["reply_to_message_id"] = int(reply_to)
        mid = self._message_id(self._post("sendPhoto", data,
                                          files={"photo": photo_buffer}))
        # Si el envio de la foto falla, al menos que llegue el texto.
        return mid if mid else self.send_text(message, parse_mode, reply_to=reply_to)
