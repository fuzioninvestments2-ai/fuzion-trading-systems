"""
bot/telegram_signals.py
=======================
Bot de Telegram con MENÚ DE BOTONES (señales manuales), estilo Dewbot/Baloo.

Flujo: /start -> mercado -> activo -> tiempo -> Start Analysis -> señal.

Si existe tu SSID (archivo ssid.txt), el análisis usa PRECIOS REALES de Pocket
Option (demo, solo lectura). Si no hay SSID, usa datos simulados (para probar la
interfaz). Toda la lógica de menú está en signal_menu.py (probada).

Uso:
  1. .env con TELEGRAM_BOT_TOKEN=...  (para Telegram)
  2. ssid.txt con 42["auth",{...}]    (opcional, para precios reales)
  3. pip install python-telegram-bot
  4. python3 bot/telegram_signals.py  ->  en Telegram, /start
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.signal_menu import SignalMenu, TIMEFRAMES, _reason_from_votes
from bot.scoring_strategy import CALL, PUT, HOLD
from bot.pocket_probe import _load_ssid

# Segundos por timeframe (para pedirle a Pocket Option las velas correctas).
_TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600}


def to_po_code(display):
    """
    Convierte el nombre bonito del menú al código de Pocket Option.
      "EUR/USD OTC" -> "EURUSD_otc"   |   "EUR/USD" -> "EURUSD"
    (Funciona perfecto para forex; cripto/acciones pueden necesitar ajuste.)
    """
    s = display.strip()
    otc = s.upper().endswith("OTC")
    if otc:
        s = s[:-3].strip()
    s = s.replace("/", "").replace(" ", "")
    return s + "_otc" if otc else s


def _keyboard(rows):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = [[InlineKeyboardButton(text=label, callback_data=data)
           for (label, data) in fila] for fila in rows]
    return InlineKeyboardMarkup(kb)


def _format_real_signal(asset_display, tf, signal, conf, details, n, balance,
                        seg_next=None):
    # Dirección = hacia dónde se inclinan más los indicadores (siempre da UP/DOWN
    # salvo empate perfecto). Así el usuario ve una tendencia, no un "nada".
    call_s = details.get("call_score", 0.0)
    put_s = details.get("put_score", 0.0)
    if call_s > put_s:
        direccion, side = "⬆️ *UP* (CALL)", CALL
    elif put_s > call_s:
        direccion, side = "⬇️ *DOWN* (PUT)", PUT
    else:
        direccion, side = "⏸️ *Neutral*", HOLD

    # Fuerza HONESTA según la confianza: no engañamos, decimos si es débil.
    if conf >= 0.60:
        fuerza = "🟢 fuerte"
    elif conf >= 0.35:
        fuerza = "🟡 media"
    else:
        fuerza = "🔴 débil (mejor esperar)"

    votes = details.get("votes", {})
    motivo = (_reason_from_votes(votes, side) if side != HOLD
              else "indicadores equilibrados")
    bal = f"\n💰 Balance demo: ${balance:.2f}" if balance else ""

    # TIMING (clave en binarias): cuándo entrar. La entrada correcta es al ABRIR
    # la próxima vela, no a mitad. Avisamos los segundos que faltan.
    if seg_next is not None:
        if seg_next <= 5:
            timing = f"\n⏱️ *¡ENTRA YA!* (vela nueva en {seg_next}s)"
        else:
            timing = (f"\n⏱️ Entra al ABRIR la próxima vela: faltan "
                      f"*{seg_next}s* (no entres a mitad)")
    else:
        timing = ""

    return (f"📈 *{asset_display}*  |  ⏱️ *{tf}*   (PRECIOS REALES ✅)\n"
            f"Dirección: {direccion}\n"
            f"Fuerza: {fuerza}  _(confianza {conf:.0%})_\n"
            f"Motivo: {motivo}\n"
            f"Velas: {n}{bal}{timing}\n\n"
            f"⚠️ _No es recomendación; ningún bot acierta siempre. Cuenta demo._")


def run():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en tu .env (con @BotFather).")

    from telegram import Update
    from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                              ContextTypes)
    from telegram.error import BadRequest

    menu = SignalMenu()

    # Si hay SSID -> preparamos el servicio de precios REALES.
    ssid = _load_ssid()
    service = None
    if ssid:
        from bot.pocket_service import PocketService
        service = PocketService(ssid, demo=True)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        modo = "PRECIOS REALES ✅" if service else "datos simulados (sin SSID)"
        text, rows = menu.main_menu()
        await update.message.reply_text(
            f"{text}\n_Modo: {modo}_", reply_markup=_keyboard(rows),
            parse_mode="Markdown")

    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        uid = query.from_user.id

        if query.data == "analyze":
            st = menu._st(uid)
            asset_display = st.get("asset")
            tf = st.get("timeframe")
            if not asset_display or not tf:
                await query.answer("Elige activo y tiempo primero", show_alert=True)
                return
            if service is None:
                # Sin SSID: usamos la simulación del menú (interfaz).
                text, rows = menu.analyze(uid)
            else:
                await query.edit_message_text(
                    f"🔎 Analizando *{asset_display}* ({tf}) con precios "
                    f"reales… espera unos segundos.", parse_mode="Markdown")
                code = to_po_code(asset_display)
                period = _TF_SECONDS.get(tf, 60)
                signal, conf, details, n, seg = await service.analyze(code, period)
                text = _format_real_signal(asset_display, tf, signal, conf,
                                           details, n, service.balance, seg)
                rows = [[("🔁 Analizar de nuevo", "analyze")],
                        [("📊 Otro activo", "back:market"), ("🏠 Menú", "back:main")]]
            await _safe_edit(query, text, rows)
            return

        text, rows = menu.handle_callback(uid, query.data)
        await _safe_edit(query, text, rows)

    async def _safe_edit(query, text, rows):
        from telegram.error import BadRequest
        try:
            await query.edit_message_text(text, reply_markup=_keyboard(rows),
                                          parse_mode="Markdown")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    async def _post_init(app):
        if service:
            await service.start()      # arranca la conexión a PO en segundo plano
            print("🔌 Conectando a Pocket Option (precios reales)...")

    app = Application.builder().token(token).post_init(_post_init).build()
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CallbackQueryHandler(on_button))

    modo = "PRECIOS REALES" if service else "SIMULADO (sin ssid.txt)"
    print(f"🤖 Bot de SEÑALES en marcha [{modo}]. Abre tu bot y pulsa /start.")
    app.run_polling()


if __name__ == "__main__":
    run()
