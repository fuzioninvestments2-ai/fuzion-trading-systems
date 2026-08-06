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

    def _post(self, method: str, data: dict, files: dict = None) -> bool:
        """POST con 3 reintentos y backoff (2s, 4s). True si Telegram acepto."""
        url = _API.format(token=self.token, method=method)
        espera = 2
        for intento in range(3):
            try:
                r = requests.post(url, data=data, files=files, timeout=self.timeout)
                if r.status_code == 200 and r.json().get("ok"):
                    return True
                log.warning("Telegram %s respondio %s: %s", method, r.status_code,
                            r.text[:200])
            except requests.RequestException as e:
                log.warning("Fallo de red en %s (intento %d): %s", method,
                            intento + 1, e)
            time.sleep(espera)
            espera *= 2
        return False

    def send_text(self, text: str, parse_mode: str = "Markdown") -> bool:
        return self._post("sendMessage", {
            "chat_id": self.channel_id, "text": text, "parse_mode": parse_mode})

    def send_photo(self, image_path: str, caption: str = "",
                   parse_mode: str = "Markdown") -> bool:
        """Envia una foto (grafico) desde un ARCHIVO con pie. Si falla, cae a texto."""
        try:
            with open(image_path, "rb") as fh:
                ok = self._post("sendPhoto",
                                {"chat_id": self.channel_id, "caption": caption,
                                 "parse_mode": parse_mode},
                                files={"photo": fh})
            if ok:
                return True
        except OSError as e:
            log.warning("No se pudo abrir la imagen %s: %s", image_path, e)
        # Respaldo: al menos mandar el texto de la tarjeta.
        return self.send_text(caption, parse_mode)

    def send(self, message: str, photo_buffer=None,
             parse_mode: str = "Markdown") -> bool:
        """
        Entrada unica de la tarjeta: si viene `photo_buffer` (PNG en memoria, p.
        ej. un grafico de matplotlib) manda foto+pie; si no, manda solo texto.
        `photo_buffer` puede ser bytes o un file-like (BytesIO).
        """
        if photo_buffer is None:
            return self.send_text(message, parse_mode)
        ok = self._post("sendPhoto",
                        {"chat_id": self.channel_id, "caption": message,
                         "parse_mode": parse_mode},
                        files={"photo": photo_buffer})
        # Si el envio de la foto falla, al menos que llegue el texto.
        return ok or self.send_text(message, parse_mode)
