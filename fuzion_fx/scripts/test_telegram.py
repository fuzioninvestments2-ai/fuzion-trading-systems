"""
scripts/test_telegram.py (fuzion_fx)
====================================
Manda un mensaje de prueba por CADA uno de los 4 bots (con su propio token) al
chat configurado. Sirve para confirmar que los 4 tokens y el TELEGRAM_CHANNEL_ID
del .env funcionan: deberian llegar 4 mensajes, uno a cada bot (F1..F).

    python fuzion_fx/scripts/test_telegram.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # fuzion_fx/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config import bot_ids, get_bot_config           # noqa: E402
from telegram.notifier import TelegramNotifier             # noqa: E402


def main() -> None:
    algun_error = False
    for bid in bot_ids():
        cfg = get_bot_config(bid)
        tg = cfg.get("telegram", {})
        token = cfg.get("telegram_token") or tg.get("bot_token")
        canal = tg.get("channel_id")
        nombre = cfg.get("name", bid)

        if not token or not canal:
            print(f"[{bid}] FALTA token o canal  (token: {'OK' if token else 'FALTA'}"
                  f" | canal: {canal or 'FALTA'})")
            algun_error = True
            continue

        notif = TelegramNotifier(token, canal)
        ok = notif.send_text(
            f"*{nombre}* — prueba de conexion ✅\n"
            f"Este bot ({cfg.get('card_label', bid)}) esta configurado y listo.")
        estado = "ENVIADO" if ok else "FALLO"
        if not ok:
            algun_error = True
        print(f"[{bid}] {nombre} -> {estado}")

    print("---")
    if algun_error:
        print("Algun bot no pudo enviar. Revisa su token en el .env y que le hayas "
              "dado /start a ese bot en Telegram.")
    else:
        print("LISTO: revisa Telegram, deberian estar los 4 mensajes (F1..F).")


if __name__ == "__main__":
    main()
