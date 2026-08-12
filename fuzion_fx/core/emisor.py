"""
core/emisor.py (fuzion_fx)
==========================
EMISOR MANUAL de senales: el trader (asesor) revisa el escaner, da el VISTO BUENO
y envia una senal personalizada a SU Telegram y a los AFILIADOS suscriptos a esa
temporalidad. Es el modo manual (complementa el automatico de los bots).

HONESTIDAD: la tarjeta lleva el sello educativo; no promete acierto. El afiliado
paga acceso a la asesoria, no ganancias garantizadas.

build_card_manual es PURO (testeable). enviar_senal_manual usa red (Telegram) y
la config; se prueba la construccion de la tarjeta, no el envio.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional

TF_LABEL = {60: "1 min - M1", 120: "2 min - M2", 180: "3 min - M3", 300: "5 min - M5"}
TF_BOT = {60: "f1_m1", 120: "f2_m2", 180: "f3_m3", 300: "f4_m5"}


def build_card_manual(pair: str, tf: int, direccion: str, nota: str = "",
                      payout: Optional[float] = None,
                      now: Optional[float] = None, es_otc: bool = False) -> str:
    """Tarjeta de senal MANUAL (Markdown) coherente con la del bot. Entrada = el
    proximo borde de vela; vence = entrada + tf. es_otc muestra el sufijo OTC para
    que el afiliado opere el MISMO activo (igual que las tarjetas automaticas)."""
    now = time.time() if now is None else now
    tf = int(tf)
    seg = tf
    borde = int(now) - (int(now) % seg) + seg
    entrada = datetime.fromtimestamp(borde).strftime("%H:%M")
    vence = datetime.fromtimestamp(borde + seg).strftime("%H:%M")
    d = str(direccion).upper()
    flecha = "🟩 CALL (poner ARRIBA)" if d == "CALL" else "🟥 PUT (poner ABAJO)"
    pago = f"\n💰 Pago del activo: {int(payout)}%" if payout is not None else ""
    extra = f"\n📝 {nota}" if nota else ""
    par_txt = f"{pair} OTC" if es_otc else pair
    return (f"🤖 *FUZION FX — Señal (asesoría)*\n"
            f"📊 *{par_txt}*\n{flecha}\n"
            f"⏰ HORA DE ENTRADA: *{entrada}*\n"
            f"⌛ VENCE: {vence}  ({TF_LABEL.get(tf, str(tf) + 's')})"
            f"{pago}{extra}\n"
            f"⚠️ Demo · señal educativa · el acierto no está garantizado")


def enviar_senal_manual(pair: str, tf: int, direccion: str, nota: str = "",
                        payout: Optional[float] = None) -> Dict[str, Any]:
    """
    Manda la senal manual al Telegram del dueno y a los afiliados activos de esa
    temporalidad. Devuelve {ok, enviados, card}. ok=False si falta token/canal
    (no revienta). El envio real es best-effort (reintentos del notifier).
    """
    # Card por defecto (sin OTC) para que el except SIEMPRE tenga algo que devolver
    # aunque falle load_config; dentro del try se reconstruye con el mercado real.
    card = build_card_manual(pair, tf, direccion, nota, payout)
    try:
        from core.config import load_config
        from telegram.notifier import TelegramNotifier
        from core import afiliados
        cfg = load_config()
        es_otc = str(cfg.get("market", "otc")).lower() == "otc"
        card = build_card_manual(pair, tf, direccion, nota, payout, es_otc=es_otc)
        tg = cfg.get("telegram", {})
        token, canal = tg.get("bot_token"), tg.get("channel_id")
        if not (token and canal):
            return {"ok": False, "enviados": 0, "card": card,
                    "error": "falta telegram.bot_token/channel_id en config"}
        n = TelegramNotifier(token, canal)
        enviados = 1 if n.send_text(card) else 0
        for a in afiliados.destinatarios_para(TF_BOT.get(int(tf), "f4_m5")):
            try:
                if n.enviar_a(a["chat_id"], card):
                    enviados += 1
            except Exception:
                pass
        return {"ok": True, "enviados": enviados, "card": card}
    except Exception as exc:
        return {"ok": False, "enviados": 0, "card": card, "error": str(exc)}
