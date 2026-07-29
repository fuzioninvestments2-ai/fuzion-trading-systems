"""
bot/robot_reversion.py
======================
LANZADOR EN VIVO del robot de reversión (FX real). Une todo:

  Pocket Option (velas M1 en vivo)  ->  VigilanteReversion (detecta el pico)
        ->  tarjeta  ->  Telegram (@FuZionFzbot).

Cómo funciona, en simple:
  - Lee tu sesión de `ssid_real.txt` (perfil REAL) y se conecta a Pocket Option (solo
    lectura, nunca opera).
  - El websocket escucha UN par a la vez, así que ROTA por la lista dejando ~75s a cada
    uno (lo justo para que cierre una vela de 1m). No es simultáneo: es un muestreo.
  - Cada vela M1 que cierra pasa por el vigilante; si hay reversión con ventaja, te
    manda la tarjeta a Telegram. Guarda las velas en `history_real.db` (historial que
    crece con lo que llega en vivo).
  - Respeta el horario real (calla con el mercado cerrado).

Requisitos en la carpeta / entorno:
  - `ssid_real.txt`  (o env POCKET_OPTION_SSID_REAL) — tu sesión de PO.
  - `TELEGRAM_BOT_TOKEN_REAL` en el .env — token de @FuZionFzbot.
  - chat: manda un mensaje al bot una vez (o define TELEGRAM_CHAT_ID_REAL).

Arranque:  python -m bot.robot_reversion REAL
No correr a la vez que INICIAR_REAL.bat si comparten el mismo SSID (PO rechaza doble
conexión). Las partes puras se prueban en bot/test_robot_reversion.py.
"""
import asyncio
import logging
import os
import sys

from bot.profiles import get_profile
from bot.pocket_probe import _load_ssid
from bot.pocket_client import PocketOptionClient
from bot.candles import CandleBuilder
from bot.history import HistoryRepository
from bot.market_hours import is_open
from bot.senal_reversion import cargar_tabla
from bot.vigilante_reversion import VigilanteReversion

# Pares con el borde de reversión más fuerte (según reversion_tabla.json / backtest).
PARES_FUERTES = ("EURCHF", "AUDNZD", "AUDCAD", "EURGBP", "NZDUSD", "USDCHF", "GBPCHF")
DWELL_SEG = 75                 # segundos escuchando cada par (>=1 vela M1)
# Tiempos cuyo historial se pide al saltar a cada par (para guardar historial completo).
PERIODOS_HISTORIAL = (120, 180, 300, 600, 900, 1800, 3600)


def _chat_de_updates(updates):
    """Saca el chat_id del último update entrante (para no pedirlo a mano). None si no
    hay ninguno. `updates`: lista de objetos Update de python-telegram-bot."""
    for u in reversed(list(updates or [])):
        chat = getattr(u, "effective_chat", None)
        if chat is not None and getattr(chat, "id", None) is not None:
            return str(chat.id)
        msg = getattr(u, "message", None)
        cid = getattr(getattr(msg, "chat", None), "id", None)
        if cid is not None:
            return str(cid)
    return None


class RobotReversion:
    def __init__(self, profile, pares=None, expiry_min=3, dwell_seg=DWELL_SEG,
                 ssid=None, token=None, chat_id=None, tabla=None, repo=None,
                 is_open_fn=None, demo=True):
        self.profile = profile
        self.pares = list(pares) if pares else list(PARES_FUERTES)
        self.expiry_min = int(expiry_min)
        self.dwell_seg = int(dwell_seg)
        self.demo = demo
        self.ssid = ssid if ssid is not None else _load_ssid(profile.nombre)
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN_REAL", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID_REAL", "")
        self.repo = repo if repo is not None else HistoryRepository(profile.db_path)
        if tabla is None:
            tabla = cargar_tabla(os.path.join(profile.datasets_dir, "reversion_tabla.json"))
        self.tabla = tabla
        gate = is_open_fn if is_open_fn is not None else (lambda p: is_open(p)[0])
        self.vig = VigilanteReversion(self.pares, tabla=tabla,
                                      expiry_min=self.expiry_min, is_open=gate)
        self._builders = {}
        self._cola = asyncio.Queue()
        self.client = None
        self.bot = None
        self.log = logging.getLogger("robot_reversion")

    # --- construcción de velas desde ticks (mismo patrón que pocket_service) ---
    def _builder(self, asset):
        return self._builders.setdefault(asset, CandleBuilder(60))

    def _on_tick(self, asset, ts, price):
        """Callback del websocket: alimenta la vela; al cerrar, evalúa reversión."""
        try:
            closed = self._builder(asset).add_tick(price, ts * 1000.0)   # ts en ms
        except Exception:
            return
        if not closed:
            return
        try:
            self.repo.record_candle(asset, "M1", closed)                 # historial reciente
        except Exception:
            self.log.exception("No se pudo guardar la vela de %s", asset)
        s = self.vig.nueva_vela(asset, closed["close"], ts=closed.get("timestamp"))
        if s:
            self._cola.put_nowait(s)

    def _on_history(self, payload):
        """Guarda el historial que Pocket Option manda al saltar a un par (velas OHLC
        ya hechas o ticks que agregamos), en su tiempo (60->M1, otros->tf<seg>). Así
        `history_real.db` crece completo mientras el robot corre."""
        if not isinstance(payload, dict):
            return
        asset = payload.get("asset")
        if not asset:
            return
        try:
            period = int(payload.get("period", 60) or 60)
        except (TypeError, ValueError):
            period = 60
        key = "M1" if period == 60 else f"tf{period}"
        filas = []
        candles = payload.get("candles") or payload.get("data")
        if candles:
            for c in candles:
                try:
                    if isinstance(c, dict):
                        t = float(c.get("time") or c.get("t") or c.get("timestamp"))
                        o = float(c.get("open", c.get("o")))
                        h = float(c.get("high", c.get("h", o)))
                        lo = float(c.get("low", c.get("l", o)))
                        cl = float(c.get("close", c.get("c", o)))
                        vol = float(c.get("volume", c.get("v", 0)) or 0)
                    elif isinstance(c, (list, tuple)) and len(c) >= 5:
                        t, o, cl, h, lo = (float(c[0]), float(c[1]), float(c[2]),
                                           float(c[3]), float(c[4]))
                        vol = float(c[5]) if len(c) > 5 else 0.0
                    else:
                        continue
                except (TypeError, ValueError):
                    continue
                ts_ms = int(t * 1000) if t < 1e12 else int(t)   # seg o ms -> ms
                filas.append({"timestamp": ts_ms, "open": o, "high": h,
                              "low": lo, "close": cl, "volume": vol})
        else:
            hist = payload.get("history", [])
            if not hist:
                return
            cb = CandleBuilder(period)
            for row in hist:
                try:
                    t, p = float(row[0]), float(row[1])
                except (IndexError, TypeError, ValueError):
                    continue
                cb.add_tick(p, t * 1000.0)
            filas = cb.closed_candles()
        if filas:
            try:
                self.repo.record_many(asset, key, filas)
            except Exception:
                self.log.exception("No se pudo guardar historial de %s", asset)

    # --- precarga de contexto desde el historial guardado ---
    def _precargar(self):
        for p in self.pares:
            try:
                df = self.repo.get_recent(p, "M1", 50)
            except Exception:
                df = None
            if df is not None and len(df):
                self.vig.precargar(p, df["close"].astype(float).tolist())

    # --- Telegram ---
    async def _resolver_chat(self):
        if self.chat_id:
            return True
        try:
            ups = await self.bot.get_updates(timeout=5)
            self.chat_id = _chat_de_updates(ups) or ""
        except Exception:
            self.log.exception("No se pudo leer get_updates")
        return bool(self.chat_id)

    async def _enviar_loop(self):
        while True:
            s = await self._cola.get()
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=s["tarjeta"])
                self.log.info("Señal enviada: %s %s %.1f%%",
                              s["par"], s["direccion"], s.get("probabilidad", 0))
            except Exception:
                self.log.exception("No se pudo enviar a Telegram")

    async def _rotar(self):
        i = 0
        while True:
            par = self.pares[i % len(self.pares)]
            try:
                await self.client.set_asset(par, 60)                 # M1 en vivo
                # Pide el historial de los tiempos largos para guardarlo completo;
                # request_history vuelve a 60s al final para seguir con los ticks M1.
                await self.client.request_history(par, PERIODOS_HISTORIAL)
            except Exception:
                self.log.exception("No se pudo cambiar a %s", par)
            i += 1
            await asyncio.sleep(self.dwell_seg)

    async def arrancar(self):
        """Punto de entrada async: conecta, resuelve chat, rota y envía."""
        if not self.ssid:
            raise RuntimeError("Falta ssid_real.txt (o POCKET_OPTION_SSID_REAL).")
        if not self.token:
            raise RuntimeError("Falta TELEGRAM_BOT_TOKEN_REAL en el .env.")
        from telegram import Bot
        self.bot = Bot(self.token)
        await self.bot.initialize()
        if not await self._resolver_chat():
            raise RuntimeError("No sé a qué chat enviar. Manda un mensaje a tu bot en "
                               "Telegram y reintenta, o define TELEGRAM_CHAT_ID_REAL.")
        self._precargar()
        self.client = PocketOptionClient(self.ssid, on_tick=self._on_tick,
                                         on_history=self._on_history,
                                         demo=self.demo, logger=self.log)
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=f"FUZION FX activo. Vigilando {len(self.pares)} pares "
                 f"({', '.join(self.pares)}). Aviso cuando haya reversión con ventaja.")
        tarea_cli = asyncio.create_task(self.client.run(asset=self.pares[0], period=60))
        try:
            await asyncio.gather(self._rotar(), self._enviar_loop(), tarea_cli)
        finally:
            self.client.stop()
            await self.bot.shutdown()


def main(argv):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    # Cargar el .env (token de Telegram, etc.) igual que hace telegram_signals.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    nombre = (argv[0] if argv else "REAL").upper()
    profile = get_profile(nombre)
    # Pares: argumentos extra = lista propia; 'TODOS'/'ALL' = los 22 del perfil;
    # sin argumentos = los 7 fuertes por defecto.
    extra = [a.upper() for a in argv[1:]]
    if extra and extra[0] in ("TODOS", "ALL"):
        pares = list(profile.activos)
    elif extra:
        pares = extra
    else:
        pares = None
    demo = os.getenv("POCKET_DEMO_REAL", "1") not in ("0", "false", "False")
    robot = RobotReversion(profile, pares=pares, demo=demo)
    ciclo = robot.dwell_seg * len(robot.pares)
    print(f"Robot de reversión · perfil {profile.nombre} · "
          f"{len(robot.pares)} pares · demo={demo} · "
          f"vuelta completa ~{ciclo//60} min")
    try:
        asyncio.run(robot.arrancar())
    except KeyboardInterrupt:
        print("\nDetenido.")
    except RuntimeError as e:
        print(f"\nNo pudo arrancar: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
