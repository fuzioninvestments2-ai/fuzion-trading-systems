"""
telegram/signal_formatter.py (fuzion_fx)
========================================
Formateo de las tarjetas de Telegram: SEÑAL y RESULTADO. Una sola pieza que arma
el texto (Regla 1: el bot no duplica formato). Emojis Unicode nativos (no
imagenes), texto en español (LATAM), hora 24h HH:MM, precios FX a 5 decimales.

DATOS POR PAR: el acierto reciente y la estrella salen del historial POR PAR
(el bot los provee via `par_stats(par)`), no por setup. Cada divisa lleva su
propio win-rate: si EURUSD gana y NZDUSD pierde, no se mezclan.

Recibe diccionarios con los datos ya calculados (el bot los provee); esta clase
solo FORMATEA y aplica las reglas de visualizacion (estrella, "sin muestra",
color por direccion, mercado). Es pura y se testea sin red.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class SignalCardFormatter:
    # Direccion -> etiqueta con color (verde CALL / rojo PUT) e instruccion.
    ARROWS = {
        "CALL": "🟩 CALL (poner ARRIBA)",
        "PUT": "🟥 PUT (poner ABAJO)",
    }
    ICONS_RESULT = {"win": "✅ WIN", "loss": "❌ LOSS", "tie": "➖ EMPATE"}

    # Reglas de la estrella y de la muestra (POR PAR).
    STAR_MIN_WIN_PCT = 80.0
    STAR_MIN_MEASURED = 10
    MIN_MEASURED_SHOW = 5          # por debajo: "sin muestra aún"

    # ------------------------------------------------------------- helpers
    @staticmethod
    def session_from_utc_hour(hour: int) -> str:
        """Mercado dominante por hora UTC: Europe / America / Asia.

        Fallback: solo se usa si el bot no manda `mercado` explicito.
        """
        h = int(hour) % 24
        if 7 <= h < 13:
            return "Europe"
        if 13 <= h < 21:
            return "America"
        return "Asia"

    def _star(self, acierto_pct: Optional[float], n_muestras: int) -> bool:
        """Estrella SOLO con acierto >= 80% y >= 10 señales medidas (por par)."""
        return (acierto_pct is not None
                and acierto_pct >= self.STAR_MIN_WIN_PCT
                and n_muestras >= self.STAR_MIN_MEASURED)

    def _acierto(self, acierto_pct: Optional[float], n_muestras: int) -> str:
        """Linea de acierto reciente (por par); 'sin muestra' si N < 5."""
        if acierto_pct is None or n_muestras < self.MIN_MEASURED_SHOW:
            return "sin muestra aún (recién aprende)"
        return f"{acierto_pct:.0f}%  ({n_muestras} señales medidas)"

    # ------------------------------------------------------------- señal
    def format_signal(self, d: Dict[str, Any]) -> str:
        """
        Tarjeta de SEÑAL. `d` espera (POR PAR):
          par, direccion (CALL/PUT), hora_entrada, hora_vencimiento, mercado
          (Asia/Europe/America), payout, confirmaciones (lista de indicadores),
          acierto_pct (float|None), n_muestras (int), atr (float, en pips).
        Opcionales de presentacion:
          bot_name (de bots.yaml), card_label (ej. "1M"), tz_offset (int).
        """
        acierto_pct = d.get("acierto_pct")
        n_muestras = int(d.get("n_muestras", 0))

        direccion = str(d["direccion"]).upper()
        arrow = self.ARROWS.get(direccion, direccion)
        estrella = " ⭐" if self._star(acierto_pct, n_muestras) else ""
        indic = ", ".join(d.get("confirmaciones", []))
        acierto = self._acierto(acierto_pct, n_muestras)
        # Mercado explicito del bot; si no viene, se deriva de la hora UTC.
        mercado = d.get("mercado") or self.session_from_utc_hour(d.get("utc_hour", 0))
        off = int(d.get("tz_offset", 0))
        pair_txt = str(d["par"]).replace("/", "")
        bot_name = d.get("bot_name", "FUZION FX")
        card_label = d.get("card_label", "")
        label_txt = f"  ({card_label})" if card_label else ""

        return (
            f"🤖 *{bot_name}*{estrella}\n"
            f"🌐 Zona Horaria: UTC{off:+d}:00\n"
            f"📊 DIVISA: *{pair_txt}*\n"
            f"{arrow}\n"
            f"⏰ HORA DE ENTRADA: *{d['hora_entrada']}*\n"
            f"⌛ VENCE: {d['hora_vencimiento']}{label_txt}\n"
            f"🌍 Mercado: {mercado}\n"
            f"💰 Pago del activo: {int(d.get('payout', 85))}%\n"
            f"🎯 Confirmaciones: {len(d.get('confirmaciones', []))} ({indic})\n"
            f"📈 Acierto reciente: {acierto}\n"
            f"📊 Volatilidad (ATR): {d.get('atr', 0.0)} pips\n"
            f"⚠️ Demo · señal educativa · el acierto no está garantizado")

    # ------------------------------------------------------------- resultado
    def format_result(self, d: Dict[str, Any]) -> str:
        """
        Tarjeta de RESULTADO. `d` espera:
          par, direccion, resultado (win/loss/tie), entrada (float),
          cierre (float), modo_recuperacion (bool).
        Opcionales de presentacion: bot_name, card_label.
        La nota de recuperacion se agrega SOLO si modo_recuperacion es True.
        """
        icono = self.ICONS_RESULT.get(d["resultado"], d["resultado"])
        bot_name = d.get("bot_name", "FUZION FX")
        card_label = d.get("card_label", "")
        label_txt = f" ({card_label})" if card_label else ""

        txt = (
            f"🏁 *{bot_name}* · *{d['par']}*{label_txt}\n"
            f"Resultado: *{icono}*\n"
            f"Direccion: {d['direccion']}\n"
            f"Entrada: {float(d['entrada']):.5f}  →  Cierre: {float(d['cierre']):.5f}\n"
            f"⚠️ Demo · resultado educativo · el acierto no esta garantizado")
        if d.get("modo_recuperacion"):
            txt += ("\n🔁 Correccion: el par entra en RECUPERACION — la proxima "
                    "senal sera mas estricta y de MENOR tamano (no se dobla).")
        return txt
