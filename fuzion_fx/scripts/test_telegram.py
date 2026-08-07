"""
scripts/test_telegram.py (fuzion_fx)
====================================
Manda UN mensaje de prueba al canal/chat configurado, para confirmar que el
token y el TELEGRAM_CHANNEL_ID del .env funcionan (el ultimo eslabon).

    python fuzion_fx/scripts/test_telegram.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # fuzion_fx/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config import get_bot_config                     # noqa: E402
from telegram.notifier import TelegramNotifier             # noqa: E402


def main() -> None:
    tg = get_bot_config("f1_m1")["telegram"]
    token = tg.get("bot_token", "")
    canal = tg.get("channel_id", "")
    if not token or not canal:
        print("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHANNEL_ID en el .env.")
        print(f"  token: {'OK' if token else 'FALTA'} | canal: {canal or 'FALTA'}")
        return

    print(f"Enviando mensaje de prueba al chat {canal}...")
    notif = TelegramNotifier(token, canal)
    ok = notif.send_text(
        "*FUZION FX* — prueba de conexion ✅\n"
        "Si ves este mensaje, Telegram esta bien configurado. "
        "Las senales de los 4 bots llegaran aca.")
    if ok:
        print("ENVIADO. Revisa tu Telegram: deberia estar el mensaje.")
    else:
        print("NO se pudo enviar. Revisa que el token sea correcto y que el bot "
              "pueda escribir al chat (que le hayas dado /start al bot).")


if __name__ == "__main__":
    main()
