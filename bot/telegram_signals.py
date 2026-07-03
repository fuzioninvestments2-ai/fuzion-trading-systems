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
from datetime import datetime, timedelta

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


def _format_deep(asset_display, tf, result, seg, balance, n_ticks, compact=False):
    """
    Formatea el resultado del análisis profundo multi-temporalidad.

    compact=True: versión más corta para el PIE DE FOTO de Telegram (límite 1024
    caracteres), para poder enviar gráfico + análisis en UN SOLO mensaje. Recorta
    solo la parte educativa larga; mantiene lo esencial y el panel completo.
    """
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
        # HORA EXACTA de entrada (reloj del usuario) = ahora + segundos hasta que
        # ABRE la próxima vela. Así sabes el momento justo, como los bots que dan
        # la hora de entrada (ej. 23:50:00), no solo "en Xs".
        hora_entrada = (datetime.now() + timedelta(seconds=seg)).strftime("%H:%M:%S")
        if seg <= 5:
            timing = f"\n⏱️ *¡ENTRA YA!* (nueva vela ~{hora_entrada})"
        else:
            timing = (f"\n⏱️ *Entra a las {hora_entrada}* "
                      f"_(al abrir la vela, en {seg}s)_")
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
    if result.get("consenso_extremo"):
        alerta += ("\n🔬 *CONSENSO EXTREMO:* casi TODOS los tiempos coinciden "
                   "(raro) → confírmalo antes de entrar")
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

    # Alineación FRACTAL: cuántos de TODOS los tiempos apuntan igual (0-100%).
    frac = result.get("alineacion_fractal")
    if frac is not None:
        fractal_txt = (f"\n🧬 *Alineación fractal:* {frac:.0%} "
                       f"_({result.get('fractal_txt', '')})_")
    else:
        fractal_txt = ""

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
                     + ("" if (m1 >= 400 or compact) else
                        " _(los tiempos largos se llenan con el tiempo)_"))
    else:
        cobertura = ""

    # MODO COMPACTO (para el pie de foto ≤1024): recortamos solo lo educativo
    # largo. Se conserva el PANEL completo (15s→30m), las alertas y el timing.
    if compact:
        if explicacion:
            # Solo las 2 primeras frases (incluye el aviso de tendencia si lo hay).
            frases = explicacion.split(". ")
            corta = ". ".join(frases[:2]).strip().rstrip(".")
            expl = f"\n🧭 *Lectura:* _{corta}._"
        bal = ""                                   # el balance se ve en el menú
        # De lo aprendido dejamos solo los "mejores indicadores" (línea corta).
        pt = result.get("pesos_top")
        if pt:
            det = ", ".join(f"{_NOM.get(n, n)} {hr:.0%}" for n, hr in pt)
            aprendido = f"\n🧠 Mejores: {det}"
        else:
            aprendido = ""

    return (f"📈 *{asset_display}*   ⏱️ *{tf}*   (REALES ✅)\n"
            f"{alerta}\n"
            f"\n*{veredicto}*\n"
            f"Dirección: {direccion}{modo}\n"
            f"🎯 Alineación: *{fuerza:.0%}*  ({coinciden}){fractal_txt}{expl}{patrones}{vwap_txt}{niveles_txt}\n\n"
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

    async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/historial [ACTIVO] — escanea el historial hacia ATRÁS (experimental)."""
        if service is None:
            await update.message.reply_text("Necesitas ssid.txt (precios reales).")
            return
        args = context.args or []
        arg0 = (args[0].lower() if args else "")

        # /historial todos  -> escanea M1 hacia atrás de TODA la watchlist.
        if arg0 in ("todos", "all", "todo"):
            assets = list(service._watchlist)
            await update.message.reply_text(
                f"📥 Escaneando historial de *{len(assets)}* activos hacia "
                f"atrás (M1)…\n_Esto tarda BASTANTE (varios minutos). Ve haciendo "
                f"otra cosa; te aviso al terminar._", parse_mode="Markdown")
            lineas = []
            for a in assets:
                try:
                    total = await service.scan_backwards(a, period=60,
                                                         max_days=365, paginas=15)
                    lineas.append(f"  {a}: *{total}*")
                except Exception:
                    lineas.append(f"  {a}: (error)")
            await update.message.reply_text(
                "✅ Historial M1 por activo:\n" + "\n".join(lineas),
                parse_mode="Markdown")
            return

        # Activo: el que pasen, o el último en foco, o EUR/USD OTC por defecto.
        code = (to_po_code(" ".join(args)) if args
                else (service._focus or "EURUSD_otc"))
        await update.message.reply_text(
            f"📥 Buscando historial ANTIGUO de *{code}* hacia atrás, en TODAS "
            f"las temporalidades…\n_Experimental: tomo lo que Pocket Option "
            f"tenga (sin inventar). Puede tardar 2-3 minutos._",
            parse_mode="Markdown")
        # Escaneamos cada temporalidad clave hacia atrás (M1, 3m, 5m, 15m, 30m).
        periodos = [(60, "1m"), (180, "3m"), (300, "5m"), (900, "15m"),
                    (1800, "30m")]
        try:
            lineas = []
            for p, etq in periodos:
                total = await service.scan_backwards(code, period=p,
                                                     max_days=365, paginas=25)
                lineas.append(f"  {etq}: *{total}* velas")
            await update.message.reply_text(
                f"✅ Historial de *{code}* (por temporalidad):\n"
                + "\n".join(lineas)
                + "\n\n_Si algún número no subió, PO no da más historial atrás "
                  "en ese tiempo; lo seguimos acumulando en vivo._",
                parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"No se pudo escanear: {e}")

    async def _leyendo(query, asset_display, tf):
        # Muestra "🧘 Leyendo…" de forma SEGURA. Si el mensaje es una FOTO (viene
        # de un análisis anterior), no se puede editar su texto -> lo ignoramos.
        try:
            await query.edit_message_text(
                f"🧘 Leyendo *{asset_display}* ({tf}) con atención…\n"
                f"_Concentrándome en el mercado unos segundos._",
                parse_mode="Markdown")
        except Exception:
            pass

    async def _do_analysis(query, asset_display, tf):
        """Hace y envía el análisis de un activo/tiempo (reutilizable)."""
        if service is None:
            text, rows = menu.analyze(query.from_user.id)
            await _safe_edit(query, text, rows)
            return
        await _leyendo(query, asset_display, tf)
        code = to_po_code(asset_display)
        period = _TF_SECONDS.get(tf, 60)
        if collector:
            collector.set_focus(code)
        result, seg, n = await service.analyze(code, period)
        text = _format_deep(asset_display, tf, result, seg, service.balance, n)
        caption = _format_deep(asset_display, tf, result, seg,
                               service.balance, n, compact=True)
        # El botón "Analizar de nuevo" LLEVA el activo y el tiempo en su dato, así
        # funciona SIEMPRE (incluso tras reiniciar el bot, sin memoria previa).
        rows = [[("🔁 Analizar de nuevo", f"re:{asset_display}:{tf}")],
                [("📊 Otro activo", "back:market"), ("🏠 Menú", "back:main")]]
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
        await _send_signal(query, caption, text, rows, path)

    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        uid = query.from_user.id

        # "Analizar de nuevo" que lleva el activo y el tiempo consigo (re:activo:tf).
        if query.data.startswith("re:"):
            try:
                _, asset_display, tf = query.data.split(":", 2)
            except ValueError:
                await query.answer("Vuelve a elegir con /start", show_alert=True)
                return
            await _do_analysis(query, asset_display, tf)
            return

        if query.data == "analyze":
            st = menu._st(uid)
            asset_display = st.get("asset")
            tf = st.get("timeframe")
            if not asset_display or not tf:
                await query.answer("Elige activo y tiempo primero (usa /start)",
                                   show_alert=True)
                return
            await _do_analysis(query, asset_display, tf)
            return

        text, rows = menu.handle_callback(uid, query.data)
        await _safe_edit(query, text, rows)

    async def _send_signal(query, caption, text, rows, path):
        """
        Envía la señal en UN SOLO mensaje: gráfico con el análisis (compacto) de
        pie de foto. `caption` es la versión compacta (≤1024); `text` es la
        completa (para el respaldo). Reintentos robustos:
          1) foto + pie compacto con formato Markdown,
          2) si el formato falla -> foto + pie compacto en texto plano,
          3) si aun así no cabe o no hay gráfico -> foto aparte + texto completo.
        Al enviar el mensaje unido, borra el "🧘 Leyendo…" para no dejarlo colgado.
        """
        from telegram.error import BadRequest
        kb = _keyboard(rows)

        async def _foto(cap, markdown):
            with open(path, "rb") as fimg:
                await query.message.reply_photo(
                    photo=fimg, caption=cap, reply_markup=kb,
                    parse_mode="Markdown" if markdown else None)

        if path:
            plano = caption.replace("*", "").replace("`", "").replace("_", "")
            for cap, md in ((caption, True), (plano, False)):
                try:
                    await _foto(cap, md)
                    try:
                        await query.message.delete()   # quita el "Leyendo…"
                    except Exception:
                        pass
                    return
                except BadRequest:
                    continue        # formato roto o pie muy largo -> siguiente intento
            # Respaldo: no se pudo unir -> foto aparte + texto COMPLETO por separado.
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
            print("📚 Colector integrado activo (misma conexión, aprendizaje 24/7).")
        if collector:                  # colector aparte (opcional, ENABLE_COLLECTOR)
            asyncio.create_task(collector.run())
            print("📚 Colector 24/7 (2ª conexión) aprendiendo en segundo plano...")

    async def _post_shutdown(app):
        # Apagado LIMPIO: cancela las tareas de fondo antes de cerrar el loop,
        # para no dejar "Task was destroyed" ni tracebacks al cerrar.
        if service:
            try:
                await service.stop()
            except Exception:
                pass

    async def _on_error(update, context):
        # Manejador GLOBAL de errores: evita que cualquier fallo suelte un
        # traceback enorme en pantalla. Solo deja un aviso corto y sigue.
        print(f"(aviso interno, el bot sigue funcionando: {context.error})")

    app = (Application.builder().token(token)
           .post_init(_post_init).post_shutdown(_post_shutdown).build())
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CommandHandler("historial", historial))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_error_handler(_on_error)

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
