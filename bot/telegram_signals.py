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

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.signal_menu import SignalMenu, TIMEFRAMES, _reason_from_votes
from bot.scoring_strategy import CALL, PUT, HOLD
from bot.pocket_probe import _load_ssid

# Segundos por timeframe (para el timing y la ecuación de tiempos).
_TF_SECONDS = {"S5": 5, "S10": 10, "S15": 15, "S30": 30,
               "M1": 60, "M2": 120, "M3": 180, "M5": 300, "M10": 600,
               "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}


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

    # Cuántos indicadores apoyan la dirección ganadora.
    call_v = details.get("call_votes", 0)
    put_v = details.get("put_votes", 0)
    votos_ganadores = max(call_v, put_v)

    # Fuerza HONESTA según la confianza: no engañamos, decimos si es débil.
    if conf >= 0.60:
        fuerza = "🟢 fuerte"
    elif conf >= 0.35:
        fuerza = "🟡 media"
    else:
        fuerza = "🔴 débil"

    # VEREDICTO CLARO (lo más importante): decir SÍ operar o NO operar.
    # El porqué: en binarias se gana operando POCAS veces pero buenas. Una señal
    # débil o con pocos indicadores de acuerdo = NO operar.
    if side == HOLD or votos_ganadores < 2 or conf < 0.35:
        veredicto = "🚫 *NO OPERAR* — señal floja, espera una mejor"
    elif conf >= 0.55 and votos_ganadores >= 3:
        veredicto = "✅ *OPERAR* — señal fuerte y con confluencia"
    else:
        veredicto = "🟡 *OPCIONAL* — señal media (con cautela)"

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
            f"\n{veredicto}\n\n"
            f"Dirección: {direccion}\n"
            f"Fuerza: {fuerza}  _(confianza {conf:.0%}, {votos_ganadores} indicadores)_\n"
            f"Motivo: {motivo}\n"
            f"Velas: {n}{bal}{timing}\n\n"
            f"⚠️ _No es recomendación; ningún bot acierta siempre. Cuenta demo._")


def _tf_label(seconds):
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return "1D"


def _format_deep(asset_display, tf, result, seg, balance, n_ticks):
    """Formatea el resultado del análisis profundo multi-temporalidad."""
    # Caso especial: mercado cerrado.
    if result.get("cerrado"):
        return (f"📈 *{asset_display}*  |  ⏱️ *{tf}*\n\n"
                f"🕐 *{result.get('direccion', 'Mercado cerrado')}*\n\n"
                f"_Este activo real no opera ahora. Prueba un activo *OTC* "
                f"(disponible 24/7)._")

    veredicto = result.get("veredicto", "")
    direccion = result.get("direccion", "")
    fuerza = result.get("fuerza", 0.0)
    coinciden = result.get("coinciden", "")
    por = result.get("por_tiempo", {})
    emo = {"CALL": "⬆️", "PUT": "⬇️", "NEUTRAL": "⏸️"}

    def _dot(conf):
        # 25% o más = buena entrada (verde), según la lectura del usuario; 15-25%
        # aceptable (amarillo); por debajo, débil.
        return "🟢" if conf >= 0.25 else ("🟡" if conf >= 0.15 else "▫️")

    filas = []
    for tfs, v in sorted(por.items()):
        flecha = emo.get(v["dir"], "⏸️")
        if v["velas"] < 6:
            estado = "·  _(pocos datos)_"
        elif v["dir"] == "NEUTRAL":
            estado = "▫️ neutral"
        else:
            estado = f"{_dot(v['conf'])} {v['conf']:.0%}"
        filas.append(f"`{_tf_label(tfs):>4}`  {flecha}  {estado}")
    desglose = "\n".join(filas) if filas else "  (sin datos suficientes)"

    if seg is not None:
        timing = (f"\n⏱️ *¡ENTRA YA!* (vela en {seg}s)" if seg <= 5
                  else f"\n⏱️ Entra al ABRIR la próxima vela: *{seg}s*")
    else:
        timing = ""
    bal = f"\n💰 Balance demo: ${balance:.2f}" if balance else ""
    coin = f"  ({coinciden})" if coinciden else ""

    # Payout (% de pago). Si es bajo, avisamos (regla del usuario: no entrar).
    payout = result.get("payout")
    if payout is not None:
        if result.get("pago_bajo"):
            pago = f"\n💵 *Pago: {payout:.0f}%* ⚠️ BAJO — mejor NO entrar aquí"
        else:
            pago = f"\n💵 Pago: {payout:.0f}%"
    else:
        pago = ""

    # Calibración aprendida (si existe).
    umbral = result.get("umbral")
    wr = result.get("win_rate_hist")
    if umbral is not None and wr is not None:
        aprendido = (f"\n🎓 Umbral aprendido: {umbral:.0%} "
                     f"_(win-rate histórico {wr:.0%})_")
    else:
        aprendido = ""

    # Indicadores que el bot ha APRENDIDO a valorar más en este activo.
    _NOM = {"rsi": "RSI", "macd": "MACD", "bollinger": "Bollinger",
            "moving_averages": "Medias", "stochastic": "Estocástico",
            "donchian": "Donchian", "vwap": "VWAP", "patterns": "Patrones"}
    pesos_top = result.get("pesos_top")
    if pesos_top:
        detalle = ", ".join(f"{_NOM.get(n, n)} {hr:.0%}" for n, hr in pesos_top)
        fuente = result.get("pesos_fuente")
        etiqueta = (" _(de señales reales)_" if fuente == "real"
                    else " _(de backtest)_" if fuente == "backtest" else "")
        aprendido += f"\n🧠 Mejores indicadores aquí: {detalle}{etiqueta}"

    # Win-rate REAL del bot (de sus propias señales ya resueltas), no del backtest.
    wrr = result.get("win_rate_real")
    if wrr is not None:
        aprendido += (f"\n📈 Acierto REAL del bot aquí: {wrr:.0%} "
                      f"_({result.get('senales_reales', 0)} señales medidas)_")

    # Alerta anti-manipulación (si el mercado se comportó raro).
    manip = result.get("manipulacion")
    alerta = (f"\n🛡️ *ALERTA:* mercado raro ({', '.join(manip)}) → mejor NO operar"
              if manip else "")
    if result.get("inestable"):
        alerta += "\n🔄 *INDECISIÓN:* la señal cambió de dirección → espera"
    if result.get("vacio"):
        alerta += ("\n🕳️ *VACÍO DE MERCADO:* " + ", ".join(result["vacio"])
                   + " → feed no fiable, NO operes")
    if result.get("indecision_vela"):
        alerta += "\n🕯️ *DOJI:* vela de indecisión → espera dirección clara"
    if result.get("contra_tendencia"):
        alerta += ("\n📉 *CONTRA TENDENCIA:* la señal va contra el tiempo mayor "
                   "→ ALTO RIESGO, mejor operar a favor de la tendencia")
    na = result.get("nivel_alerta")
    if na:
        if na[0] == "techo":
            alerta += (f"\n🧱 *PEGADO AL TECHO* ({na[1]}): zona de resistencia → "
                       "puede rechazar a la baja")
        else:
            alerta += (f"\n🧱 *PEGADO AL PISO* ({na[1]}): zona de soporte → "
                       "puede rebotar al alza")

    explicacion = result.get("explicacion", "")
    expl = f"\n🧭 *Lectura:* _{explicacion}_" if explicacion else ""

    reg = result.get("regime")
    adxv = result.get("adx")
    # El "Modo" no es solo etiqueta: el bot YA ajustó el peso de sus indicadores
    # a este régimen (en Slide manda MACD/medias; en Oscillate los rebotes).
    reg_map = {
        "slide": "📈 Slide (tendencia) → prioriza MACD/medias",
        "oscillate": "🔁 Oscillate (rango) → prioriza rebotes techo/piso",
        "mixto": "🔀 mixto → pesos equilibrados",
    }
    modo = (f"\n📐 Modo: {reg_map.get(reg, '')}"
            + (f" _(ADX {adxv})_" if adxv is not None else "")) if reg else ""

    # Patrones de vela (la FORMA de la vela): confirmación o indecisión.
    pats = result.get("patrones")
    patrones = f"\n🕯️ *Patrones:* {', '.join(pats)}" if pats else ""

    # VWAP: de qué lado del "precio justo" estamos (contexto profesional).
    vw = result.get("vwap")
    if vw and vw.get("vwap") is not None:
        lado = {"CALL": "por ENCIMA (sesgo alcista)",
                "PUT": "por DEBAJO (sesgo bajista)",
                "HOLD": "pegado al VWAP (neutral)"}.get(vw["side"], "")
        vwap_txt = f"\n📏 *VWAP:* precio {lado} _({vw['dist_pct']:+.2f}%)_"
    else:
        vwap_txt = ""

    # Techo/piso más cercanos (soporte/resistencia): dónde puede rebotar/rechazar.
    lv = result.get("levels")
    if lv and (lv.get("resistencias") or lv.get("soportes")):
        techo = f"{lv['resistencias'][0]:.5f}" if lv.get("resistencias") else "—"
        piso = f"{lv['soportes'][0]:.5f}" if lv.get("soportes") else "—"
        niveles_txt = f"\n🧱 *Techo:* {techo}  ·  *Piso:* {piso}"
    else:
        niveles_txt = ""

    # Cobertura de datos (transparencia): cuántas velas M1 lleva el activo. Los
    # tiempos largos se llenan con el uso; el historial se guarda entre reinicios.
    m1 = result.get("m1_count")
    if m1 is not None:
        cobertura = (f"\n📚 Historial: {m1} velas M1 acumuladas"
                     + ("" if m1 >= 400 else
                        " _(los tiempos largos se llenan con el tiempo)_"))
    else:
        cobertura = ""

    return (f"📈 *{asset_display}*   ⏱️ *{tf}*   (REALES ✅)\n"
            f"{alerta}\n"
            f"\n*{veredicto}*\n"
            f"Dirección: {direccion}{modo}\n"
            f"🎯 Alineación: *{fuerza:.0%}*  ({coinciden}){expl}{patrones}{vwap_txt}{niveles_txt}\n\n"
            f"🔎 *Panel de tiempos:*\n{desglose}\n"
            f"{timing}{pago}{bal}{aprendido}{cobertura}\n\n"
            f"⚠️ _No es recomendación; ningún bot acierta siempre. Demo._")


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
    collector = None
    if ssid:
        from bot.pocket_service import PocketService
        service = PocketService(ssid, demo=True)
        # Colector 24/7: usa una SEGUNDA conexión con el mismo SSID. Pocket Option
        # a veces no permite dos conexiones a la vez y provoca desconexiones. Por
        # eso viene DESACTIVADO por defecto (más estable con una sola conexión).
        # Para activarlo: crea en el .env la línea  ENABLE_COLLECTOR=1
        if os.getenv("ENABLE_COLLECTOR", "").strip() in ("1", "true", "yes"):
            from bot.collector import Collector
            collector = Collector(ssid, service.repo, demo=True)

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
                    f"🧘 Leyendo *{asset_display}* ({tf}) con atención…\n"
                    f"_Concentrándome en el mercado unos segundos para darte "
                    f"la mejor lectura._", parse_mode="Markdown")
                code = to_po_code(asset_display)
                period = _TF_SECONDS.get(tf, 60)
                # Le decimos al colector que priorice este activo: así sus tiempos
                # largos se llenan antes para la próxima lectura.
                if collector:
                    collector.set_focus(code)
                result, seg, n = await service.analyze(code, period)
                text = _format_deep(asset_display, tf, result, seg,
                                    service.balance, n)
                rows = [[("🔁 Analizar de nuevo", "analyze")],
                        [("📊 Otro activo", "back:market"), ("🏠 Menú", "back:main")]]
                # Dibujamos el gráfico (si hay velas) y enviamos TODO junto:
                # gráfico + análisis en un SOLO mensaje (foto con pie de foto).
                path = None
                chart_df = result.get("chart")
                if chart_df is not None and len(chart_df) >= 5:
                    try:
                        from bot.chart import draw_candles
                        path = os.path.join(ROOT, "charts_tmp.png")
                        draw_candles(chart_df, asset_display, tf, path,
                                     direccion=result.get("direccion", ""),
                                     levels=result.get("levels"))
                    except Exception:
                        path = None
                await _send_signal(query, text, rows, path)
                return
            await _safe_edit(query, text, rows)
            return

        text, rows = menu.handle_callback(uid, query.data)
        await _safe_edit(query, text, rows)

    async def _send_signal(query, text, rows, path):
        """
        Envía la señal UNIENDO gráfico + análisis en un solo mensaje (foto con el
        texto de pie de foto). Con reintentos robustos:
          1) foto + pie con formato Markdown,
          2) si el formato falla -> foto + pie en texto plano,
          3) si el pie es muy largo (>1024) o no hay gráfico -> foto aparte + el
             texto como mensaje editado (para no perder la lectura).
        Al enviar el mensaje unido, borra el "🧘 Leyendo…" para no dejarlo colgado.
        """
        from telegram.error import BadRequest
        kb = _keyboard(rows)

        async def _foto(caption, markdown):
            with open(path, "rb") as fimg:
                await query.message.reply_photo(
                    photo=fimg, caption=caption, reply_markup=kb,
                    parse_mode="Markdown" if markdown else None)

        if path:
            for caption, md in ((text, True),
                                (text.replace("*", "").replace("`", "")
                                     .replace("_", ""), False)):
                try:
                    await _foto(caption, md)
                    try:
                        await query.message.delete()   # quita el "Leyendo…"
                    except Exception:
                        pass
                    return
                except BadRequest:
                    continue        # formato roto o pie muy largo -> siguiente intento
            # No se pudo unir (p.ej. pie > 1024): foto aparte + texto por separado.
            try:
                await _foto("📈", False)
            except Exception:
                pass
        await _safe_edit(query, text, rows)

    async def _safe_edit(query, text, rows):
        """
        Edita el mensaje con formato Markdown. Si Telegram rechaza el formato
        (un carácter especial en un nombre/razón rompe el Markdown), NO perdemos
        la información: reintentamos SIN formato, y si aún falla, la enviamos como
        mensaje nuevo. Así la lectura SIEMPRE llega al usuario (Regla 3: robustez).
        """
        from telegram.error import BadRequest
        try:
            await query.edit_message_text(text, reply_markup=_keyboard(rows),
                                          parse_mode="Markdown")
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
        # Reintento en texto plano (quitamos los marcadores * _ ` de Markdown).
        plano = text.replace("*", "").replace("`", "").replace("_", "")
        try:
            await query.edit_message_text(plano, reply_markup=_keyboard(rows))
        except BadRequest:
            # El mensaje original no se puede editar (p.ej. era una foto):
            # enviamos la lectura como mensaje nuevo para no perderla.
            try:
                await query.message.reply_text(plano, reply_markup=_keyboard(rows))
            except Exception:
                pass

    async def _post_init(app):
        if service:
            await service.start()      # arranca la conexión a PO en segundo plano
            print("🔌 Conectando a Pocket Option (precios reales)...")
        if collector:
            asyncio.create_task(collector.run())
            print("📚 Colector 24/7 aprendiendo en segundo plano...")

    app = Application.builder().token(token).post_init(_post_init).build()
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CallbackQueryHandler(on_button))

    modo = "PRECIOS REALES" if service else "SIMULADO (sin ssid.txt)"
    print(f"🤖 Bot de SEÑALES en marcha [{modo}]. Abre tu bot y pulsa /start.")
    print("   (Para apagarlo: pulsa Ctrl + C)")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        # Apagado LIMPIO al pulsar Ctrl + C (sin traceback que asuste).
        pass
    finally:
        print("\n🛑 Bot detenido. ¡Hasta la próxima!")


if __name__ == "__main__":
    run()
