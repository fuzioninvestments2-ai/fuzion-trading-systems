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
import logging
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

# El historial NO se carga por Telegram (es lento). Se descarga en bloque, aparte.
_AVISO_HISTORIAL = (
    "📥 *El historial no se carga por aquí* (es lento).\n\n"
    "Descárgalo en bloque (rápido) con el bot APAGADO:\n"
    "1) Cierra la ventana del bot.\n"
    "2) Doble clic en *DESCARGAR_HISTORIAL* (en la carpeta del proyecto).\n"
    "3) Vuelve a abrir *INICIAR_BOT*.\n\n"
    "_Baja OTC (BinaryOptionsToolsV2) y FX real (yfinance) a la base de datos._")


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


def _fusionar_sistema(result, res):
    """
    FUSIÓN: mete el veredicto del SISTEMA del trader (10 indicadores, 7/12,
    EMA200-1H) dentro del `result` de la tarjeta rica. Así la DECISIÓN la toma su
    sistema exacto y la PRESENTACIÓN rica se mantiene (chart, VWAP, panel, hora de
    entrada, Pago, Mejores). Sobrescribe veredicto/dirección/fuerza/coincidencias y
    la dirección de cada tiempo del panel (conserva conf%/velas de la lectura fina).
    """
    d1h = res.get("direccion_1h", "HOLD")
    op = res.get("veredicto") == "OPERAR"
    # PROTECCIÓN MANDA: si el motor rico detecta manipulación o VACÍO de mercado
    # (feed no fiable), NO OPERAR aunque el sistema del trader diga que sí. La
    # protección nunca se salta (disciplina, no forzar entradas sobre datos raros).
    if result.get("manipulacion") or result.get("vacio"):
        op = False
    result["veredicto"] = "✅ OPERAR" if op else "🚫 NO OPERAR"
    result["direccion"] = {"CALL": "⬆️ UP (CALL)", "PUT": "⬇️ DOWN (PUT)"}.get(
        d1h, "⏸️ sin dirección clara")
    result["fuerza"] = res.get("peso_favor", 0) / 100.0
    # Alineación SOBRE LAS 12 temporalidades del trader (su regla es 7 de 12). Se
    # muestra el denominador 12 — no el nº de tiempos con datos — para que se vea
    # cuántos FALTAN por confirmar (antes salía "7/7" y parecía perfecto cuando en
    # realidad 5 tiempos no tenían datos).
    alin = res.get("alineados", 0)
    presentes = res.get("total_tf", 0)
    result["coinciden"] = f"{alin}/12"
    result["sistema_presentes"] = presentes
    result["sistema_motivo"] = res.get("motivo", "")
    result["_es_sistema"] = True                     # la tarjeta oculta lo del motor viejo
    # Si la protección (vacío/manipulación) tumbó una señal que el sistema aprobaba,
    # se dice explícitamente (así el NO OPERAR con dirección CALL tiene su porqué).
    if res.get("veredicto") == "OPERAR" and not op:
        result["sistema_motivo"] = ("Sistema alineado, pero la protección bloquea: "
                                    + ", ".join(result.get("manipulacion")
                                                or result.get("vacio") or ["datos raros"]))
    dpt = res.get("dir_por_tf", {})
    for tf_s, info in result.get("por_tiempo", {}).items():
        d = dpt.get(tf_s)
        if d in ("CALL", "PUT", "HOLD"):
            info["dir"] = "NEUTRAL" if d == "HOLD" else d


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

    celdas = []
    for tfs, v in sorted(por.items()):
        # El trader OPERA de 5s a 30m: solo esos se MUESTRAN en el panel. Los
        # tiempos mayores (1h/2h/4h/1D) SÍ se analizan por dentro (dan el sesgo/
        # tendencia mayor) pero NO se listan aquí para no ensuciar la lectura.
        if tfs >= 3600:
            continue
        # En COMPACTO (pie de foto ≤1024) ocultamos los tiempos aún SIN datos:
        # con la escalera 5s→1d hay hasta 16 filas y los largos tardan en
        # llenarse; mostrarlos vacíos desborda el mensaje y no aporta lectura.
        if compact and v["velas"] < 6:
            continue
        flecha = emo.get(v["dir"], "⏸️")
        if v["velas"] < 6:
            estado = "· _(pocos)_"
        elif v["dir"] == "NEUTRAL":
            estado = "▫️ Neu"
        else:
            estado = f"{_dot(v['conf'])} {v['conf']:.0%}"
        celdas.append(f"`{_tf_label(tfs):>4}` {flecha} {estado}")
    # TRES COLUMNAS: la escalera tiene hasta 16 tiempos; en una columna la tarjeta
    # queda larguísima. De a tres queda ~1/3 de alto (más ancho, se lee de un
    # vistazo, mejor alineado).
    filas = []
    for i in range(0, len(celdas), 3):
        filas.append("  ".join(celdas[i:i + 3]))
    desglose = ("\n".join(filas) if filas else
                "  (aún sin datos de este activo — dale unos segundos o descarga "
                "su historial)")

    if seg is not None:
        # HORA EXACTA de entrada = apertura de la próxima vela, en el RELOJ LOCAL del
        # usuario (datetime.now() + segundos que faltan). Se usa el reloj del equipo
        # a propósito: es la hora que el trader ve en su pantalla. `seg` viene
        # alineado al borde de la vela (hora de mercado de PO), así el conteo es
        # exacto aunque la hora absoluta dependa del reloj local.
        momento = datetime.now() + timedelta(seconds=int(seg))
        hora_entrada = momento.strftime("%H:%M:%S")
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

    # ALERTAS. Con TU sistema (la fórmula) se muestran SOLO las de protección real
    # (manipulación, vacío de feed) y la de nivel S/R. Las alertas DIRECCIONALES del
    # motor viejo (contra tendencia, indecisión, consenso extremo, doji) se BORRAN:
    # contradecían a la fórmula (que ya decide dirección con tiempos + movimiento) y
    # solo confundían.
    _sist = result.get("_es_sistema")
    manip = result.get("manipulacion")
    alerta = (f"\n🛡️ *ALERTA:* mercado raro ({', '.join(manip)}) → mejor NO operar"
              if manip else "")
    if result.get("vacio"):
        alerta += ("\n🕳️ *VACÍO DE MERCADO:* " + ", ".join(result["vacio"])
                   + " → feed no fiable, NO operes")
    if not _sist:
        if result.get("inestable"):
            alerta += "\n🔄 *INDECISIÓN:* la señal cambió de dirección → espera"
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

    # LECTURA / MOTIVO. Cuando manda TU sistema, el motivo es el del sistema (la
    # razón real del veredicto: alineación, ley EMA200-1H o filtro), no la lectura
    # del motor viejo — así el NO OPERAR SIEMPRE dice por qué, sin contradicciones.
    es_sistema = result.get("_es_sistema")
    if es_sistema:
        motivo_sis = result.get("sistema_motivo", "")
        expl = f"\n🧭 *Motivo:* _{motivo_sis}_" if motivo_sis else ""
    else:
        explicacion = result.get("explicacion", "")
        expl = f"\n🧭 *Lectura:* _{explicacion}_" if explicacion else ""

    # Alineación FRACTAL del motor viejo: se OCULTA con el sistema (contradecía la
    # alineación del trader, p.ej. "fractal 4/9" vs "sistema 7/12"). Solo se muestra
    # cuando no manda el sistema.
    frac = result.get("alineacion_fractal")
    if frac is not None and not es_sistema:
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

    # Patrones de vela (la FORMA de la vela): confirmación o indecisión. Con TU
    # sistema se OCULTA el patrón GLOBAL del motor viejo (uno solo, de un tiempo
    # suelto): contradecía la lectura (p.ej. "Marubozu bajista" junto a un CALL).
    # Los patrones se leen POR temporalidad dentro del consenso de indicadores.
    pats = result.get("patrones")
    patrones = (f"\n🕯️ *Patrones:* {', '.join(pats)}"
                if (pats and not es_sistema) else "")

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
        if not es_sistema and result.get("explicacion"):
            # Solo las 2 primeras frases (incluye el aviso de tendencia si lo hay).
            frases = result["explicacion"].split(". ")
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

    # Encabezado HONESTO: si el activo aún no tiene temporalidades con datos
    # (recién cambiado, sin historial), no decimos "datos en vivo" — avisamos que
    # está cargando, para no confundir con el gráfico de OTRO activo de arriba.
    cabecera = ("_(datos en vivo)_ ✅" if por
                else "_(cargando datos de este activo…)_ ⏳")
    # Con TU sistema: aviso de cuántas de las 12 temporalidades faltan por datos
    # (los tiempos largos y el sub-minuto tardan en llenarse). Así se entiende un
    # veredicto con pocos tiempos confirmados.
    faltan_txt = ""
    if es_sistema:
        pres = result.get("sistema_presentes", 0)
        if pres < 12:
            faltan_txt = f" _· faltan {12 - pres} tiempos por datos_"
    return (f"📈 *{asset_display}*   ⏱️ *{tf}*   {cabecera}\n"
            f"{alerta}\n"
            f"\n*{veredicto}*\n"
            f"Dirección: {direccion}{modo}\n"
            f"🎯 Alineación: *{fuerza:.0%}*  ({coinciden}){faltan_txt}{fractal_txt}{expl}{patrones}{vwap_txt}{niveles_txt}\n\n"
            f"🔎 *Panel de tiempos:*\n{desglose}\n"
            f"{timing}{pago}{bal}{aprendido}{cobertura}\n\n"
            f"⚠️ _No es recomendación; ningún bot acierta siempre. Demo._")


def run(profile_name="OTC"):
    """
    Arranca UN bot separado según su perfil (OTC o REAL). Dos bots distintos:
      - Token PROPIO por bot: TELEGRAM_BOT_TOKEN_OTC / TELEGRAM_BOT_TOKEN_REAL.
        (Para compatibilidad, el OTC acepta también el viejo TELEGRAM_BOT_TOKEN.)
      - Historial PROPIO por bot (profile.db_path): sin cruces entre mercados.
    Así el OTC y el real corren aislados, cada uno su Telegram y su base de datos.
    """
    from bot.profiles import get_profile
    profile = get_profile(profile_name)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    # Token propio del bot; el OTC hace fallback al nombre viejo por compatibilidad.
    token = os.getenv(f"TELEGRAM_BOT_TOKEN_{profile.nombre}", "")
    if not token and profile.nombre == "OTC":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(
            f"Falta TELEGRAM_BOT_TOKEN_{profile.nombre} en tu .env "
            f"(crea el bot '{profile.titulo}' con @BotFather y pega su token).")

    from telegram import Update
    from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                              ContextTypes)
    from telegram.error import BadRequest

    # Mercados por bot: el real solo muestra monedas reales; el OTC, los OTC.
    if profile.nombre == "REAL":
        mercados = ["real"]
    else:
        mercados = ["otc", "crypto", "stocks", "commodities", "indices"]
    menu = SignalMenu(mercados)

    # SSID PROPIO de este bot (su cuenta de PO), para no mezclar con el otro.
    ssid = _load_ssid(profile.nombre)
    service = None
    collector = None
    if ssid:
        from bot.pocket_service import PocketService
        # BD PROPIA del bot (historial separado, sin cruces OTC<->real).
        service = PocketService(ssid, demo=True, db_path=profile.db_path)
        # Colector 24/7: usa una SEGUNDA conexión con el mismo SSID. Pocket Option
        # a veces no permite dos conexiones a la vez y provoca desconexiones. Por
        # eso viene DESACTIVADO por defecto (más estable con una sola conexión).
        # Para activarlo: crea en el .env la línea  ENABLE_COLLECTOR=1
        if os.getenv("ENABLE_COLLECTOR", "").strip() in ("1", "true", "yes"):
            from bot.collector import Collector
            collector = Collector(ssid, service.repo, demo=True)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        modo = "PRECIOS REALES ✅" if service else "datos simulados (sin SSID)"
        text, rows = menu.entrada(update.effective_user.id)
        await update.message.reply_text(
            f"🤖 *{profile.titulo}*\n{text}\n_Modo: {modo}_",
            reply_markup=_keyboard(rows), parse_mode="Markdown")

    async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/historial — el historial por Telegram es lento; se usa la descarga batch."""
        await update.message.reply_text(_AVISO_HISTORIAL, parse_mode="Markdown")

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

        # FUSIÓN: si el perfil usa el SISTEMA del trader, el VEREDICTO lo decide su
        # sistema exacto (10 indicadores, 7/12, EMA200-1H, filtros) y la tarjeta
        # RICA (chart, VWAP, panel, hora de entrada, Pago, Mejores) se mantiene.
        sistema = None
        if getattr(profile, "usa_sistema", False):
            from bot import otc_system, real_system
            sistema = real_system if profile.nombre == "REAL" else otc_system

        # registrar=(sin sistema): el motor viejo guarda su señal solo si NO hay
        # sistema; con sistema, se registra la señal del SISTEMA (aprendizaje correcto).
        result, seg, n = await service.analyze(code, period,
                                               registrar=(sistema is None))
        if sistema is not None:
            payout = service._payouts.get(code)
            hora_est = None
            if getattr(sistema, "NOTICIAS_DURANTE", None) is not None:
                from datetime import datetime, timezone
                hora_est = (datetime.now(timezone.utc).hour - 5) % 24
            try:
                res_sis = service.veredicto_sistema(code, sistema, payout=payout,
                                                    hora_est=hora_est,
                                                    tf_operar=period)
                _fusionar_sistema(result, res_sis)
                # PANEL = TU sistema: 12 temporalidades exactas con el consenso de
                # los 10 indicadores (no el motor viejo, que metía tiempos ajenos
                # como 4m y direcciones sueltas -> "desorden"). Cada tiempo muestra
                # su dirección de consenso y su fuerza (indicadores que coinciden).
                try:
                    panel = service.panel_sistema(code, sistema)
                    if panel:
                        result["por_tiempo"] = panel
                except Exception:
                    logging.exception("No se pudo armar el panel del sistema")
                if res_sis.get("veredicto") == "OPERAR":
                    service._registrar_senal_sistema(code, period, res_sis)
                # COHERENCIA GRÁFICO=LECTURA: dibuja las MISMAS velas que el sistema
                # calificó para el tiempo operado (si están frescas). Así el gráfico
                # no discrepa de la dirección/panel (el bug "el gráfico no coincide"
                # venía de dibujar ticks en vivo mientras la señal leía el historial).
                fop = service.frame_sistema_operativo(code, sistema, period)
                if fop is not None and len(fop) >= 5:
                    result["chart"] = fop.tail(45).reset_index(drop=True)
                    try:
                        from bot.levels import detect_levels
                        lv = detect_levels(result["chart"])
                        if lv.get("soportes") or lv.get("resistencias"):
                            result["levels"] = lv
                    except Exception:
                        pass
            except Exception:
                logging.exception("No se pudo fusionar el sistema del trader")

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
                # Nombre de archivo ÚNICO por activo+tiempo: así NUNCA se envía el
                # gráfico de otro activo (antes, un archivo compartido 'charts_tmp'
                # podía dejar pegado el gráfico anterior a la tarjeta nueva).
                safe = "".join(c if c.isalnum() else "_" for c in f"{code}_{tf}")
                path = os.path.join(ROOT, f"chart_{safe}.png")
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

        # (Botón viejo de historial en mensajes previos): redirige a la descarga
        # batch. El historial por Telegram es LENTO y se retiró.
        if query.data.startswith("hist:"):
            await query.message.reply_text(_AVISO_HISTORIAL, parse_mode="Markdown")
            return

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
        chat = query.message.chat
        # OPCIÓN A: el GRÁFICO va primero (mensaje propio, arriba) y la tarjeta
        # COMPLETA debajo. Así el gráfico no llega desfasado ni se recorta por el
        # límite de 1024 del pie de foto. `caption` (versión compacta) ya no se usa.
        try:
            await query.message.delete()          # quita el "🧘 Leyendo…"
        except Exception:
            pass
        if path:                                   # 1) gráfico primero
            try:
                with open(path, "rb") as fimg:
                    await chat.send_photo(photo=fimg)
            except Exception:
                pass
        # 2) Tarjeta COMPLETA debajo, con respaldo en texto plano si el Markdown falla.
        try:
            await chat.send_message(text, reply_markup=kb, parse_mode="Markdown")
        except BadRequest:
            plano = text.replace("*", "").replace("`", "").replace("_", "")
            try:
                await chat.send_message(plano, reply_markup=kb)
            except Exception:
                pass

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
    import sys
    # Perfil por argumento: 'OTC' (default) o 'REAL'. Cada uno es un bot aparte.
    perfil = sys.argv[1] if len(sys.argv) > 1 else "OTC"
    run(perfil)
