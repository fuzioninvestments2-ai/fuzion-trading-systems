"""
telegram/signal_formatter.py (fuzion_fx)
========================================
Formateo de las tarjetas de Telegram: SEÑAL y RESULTADO. Una sola pieza que arma
el texto (Regla 1: el bot no duplica formato). Emojis Unicode nativos (no
imagenes), texto en español (LATAM), hora 24h HH:MM, precios FX a 5 decimales.

Recibe diccionarios con los datos ya calculados (el bot los provee); esta clase
solo FORMATEA y aplica las reglas de visualizacion (estrella, "sin muestra",
color por direccion, sesion). Es pura y se testea sin red.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class SignalCardFormatter:
    # Direccion -> etiqueta con color (verde CALL / rojo PUT) e instruccion.
    ARROWS = {
        "CALL": "🟩 CALL (poner ARRIBA)",
        "PUT": "🟥 PUT (poner ABAJO)",
    }
    ICONS_RESULT = {"win": "✅ WIN", "loss": "❌ LOSS", "tie": "➖ EMPATE"}

    # Reglas de la estrella y de la muestra.
    STAR_MIN_WIN_PCT = 80.0
    STAR_MIN_MEASURED = 10
    MIN_MEASURED_SHOW = 5          # por debajo: "sin muestra aún"

    # ------------------------------------------------------------- helpers
    @staticmethod
    def session_from_utc_hour(hour: int) -> str:
        """Mercado dominante por hora UTC: Europe / America / Asia."""
        h = int(hour) % 24
        if 7 <= h < 13:
            return "Europe"
        if 13 <= h < 21:
            return "America"
        return "Asia"

    def _star(self, win_pct: Optional[float], measured: int) -> bool:
        """Estrella SOLO con acierto >= 80% y >= 10 señales medidas."""
        return (win_pct is not None
                and win_pct >= self.STAR_MIN_WIN_PCT
                and measured >= self.STAR_MIN_MEASURED)

    def _acierto(self, win_pct: Optional[float], measured: int) -> str:
        """Linea de acierto reciente; 'sin muestra' si N < 5."""
        if win_pct is None or measured < self.MIN_MEASURED_SHOW:
            return "sin muestra aún (recién aprende)"
        return f"{win_pct:.0f}%  ({measured} señales medidas)"

    # ------------------------------------------------------------- señal
    def format_signal(self, d: Dict[str, Any]) -> str:
        """
        Tarjeta de SEÑAL. `d` espera:
          bot_name, pair, direction (CALL/PUT), card_label, entry_time,
          expiry_time, tz_offset (int), session|utc_hour, payout_pct,
          confirmations, indicators (list), win_pct (float|None), measured (int),
          atr_pips (float).
        """
        direccion = str(d["direction"]).upper()
        arrow = self.ARROWS.get(direccion, direccion)
        estrella = " ⭐" if self._star(d.get("win_pct"), int(d.get("measured", 0))) else ""
        indic = ", ".join(d.get("indicators", []))
        acierto = self._acierto(d.get("win_pct"), int(d.get("measured", 0)))
        sesion = d.get("session") or self.session_from_utc_hour(d.get("utc_hour", 0))
        off = int(d.get("tz_offset", 0))
        pair_txt = str(d["pair"]).replace("/", "")

        return (
            f"🤖 *{d['bot_name']}*{estrella}\n"
            f"🌐 Zona Horaria: UTC{off:+d}:00\n"
            f"📊 DIVISA: *{pair_txt}*\n"
            f"{arrow}\n"
            f"⏰ HORA DE ENTRADA: *{d['entry_time']}*\n"
            f"⌛ VENCE: {d['expiry_time']}  ({d['card_label']})\n"
            f"🌍 Mercado: {sesion}\n"
            f"💰 Pago del activo: {int(d.get('payout_pct', 85))}%\n"
            f"🎯 Confirmaciones: {int(d['confirmations'])} ({indic})\n"
            f"📈 Acierto reciente: {acierto}\n"
            f"📊 Volatilidad (ATR): {d.get('atr_pips', 0.0)} pips\n"
            f"⚠️ Demo · señal educativa · el acierto no está garantizado")

    # ------------------------------------------------------------- resultado
    def format_result(self, d: Dict[str, Any]) -> str:
        """
        Tarjeta de RESULTADO. `d` espera:
          bot_name, pair, card_label, result (win/loss/tie), direction,
          entry (float), exit (float). En LOSS se agrega la nota de recuperacion.
        """
        icono = self.ICONS_RESULT.get(d["result"], d["result"])
        txt = (
            f"🏁 *{d['bot_name']}* · *{d['pair']}* ({d['card_label']})\n"
            f"Resultado: *{icono}*\n"
            f"Direccion: {d['direction']}\n"
            f"Entrada: {float(d['entry']):.5f}  →  Cierre: {float(d['exit']):.5f}\n"
            f"⚠️ Demo · resultado educativo · el acierto no esta garantizado")
        if d["result"] == "loss":
            txt += ("\n🔁 Correccion: el par entra en RECUPERACION — la proxima "
                    "senal sera mas estricta y de MENOR tamano (no se dobla).")
        return txt
