"""
bot/telegram_bot.py
===================
Capa de RED del bot de Telegram: conecta Telegram con `BotController`.

Solo TRADUCE mensajes de Telegram a llamadas del controlador. Toda la lógica
está en telegram_controller.py (que sí está probado). Esta capa no se puede
probar sin un token real, por eso se mantiene mínima.

CÓMO OBTENER UN TOKEN (gratis):
  1. En Telegram, busca el bot oficial "@BotFather".
  2. Escríbele /newbot y sigue los pasos (nombre + usuario que termine en 'bot').
  3. Te dará un TOKEN largo (ej. 123456:ABC-DEF...).
  4. Guárdalo en tu archivo .env:  TELEGRAM_BOT_TOKEN=tu_token
     (el .env está en .gitignore; NUNCA lo subas a git).

Requiere la librería:  pip install python-telegram-bot
Ejecutar:              python3 bot/telegram_bot.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.telegram_controller import BotController


def run():
    # Cargar .env si python-dotenv está disponible (opcional).
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(
            "Falta TELEGRAM_BOT_TOKEN. Crea un bot con @BotFather y pon el token "
            "en tu archivo .env (ver instrucciones arriba). NUNCA lo subas a git.")

    # Import perezoso: solo cuando de verdad vamos a conectar.
    from telegram import Update
    from telegram.ext import (Application, CommandHandler, MessageHandler,
                              filters, ContextTypes)

    controller = BotController()

    async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Traducimos el texto recibido a una respuesta del controlador.
        texto = update.message.text if update.message else ""
        respuesta = controller.handle(texto)
        await update.message.reply_text(respuesta)

    app = Application.builder().token(token).build()
    # Mapear los comandos y también texto libre a la misma función.
    for cmd in ("start", "stop", "estado", "status", "senal", "signal",
                "preset", "help", "ayuda"):
        app.add_handler(CommandHandler(cmd, responder))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("🤖 Bot de Telegram en marcha. Escríbele /help en Telegram.")
    app.run_polling()


if __name__ == "__main__":
    run()
