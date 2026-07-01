"""
bot/telegram_controller.py
==========================
Lógica de COMANDOS del bot de Telegram, SEPARADA de la red.

EL PORQUÉ de separar la lógica del envío por Telegram: así podemos PROBAR los
comandos (start/stop/estado...) sin depender de internet ni de un token. La capa
de red (telegram_bot.py) solo traduce mensajes -> estas funciones.

SRP: esta clase decide QUÉ responder a cada comando y mantiene el estado del bot
(encendido/apagado, preset, última señal). No sabe de Telegram ni de Pocket
Option directamente; el arranque/parada reales se inyectan (start_fn/stop_fn).
"""

from bot.config import get_preset


class BotController:
    """
    Controlador de comandos.

    Parámetros (inyección de dependencias, opcionales):
      start_fn : callable() -> None  — arranca el motor real (o simulado).
      stop_fn  : callable() -> None  — detiene el motor.
      status_fn: callable() -> dict  — devuelve estadísticas actuales del motor.
    Si no se inyectan, el controlador solo gestiona el estado (modo esqueleto).
    """

    def __init__(self, start_fn=None, stop_fn=None, status_fn=None,
                 signal_fn=None, preset="moderado"):
        self._start_fn = start_fn
        self._stop_fn = stop_fn
        self._status_fn = status_fn
        self._signal_fn = signal_fn         # devuelve la última señal del motor
        self.running = False
        self.preset = preset
        self.cfg = get_preset(preset)
        self.last_signal = None

    # --- Comandos individuales (devuelven texto para el usuario) ---

    def cmd_start(self):
        if self.running:
            return "⚠️ El bot ya está en marcha."
        self.running = True
        if self._start_fn:
            self._start_fn()
        return (f"✅ Bot ARRANCADO en modo DEMO.\n"
                f"Preset: {self.preset} | activo: {self.cfg.current_asset}\n"
                f"(No se envían órdenes reales sin tu confirmación explícita.)")

    def cmd_stop(self):
        if not self.running:
            return "⚠️ El bot ya está detenido."
        self.running = False
        if self._stop_fn:
            self._stop_fn()
        return "🛑 Bot DETENIDO."

    def cmd_status(self):
        estado = "🟢 En marcha" if self.running else "🔴 Detenido"
        stats = self._status_fn() if self._status_fn else {}
        linea_stats = ""
        if stats:
            linea_stats = (f"\nOperaciones: {stats.get('total_trades', 0)} | "
                           f"win rate: {stats.get('win_rate', 0):.0%} | "
                           f"profit: ${stats.get('total_profit', 0)}")
        return (f"📊 Estado: {estado}\nPreset: {self.preset}"
                f"{linea_stats}")

    def cmd_signal(self):
        # Si hay un motor conectado, preguntamos su última señal; si no, la local.
        señal = self._signal_fn() if self._signal_fn else self.last_signal
        if señal is None:
            return "Aún no hay señales."
        return f"Última señal: {señal}"

    def cmd_preset(self, name):
        try:
            self.cfg = get_preset(name)
            self.preset = name.lower()
            return f"⚙️ Preset cambiado a: {self.preset}"
        except ValueError as e:
            return f"❌ {e}"

    def cmd_help(self):
        return ("🤖 Comandos disponibles:\n"
                "/start — arrancar el bot (demo)\n"
                "/stop — detener el bot\n"
                "/estado — ver estado y estadísticas\n"
                "/senal — última señal\n"
                "/preset <conservador|moderado|agresivo>\n"
                "/help — esta ayuda")

    # --- Enrutador: recibe el texto del mensaje y dispara el comando ---

    def handle(self, text):
        """
        Interpreta un mensaje de texto tipo '/comando args' y devuelve la
        respuesta. Robusto ante espacios y mayúsculas.
        """
        if not text:
            return self.cmd_help()
        parts = text.strip().split()
        cmd = parts[0].lower().lstrip("/")
        args = parts[1:]

        if cmd == "start":
            return self.cmd_start()
        if cmd == "stop":
            return self.cmd_stop()
        if cmd in ("estado", "status"):
            return self.cmd_status()
        if cmd in ("senal", "señal", "signal"):
            return self.cmd_signal()
        if cmd == "preset":
            if not args:
                return "Uso: /preset <conservador|moderado|agresivo>"
            return self.cmd_preset(args[0])
        if cmd in ("help", "ayuda", "start_help"):
            return self.cmd_help()
        return "❓ Comando no reconocido. Escribe /help."
