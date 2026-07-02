"""
bot/telegram_signals.py
=======================
Bot de Telegram con MENÚ DE BOTONES (señales manuales), estilo Dewbot/Baloo.

Flujo: /start -> botones de mercado -> activo -> tiempo -> Start Analysis -> señal.

Toda la lógica está en signal_menu.py (probada). Aquí solo traducimos a botones
reales de Telegram (InlineKeyboard) y editamos el mensaje al pulsar.

CÓMO USARLO:
  1. Ten tu token en .env (TELEGRAM_BOT_TOKEN=...), igual que antes.
  2. pip install python-telegram-bot
  3. python3 bot/telegram_signals.py
  4. En Telegram, abre tu bot y pulsa /start.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.signal_menu import SignalMenu


def _keyboard(rows):
    """Convierte nuestras filas (etiqueta, dato) en botones de Telegram."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = [[InlineKeyboardButton(text=label, callback_data=data)
           for (label, data) in fila] for fila in rows]
    return InlineKeyboardMarkup(kb)


def run():
    # Cargar .env si está disponible.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(
            "Falta TELEGRAM_BOT_TOKEN en tu .env (créalo con @BotFather).")

    from telegram import Update
    from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                              ContextTypes)
    from telegram.error import BadRequest

    menu = SignalMenu()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text, rows = menu.main_menu()
        await update.message.reply_text(text, reply_markup=_keyboard(rows),
                                        parse_mode="Markdown")

    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()               # quita el "reloj" del botón
        uid = query.from_user.id
        text, rows = menu.handle_callback(uid, query.data)
        try:
            await query.edit_message_text(text, reply_markup=_keyboard(rows),
                                          parse_mode="Markdown")
        except BadRequest as e:
            # Si el texto es idéntico, Telegram se queja: lo ignoramos.
            if "not modified" not in str(e).lower():
                raise

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CallbackQueryHandler(on_button))

    print("🤖 Bot de SEÑALES (menú con botones) en marcha. Abre tu bot y pulsa /start.")
    app.run_polling()


if __name__ == "__main__":
    run()
