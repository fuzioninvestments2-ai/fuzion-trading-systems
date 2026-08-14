"""
bots/base_bot.py (fuzion_fx)
============================
Clase base con el LOOP principal de un bot. Cada uno de los 4 procesos crea un
BaseBot con su bot_id (f1_m1, ...) y llama run(). Cablea todas las piezas:

    config -> (store, risk, signal_engine, learning, notifier, price_feed)

Flujo por par: velas -> senal (confirmaciones) -> filtros de riesgo -> filtro de
aprendizaje (descarta setups que fallan) -> limite por hora -> tarjeta a Telegram.

`scan_once()` hace UNA pasada (testeable sin dormir ni red). `run()` la repite
cada `timeframe_seconds`. Sin feed real, el price_feed placeholder devuelve None
y no se emite (seguro).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from core.config import get_bot_config, load_config, ROOT
from core.results_store import ResultsStore
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine, NEUTRAL
from core import quantum_engine, indicator_set
from core.multi_timeframe import MultiTimeframeAnalyzer, TF_SEGUNDOS
from core.learning_engine import LearningEngine
from core import news_guard
from core import control
from core import afiliados
from core.modos import params_modo
from data.price_feed import PriceFeed, StubPriceFeed, CandleStoreFeed
from telegram.notifier import TelegramNotifier
from telegram.signal_formatter import SignalCardFormatter
from telegram.chart import render_candles
from indicators.pips import pip_size

# Base de velas COMPARTIDA que escribe el colector; los bots leen de aca.
PO_CANDLES_DB = os.path.join(ROOT, "data", "db", "po_candles.db")
# Calendario de noticias (bloqueo por evento de alto impacto). Editable en caliente.
NEWS_PATH = os.path.join(ROOT, "config", "news.json")


class BaseBot:
    def __init__(self, bot_id: str, price_feed: Optional[PriceFeed] = None,
                 notifier: Optional[TelegramNotifier] = None,
                 store: Optional[ResultsStore] = None) -> None:
        cfg = get_bot_config(bot_id)
        self.id = bot_id
        self.name = cfg["name"]
        self.pairs = cfg["pairs"]
        self.timeframe = cfg["timeframe"]
        self.timeframe_seconds = int(cfg["timeframe_seconds"])
        self.card_label = cfg["card_label"]
        self.max_signals_per_hour = int(cfg["signal"].get("max_signals_per_hour", 10))
        # Mercado operado (otc/real): el colector se suscribe a ese activo y la
        # tarjeta lo muestra, para que el usuario opere el MISMO (OTC != real: son
        # series de precio distintas). Se lee del top-level 'market' del yaml.
        try:
            _cfg_top = load_config()
            self.mercado = str(_cfg_top.get("market", "otc")).lower()
            # Descanso entre señales (emision ordenada, de a una, global a los 4 bots).
            self.signal_cooldown = int(_cfg_top.get("signal_cooldown_seconds", 600))
        except Exception:
            self.mercado = "otc"
            self.signal_cooldown = 600

        # store inyectable (tests usan ':memory:'); por defecto, la sqlite del bot.
        self.store = store or ResultsStore(cfg["db_path"])
        self.risk = RiskManager(cfg["risk"])
        self.engine = SignalEngine(cfg["indicators"], cfg["signal"])
        # MOTOR: "simple" (el de una tf, 4 indicadores) o "cuantico" (los 8
        # indicadores + ADX + patrones + 7 tiempos, la estrategia de Alex). Default
        # simple para no cambiar el comportamiento probado; se activa por config.
        self.motor = str(cfg.get("motor", "simple")).lower()
        # LA FOTO COMPLETA: analizador de convergencia multi-temporalidad. El motor
        # de una sola tf da el disparo de ENTRADA; la convergencia confirma que TODA
        # la foto (corto/medio/largo) apoya la direccion. Solo se aplica como filtro
        # cuando hay datos de al menos `min_tf_convergencia` temporalidades (si no,
        # cae al motor de una tf: no bloquea al arranque cuando aun no hay historia).
        self.mtf = MultiTimeframeAnalyzer(cfg["indicators"])
        self.min_tf_convergencia = int(cfg.get("min_tf_convergencia", 3))
        self.learning = LearningEngine(self.store, cfg["learning"])
        # Modo actual aplicado (para no releer/loggear en cada pasada si no cambio).
        self._modo_actual = ""
        self._scan_interval = 30               # cadencia (la fija aplicar_modo)
        self._conv_politica = "no_contradice"  # cuanto manda la foto (la fija el modo)
        # Feed real por defecto: lee po_candles.db del colector. Si el colector
        # no arranco (archivo inexistente), CandleStoreFeed devuelve None y el
        # bot simplemente no emite (seguro).
        self.feed = price_feed or CandleStoreFeed(PO_CANDLES_DB)

        # Notifier: cada bot manda por SU token (telegram_token del bot) para que
        # cada tiempo llegue a su propio bot de Telegram; si el bot no define uno,
        # cae al token comun (telegram.bot_token). Mismo canal/chat para todos.
        tg = cfg.get("telegram", {})
        token = cfg.get("telegram_token") or tg.get("bot_token")
        canal = tg.get("channel_id")
        if notifier is not None:
            self.notifier = notifier
        elif token and canal:
            self.notifier = TelegramNotifier(token, canal)
        else:
            self.notifier = None

        # Formateador unico de tarjetas (senal y resultado): el bot no duplica
        # el formato, solo provee los datos ya calculados (Regla 1).
        self.formatter = SignalCardFormatter()

        self._emitted_ts: List[float] = []     # timestamps de emisiones (rate limit)
        # Anti-duplicado (re-armado): ultima direccion avisada por par y CUANDO se
        # aviso. En direccion opuesta se avisa al toque; en la misma direccion se
        # re-avisa solo cuando la senal anterior ya vencio (paso un ciclo del
        # timeframe). Asi una tendencia con varias CALL validas no se silencia.
        self._last_dir: Dict[str, str] = {}
        self._last_emit_ts: Dict[str, float] = {}
        self.payout_pct = 85                   # fallback de DISPLAY si no hay pago real
        # Filtro de pago real: el usuario exige emitir solo en activos con pago
        # >= min_pct (72%). require: si el colector aun no recibio el pago del par,
        # NO emitir (mejor callar que a ciegas). El pago real lo provee el feed
        # (lo guarda el colector desde updateAssets de PO).
        pf = cfg.get("payout", {}) or {}
        self.payout_min = float(pf.get("min_pct", 72))
        self.payout_max = float(pf.get("max_pct", 100))
        self.payout_require = bool(pf.get("require", True))
        # Margen para resolver contra el OHLC real: si al vencer aun no llego la
        # vela real de PO (el colector rota 22 pares), se ESPERA hasta este margen
        # antes de declarar la senal NULA. Evita nulificar de mas por demora del
        # colector, sin inventar un resultado. Configurable por bot.
        self.null_grace_seconds = int(cfg.get("null_grace_seconds", 600))

        # Sistema de Checkpoint Cuantico:
        # - prefilter: recalcula 10s despues; emite SOLO si coincide (menos falsas).
        # - checkpoint: X seg antes del cierre revisa si la direccion se dio vuelta;
        #   si cambio, manda una ALERTA de autocorreccion (informa, no opera).
        self.checkpoint_offset = int(cfg.get("checkpoint_offset", 20))
        self.prefilter_seconds = 10
        self._schedule_enabled = True          # los tests lo apagan
        self._timers: List[threading.Timer] = []
        self._running = False
        self.log = self._setup_logger(cfg.get("log_level", "INFO"))

    def _setup_logger(self, level: str) -> logging.Logger:
        logger = logging.getLogger(f"bot.{self.id}")
        logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
        if not logger.handlers:
            logs_dir = os.path.join(ROOT, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            # UTF-8 en el archivo: las tarjetas llevan emojis (⬆️/⬇️) que en
            # Windows (consola cp1252) romperian el log. Con utf-8 no falla.
            fh = logging.FileHandler(os.path.join(logs_dir, f"{self.id}.log"),
                                     encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
            # Consola: se intenta reconfigurar a utf-8; si no se puede, se
            # reemplazan los caracteres no imprimibles en vez de crashear.
            sh = logging.StreamHandler()
            try:
                sh.stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        return logger

    # ------------------------------------------------------------- rate limit
    def _rate_ok(self, now: float) -> bool:
        """True si no se supero el tope de senales/hora. Purga las viejas."""
        limite = now - 3600.0
        self._emitted_ts = [t for t in self._emitted_ts if t >= limite]
        return len(self._emitted_ts) < self.max_signals_per_hour

    # ------------------------------------------------------------- filtro de pago
    def _payout_de(self, pair: str) -> Optional[float]:
        """Pago real (%) del par segun el feed (colector). None si no hay dato."""
        getter = getattr(self.feed, "get_payout", None)
        if getter is None:
            return None
        try:
            return getter(pair)
        except Exception:
            return None

    def _pago_ok(self, payout: Optional[float]) -> bool:
        """
        True si se puede emitir por pago. Sin dato: depende de payout_require
        (True -> no emitir a ciegas). Con dato: dentro de [min, max].
        """
        if payout is None:
            return not self.payout_require
        return self.payout_min <= payout <= self.payout_max

    # ------------------------------------------------------------- modo (vivo)
    def aplicar_modo(self) -> str:
        """
        Lee el modo (lento/normal/rapido) del control y ajusta EN VIVO la exigencia
        de la FOTO COMPLETA: umbral de convergencia, cuantas temporalidades se
        exigen y la cadencia. NO toca engine.min_confirmations (queda en 2 por
        config: apretarlo dejaria el motor casi mudo). Se puede cambiar desde el
        panel sin reiniciar. Devuelve el modo aplicado y cachea la cadencia.
        """
        modo = control.get_modo()
        p = params_modo(modo)
        self.mtf.umbral = float(p["umbral_convergencia"])
        self.min_tf_convergencia = int(p["min_tf_convergencia"])
        self._conv_politica = str(p.get("convergencia", "no_contradice"))
        self._scan_interval = max(15, int(p["scan_interval"]))
        if modo != self._modo_actual:
            self.log.info("Modo '%s': convergencia>=%.2f, %d tiempos, rastreo %ds "
                          "(min_confirmations queda en %s por config)", modo,
                          p["umbral_convergencia"], p["min_tf_convergencia"],
                          self._scan_interval,
                          getattr(self.engine, "min_confirmations", "?"))
            self._modo_actual = modo
        return modo

    # ------------------------------------------------------------- foto completa
    # ------------------------------------------------------- motor cuantico
    def _veredictos_ok(self) -> set:
        """Que veredictos habilitan emitir. En modo 'rapido' se acepta tambien
        OPCIONAL (mas señales); en normal/lento solo OPERAR (mas estricto)."""
        if getattr(self, "_modo_actual", "normal") == "rapido":
            return {"OPERAR", "OPCIONAL"}
        return {"OPERAR"}

    def analisis_cuantico(self, pair: str) -> Optional[Dict[str, Any]]:
        """Corre el motor cuantico sobre los 7 tiempos del par (los que el feed
        tenga con velas suficientes). None si no hay datos."""
        velas: Dict[int, Any] = {}
        for tf in quantum_engine.PESO_TF:
            try:
                c = self.feed.get_candles(pair, tf)
            except Exception:
                c = None
            if c and len(c.get("close", [])) >= indicator_set.MIN_VELAS:
                velas[tf] = c
        if not velas:
            return None
        return quantum_engine.analizar(velas)

    def _result_desde_cuantico(self, pair: str, candles: Dict[str, Any],
                               qr: Dict[str, Any]) -> Dict[str, Any]:
        """Traduce el veredicto cuantico al dict `result` que espera el pipeline
        (build_card, rec, aprendizaje). La direccion y la probabilidad salen del
        motor; los indicadores del tf base alimentan la tarjeta."""
        d = qr["direccion"]
        signal = "CALL" if d == indicator_set.CALL else "PUT"
        base = qr["por_tf"].get(self.timeframe_seconds) or next(iter(qr["por_tf"].values()))
        votos = indicator_set.votar(candles)
        confirming = [n for n, v in votos.items()
                      if n != "momentum" and v.get("dir") == d]
        votes = {n: int(v.get("dir", 0)) for n, v in votos.items()}
        import numpy as _np
        atr = float(indicator_set._atr(
            _np.asarray(candles["high"], float), _np.asarray(candles["low"], float),
            _np.asarray(candles["close"], float))[-1])
        return {
            "signal": signal,
            "setup_id": f"{signal}|Q|{base.get('modo', 'na')}",
            "confirming": confirming, "confirmations": len(confirming),
            "confirmations_list": confirming,
            "price": float(candles["close"][-1]), "atr": atr,
            "votes": votes, "readings": {},
            "probabilidad": qr["probabilidad"], "alineacion": qr["alineacion"],
            "veredicto": qr["veredicto"], "modo_mkt": base.get("modo"),
            "patron": base.get("patron"), "n_alineados": qr["n_alineados"],
        }

    def _filtro_convergencia_simple(self, pair: str, result: Dict[str, Any]):
        """
        Filtro de convergencia del motor SIMPLE (la foto completa segun la politica
        del modo). Devuelve (fuerza, detalle) para el registro/tarjeta, o None si la
        foto FRENA la señal. Extraido de scan_once para separar del motor cuantico.
        """
        conv = self.convergencia(pair)
        if conv is None:
            return (None, "")
        sig = conv["signal"]                             # CALL/PUT/NEUTRAL (segun umbral)
        apoya = sig == result["signal"]
        opuesta = sig != NEUTRAL and not apoya
        politica = getattr(self, "_conv_politica", "no_contradice")
        if politica == "confirma":
            frena = not (apoya and conv["total"] >= self.min_tf_convergencia)
        elif politica == "no_contradice":
            frena = opuesta                              # nunca operar contra la foto
        else:                                            # "info": no frena
            frena = False
        if frena:
            self.log.info("Foto completa frena %s %s (modo=%s, conv=%s, %s)",
                          pair, result["signal"], getattr(self, "_modo_actual", "?"),
                          sig, conv["detalle"])
            return None
        # Fuerza direccional: solo si la foto APOYA la direccion; si no, 0.
        fuerza = conv["convergencia"] if apoya else 0.0
        detalle = ""
        if conv["detalle"]:
            detalle = (f"{conv['alineadas']}/{conv['total']} tiempos "
                       f"({conv['detalle']}) conv {conv['convergencia']:.0%}")
        return (fuerza, detalle)

    def convergencia(self, pair: str) -> Optional[Dict[str, Any]]:
        """
        Lee las velas de TODAS las temporalidades disponibles (5s..1h) del par y
        devuelve el veredicto de convergencia (o None si el feed no las tiene). Es
        la "foto completa": el conjunto de tiempos, no una sola tf.
        """
        velas: Dict[int, Any] = {}
        for tf in TF_SEGUNDOS.values():
            try:
                c = self.feed.get_candles(pair, tf)
            except Exception:
                c = None
            if c and len(c.get("close", [])) >= 2:
                velas[tf] = c
        if not velas:
            return None
        return self.mtf.analizar(velas)

    # -------------------------------------------------------- ancla de tiempo
    def _entry_border(self, candles: Optional[Dict[str, Any]],
                      emitido: float) -> int:
        """
        Borde de la vela de ENTRADA (epoch, multiplo de tf) ANCLADO a la grilla de
        PO. Toma el ts de la ULTIMA vela conocida (reloj de PO, via colector) y
        devuelve la SIGUIENTE (ultimo+tf): la vela que el humano opera de open a
        close. Asi la hora anunciada y la vela liquidada usan el MISMO reloj y no
        se desfasan aunque el reloj del PC este corrido.

        Fallback (tests/feed sin 'ts' o vacio): grilla del reloj local, como antes.
        """
        tf = self.timeframe_seconds
        epoch = int(emitido)
        borde_local = epoch - (epoch % tf) + tf if tf > 0 else epoch
        ts_list = candles.get("ts") if isinstance(candles, dict) else None
        if ts_list:
            ultimo = int(ts_list[-1])
            # Normaliza por si el ultimo ts no cayera exacto en la grilla.
            base = ultimo - (ultimo % tf) if tf > 0 else ultimo
            borde_po = base + tf                 # siguiente vela en el reloj de PO
            # MAX de ambos: nunca antes de la vela siguiente a la ultima real (para
            # que la liquidacion tenga dato pronto y no se resuelva 'en el pasado')
            # ni antes del proximo borde local. Cubre reloj adelantado/atrasado y
            # colector con lag, manteniendo todo en la MISMA grilla.
            return max(borde_local, borde_po)
        return borde_local

    # ------------------------------------------------------------- tarjeta rica
    def build_card(self, pair: str, result: Dict[str, Any],
                   payout: Optional[float] = None,
                   entry_ts: Optional[int] = None,
                   confluencia: str = "", fuerza: Optional[float] = None,
                   show_ts: Optional[int] = None) -> str:
        """
        Arma el dict de datos POR PAR y delega el formato en SignalCardFormatter.
        El bot solo calcula (tiempos, ATR en pips, acierto por par); el formato
        (estrella, colores, mercado, disclaimer) vive en el formatter (Regla 1).
        Los tiempos van en hora LOCAL de la PC.

        entry_ts: borde de vela de entrada en el grid de PO (para liquidar).
        show_ts: MISMO borde pero en el reloj LOCAL real (para MOSTRAR la hora). Se
        separan porque el epoch de PO va adelantado (UTC+2): mostrar entry_ts diria
        una hora +2h de la real. Si show_ts no viene, se usa entry_ts (compat/tests).
        """
        from datetime import datetime, timezone

        ahora = datetime.now().astimezone()          # local, con tz
        off = ahora.utcoffset()
        horas_off = int(off.total_seconds() // 3600) if off else 0
        # Entrada = borde de vela ya fijado al emitir; vence = entrada + timeframe.
        seg = self.timeframe_seconds
        if entry_ts is None:
            epoch = int(ahora.timestamp())
            entry_ts = epoch - (epoch % seg) + seg
        entry_ts = int(entry_ts)
        # La HORA mostrada sale del reloj local (show_ts); si no vino, cae a entry_ts.
        disp = int(show_ts) if show_ts is not None else entry_ts
        entrada = datetime.fromtimestamp(disp).astimezone()
        vence = datetime.fromtimestamp(disp + seg).astimezone()

        # ATR en pips (volatilidad reciente real).
        ps = pip_size(pair)
        atr_pips = round(result["atr"] / ps, 1) if ps else 0.0

        # Acierto reciente POR PAR (win_rate(pair)): acumulado del par, no por
        # setup. Sin muestra -> acierto_pct None para que el formatter muestre
        # "sin muestra aún".
        wr = self.store.win_rate(pair)
        acierto_pct = wr["win_pct"] if wr["trades"] > 0 else None

        # card_label de bots.yaml; si no hubiera, cae al nombre del bot.
        etiqueta = self.card_label or self.name

        d = {
            "bot_name": self.name,
            "card_label": etiqueta,
            "par": pair,
            "es_otc": self.mercado == "otc",     # muestra "OTC" -> operar el activo correcto
            "direccion": result["signal"],
            "hora_entrada": entrada.strftime("%H:%M"),
            "hora_vencimiento": vence.strftime("%H:%M"),
            "tz_offset": horas_off,
            # utc_hour: el formatter deriva el mercado (Asia/Europe/America).
            "utc_hour": datetime.now(timezone.utc).hour,
            # Pago REAL del activo (lo que paga PO ahora); si no hay dato, el
            # fallback de display. El filtro ya garantizo que es >= min_pct.
            "payout": int(round(payout)) if payout is not None else self.payout_pct,
            "confirmaciones": result["confirming"],
            "votos": result.get("votes", {}),  # ema/rsi/macd/bollinger: +1/-1/0
            "acierto_pct": acierto_pct,
            "n_muestras": wr["trades"],
            "atr": atr_pips,
            "confluencia": confluencia,        # foto completa (multi-temporalidad)
            "fuerza": fuerza,                  # convergencia 0..1 (para el badge FUERZA)
            # Motor cuantico: probabilidad y alineacion para mostrarlas prominentes
            # (formato de la tarjeta de Alex). None en motor simple -> no se muestran.
            "probabilidad": result.get("probabilidad"),
            "alineacion": result.get("alineacion"),
            "n_alineados": result.get("n_alineados"),
            "modo_mkt": result.get("modo_mkt"),
            "patron": result.get("patron"),
        }
        return self.formatter.format_signal(d)

    # ------------------------------------------------------------- una pasada
    def scan_once(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Una pasada por todos los pares. Devuelve la lista de senales emitidas.
        No duerme ni exige red (con feed en memoria se testea entero).
        """
        now = time.time() if now is None else now
        emitidas: List[Dict[str, Any]] = []
        # PAUSA global (boton del panel): si esta pausado, no se emite nada. No
        # mata el proceso (el vigilante no pelea); solo silencia hasta reanudar.
        if control.esta_pausado():
            return emitidas
        # Modo en vivo (lento/normal/rapido): ajusta exigencia antes de la pasada.
        self.aplicar_modo()
        # EMISION ORDENADA (de a una, GLOBAL a los 4 bots): si hay una señal en
        # curso o el descanso no termino, no se emite nada esta pasada. Asi las
        # señales llegan de a una y con espacio (no en rafagas).
        if self.signal_cooldown > 0 and now < control.get_emitir_despues_de():
            return emitidas
        # Noticias: se releen cada pasada (el archivo se puede editar en caliente).
        eventos = news_guard.cargar_eventos(NEWS_PATH)

        # PRIORIDAD POR PAGO: el usuario quiere que ELIJA la mayor. Se lee el pago
        # UNA vez por par (se reusa abajo) y se ordenan por pago (%) descendente, asi
        # los de mejor pago se analizan y emiten PRIMERO (con el tope por hora, los de
        # pago alto ganan el cupo). Sin dato de pago (None) van al final. Ojo: un pago
        # real de 0% NO es 'sin dato' -> se compara con `is not None`, no con `or`.
        pago_de = {p: self._payout_de(p) for p in self.pairs}
        pares_ordenados = sorted(
            self.pairs,
            key=lambda p: pago_de[p] if pago_de[p] is not None else -1.0,
            reverse=True)

        for pair in pares_ordenados:
            if not self._rate_ok(now):
                self.log.info("Tope de %d senales/hora alcanzado; se corta la pasada",
                              self.max_signals_per_hour)
                break

            candles = self.feed.get_candles(pair, self.timeframe_seconds)
            if not candles or len(candles.get("close", [])) < 2:
                continue

            # MOTOR CUANTICO: la direccion y la probabilidad las decide el motor
            # sobre los 7 tiempos; solo se emite si el veredicto habilita (OPERAR, o
            # OPCIONAL en modo rapido). El motor SIMPLE (de una tf) es el fallback.
            if self.motor == "cuantico":
                qr = self.analisis_cuantico(pair)
                if qr is None or qr["veredicto"] not in self._veredictos_ok():
                    self._last_dir[pair] = None
                    continue
                result = self._result_desde_cuantico(pair, candles, qr)
            else:
                result = self.engine.analyze(candles)
                if result["signal"] == NEUTRAL:
                    # Sin senal: se resetea el par para que una nueva CALL/PUT avise.
                    self._last_dir[pair] = None
                    continue

            # ANTI-DUPLICADO (re-armado): direccion OPUESTA -> avisa al toque;
            # MISMA direccion -> re-avisa solo si la senal anterior YA vencio (paso
            # un ciclo del timeframe). Evita repetir la misma senal dentro del
            # mismo minuto, pero no se pierde una tendencia con varias CALL seguidas.
            if self._last_dir.get(pair) == result["signal"]:
                if now - self._last_emit_ts.get(pair, 0.0) < self.timeframe_seconds:
                    continue

            # BLOQUEO POR NOTICIAS: en la ventana de una noticia de alto impacto no
            # se opera (precio erratico, spread alto). Ventana = news_buffer_minutes.
            bloqueo, evento = news_guard.en_bloqueo(
                now, eventos, self.risk.news_buffer_minutes, pair)
            if bloqueo:
                self.log.info("Noticia bloquea %s: %s (±%d min)", pair,
                              evento["titulo"], self.risk.news_buffer_minutes)
                continue

            # FILTRO DE PAGO: solo emitir si el activo paga dentro de la banda
            # (53-92%). Un pago bajo destruye la ventaja aunque el acierto sea bueno
            # (break-even sube). Sin dato de pago -> no emitir. Se reusa el pago ya
            # leido para el ordenamiento (no se relee el feed).
            pago = pago_de[pair]
            if not self._pago_ok(pago):
                self.log.debug("Pago fuera de rango en %s: %s (min %s)",
                               pair, pago, self.payout_min)
                continue

            ok, motivo = self.risk.can_trade(pair)
            if not ok:
                self.log.debug("Riesgo bloquea %s: %s", pair, motivo)
                continue

            if not self.learning.should_emit(result["setup_id"]):
                self.log.debug("Aprendizaje descarta setup %s", result["setup_id"])
                continue

            # PRE-FILTRO: recalcular tras `prefilter_seconds`; emitir SOLO si la
            # direccion se mantiene (descarta setups que se dan vuelta al toque).
            confirmado = self._prefiltro(pair, result["signal"])
            if confirmado is None or confirmado["signal"] != result["signal"]:
                self.log.info("Pre-filtro descarta %s %s (cambio en %ds)",
                              pair, result["signal"], self.prefilter_seconds)
                continue
            result = confirmado                # usar la lectura fresca confirmada

            # GATE DE FOTO COMPLETA. En cuantico el motor YA hizo los 7 tiempos y su
            # veredicto: no se re-filtra; la fuerza es la alineacion. En simple, el
            # filtro de convergencia clasico (puede FRENAR).
            if self.motor == "cuantico":
                fuerza = result.get("alineacion")
                conv_detalle = (f"{result.get('n_alineados', 0)} tiempos · "
                                f"prob {result.get('probabilidad', 0):.0%} · "
                                f"alin {result.get('alineacion', 0):.0%} · "
                                f"modo {result.get('modo_mkt', '')}")
                if result.get("patron"):
                    conv_detalle += f" · patron {result['patron']}"
            else:
                gate = self._filtro_convergencia_simple(pair, result)
                if gate is None:                          # la foto FRENA la señal
                    continue
                fuerza, conv_detalle = gate

            # DOS bordes de la MISMA vela operada:
            #  - entry_border (grid de PO): para LIQUIDAR contra la vela real. El
            #    epoch de PO va adelantado (UTC+2), asi que casa con lo guardado.
            #  - entry_show (reloj LOCAL real): para MOSTRAR la hora al humano. Si se
            #    mostrara entry_border, la tarjeta diria una hora +2h de la real
            #    (justo el desfase que se veia). Ambos son la SIGUIENTE vela.
            emitido = time.time()
            tf = self.timeframe_seconds
            entry_border = self._entry_border(candles, emitido)
            entry_show = int(emitido) - (int(emitido) % tf) + tf
            # fuerza (direccional) ya calculada en el gate de convergencia arriba.

            # Emitir: persistir + notificar (tarjeta + grafico) + contadores.
            rec = {"ts": int(emitido), "pair": pair, "timeframe": self.timeframe,
                   "direction": result["signal"], "setup_id": result["setup_id"],
                   "confirmations": result["confirmations"],
                   "price": result["price"], "atr": result["atr"],
                   "entry_ts": entry_border, "entry_show_ts": entry_show,
                   "fuerza": fuerza}
            sid = self.store.save_signal(rec)
            rec["id"] = sid
            card = self.build_card(pair, result, payout=pago, entry_ts=entry_border,
                                   confluencia=conv_detalle, fuerza=fuerza,
                                   show_ts=entry_show)
            if self.notifier:
                # Grafico coordinado con la senal (velas frescas + direccion + entrada).
                img = None
                try:
                    velas_grafico = self.feed.get_candles(pair, self.timeframe_seconds) or candles
                    img = render_candles(
                        velas_grafico, f"{self.name} · {pair} · {self.card_label}",
                        result["signal"], entry_price=result["price"])
                except Exception:
                    img = None
                # 1) Al DUENO: respeta su toggle de Telegram por temporalidad.
                if control.telegram_activo(self.id):
                    self.notifier.send(card, photo_buffer=img)
                # 2) A los AFILIADOS activos suscriptos a esta temporalidad. En bytes
                #    (no BytesIO) para reenviar la misma foto a muchos sin consumirla.
                img_bytes = img.getvalue() if img is not None else None
                for a in afiliados.destinatarios_para(self.id):
                    try:
                        self.notifier.enviar_a(a["chat_id"], card, photo=img_bytes)
                    except Exception:
                        self.log.warning("No se pudo enviar a afiliado %s",
                                         a.get("nombre"))
            else:
                self.log.info("[DRY-RUN sin token] %s", card.replace("\n", " | "))

            self._last_dir[pair] = result["signal"]
            self._last_emit_ts[pair] = now         # para el re-armado por vencimiento
            self._emitted_ts.append(now)
            emitidas.append(rec)
            self.log.info("Senal emitida: %s %s (setup %s)", pair,
                          result["signal"], result["setup_id"])

            # CHECKPOINT: agendar revision X seg antes del CIERRE de la vela operada
            # (entry_border..entry_border+tf), la misma que se liquida.
            expiry = entry_border + tf
            self._schedule_checkpoint(pair, result["signal"], expiry, result, emitido)

            # EMISION ORDENADA: fija el candado GLOBAL (los 4 bots lo respetan) hasta
            # que esta señal VENZA + el descanso, y CORTA la pasada: una sola señal
            # por ventana, no una rafaga de pares. Con cooldown<=0 (tests) no aplica.
            if self.signal_cooldown > 0:
                control.set_emitir_despues_de(expiry + self.signal_cooldown)
                break

        return emitidas

    # ---------------------------------------------- Checkpoint Cuantico
    def _prefiltro(self, pair: str, direccion: str) -> Optional[Dict[str, Any]]:
        """
        Espera `prefilter_seconds` y recalcula con datos frescos. Devuelve el
        nuevo `analyze` (para reusarlo) o None si no hay datos. El caller compara
        la direccion: si cambio, no emite.
        """
        if self.prefilter_seconds > 0:
            time.sleep(self.prefilter_seconds)
        candles = self.feed.get_candles(pair, self.timeframe_seconds)
        if not candles or len(candles.get("close", [])) < 2:
            return None
        # En cuantico, re-verificar con el motor cuantico (misma exigencia de
        # veredicto); si ya no habilita o cambio de direccion, el caller descarta.
        if self.motor == "cuantico":
            qr = self.analisis_cuantico(pair)
            if qr is None or qr["veredicto"] not in self._veredictos_ok():
                return None
            return self._result_desde_cuantico(pair, candles, qr)
        return self.engine.analyze(candles)

    def _schedule_checkpoint(self, pair: str, direccion: str, expiry_ts: int,
                             orig: Dict[str, Any], ts_emitida: float) -> None:
        """Agenda el checkpoint en expiry - checkpoint_offset (timer en background)."""
        if not self._schedule_enabled:
            return
        delay = expiry_ts - self.checkpoint_offset - time.time()
        if delay <= 0:
            return                             # ya no da tiempo; se omite
        t = threading.Timer(delay, self._run_checkpoint,
                            args=(pair, direccion, orig, ts_emitida))
        t.daemon = True
        t.start()
        self._timers.append(t)

    def _run_checkpoint(self, pair: str, direccion_orig: str,
                        orig: Dict[str, Any], ts_emitida: float) -> Optional[str]:
        """
        Recalcula con los datos mas frescos. Si la direccion se dio vuelta, manda
        una ALERTA de autocorreccion. Devuelve el texto de la alerta (o None).
        """
        candles = self.feed.get_candles(pair, self.timeframe_seconds)
        if not candles or len(candles.get("close", [])) < 2:
            return None
        nuevo = self.engine.analyze(candles)
        nueva_dir = nuevo["signal"]
        # Misma direccion (o sin senal) -> no se hace nada.
        if nueva_dir == NEUTRAL or nueva_dir == direccion_orig:
            return None

        segs = int(time.time() - ts_emitida)
        cambios = self._describir_cambios(orig, nuevo)
        alerta = (f"*AUTOCORRECCION* · {self.name}\n"
                  f"Par: *{pair}*\n"
                  f"Señal original: *{direccion_orig}*  →  detectado ahora: *{nueva_dir}*\n"
                  f"Emitida hace {segs}s\n"
                  f"Cambios: {cambios}\n"
                  f"_Alerta informativa. El bot no opera por vos._")
        if self.notifier and control.telegram_activo(self.id):
            self.notifier.send_alert(alerta)
        else:
            self.log.info("[DRY-RUN alerta] %s", alerta.replace("\n", " | "))
        return alerta

    @staticmethod
    def _describir_cambios(orig: Dict[str, Any], nuevo: Dict[str, Any]) -> str:
        """Describe que indicadores se movieron (ej: 'RSI cruzo de 65 a 35')."""
        partes = []
        o = orig.get("readings", {})
        n = nuevo.get("readings", {})
        if "rsi" in o and "rsi" in n and abs(o["rsi"] - n["rsi"]) >= 5:
            partes.append(f"RSI cruzó de {o['rsi']:.0f} a {n['rsi']:.0f}")
        # Votos de indicadores que cambiaron de signo.
        ov, nv = orig.get("votes", {}), nuevo.get("votes", {})
        for k in ov:
            if ov[k] != nv.get(k):
                partes.append(f"{k} se dio vuelta")
        return "; ".join(partes) or "el balance de indicadores se invirtió"

    # ------------------------------------------------- feedback loop (aprendizaje)
    PAYOUT_ASUMIDO = 0.80          # payout tipico para el PnL sintetico de aprendizaje

    def resolve_pending(self, now: Optional[float] = None) -> int:
        """
        Cierra el loop de aprendizaje: para cada senal vencida, la liquida sobre LA
        MISMA vela que opera el humano y decide win/loss. Actualiza el store (que
        alimenta al LearningEngine) y el riesgo. Devuelve cuantas resolvio con
        resultado REAL (las nulas no cuentan).

        HONESTIDAD (Pasos 3 y 4): la tarjeta le dice al humano que ENTRE en el
        proximo borde de vela y venza un timeframe despues. Entonces la operacion
        real es UNA vela: la del borde. Se puntua sobre ESA vela real de PO
        (open=precio de entrada en el borde, close=precio al vencimiento), NO desde
        el instante en que el bot detecto (eso adelantaba el resultado y daba un
        win-rate irreal). Si no hay vela real de esa operacion, se ESPERA hasta
        `null_grace_seconds`; pasado el margen, NULA (no se interpola, no se
        inventa, no se gana por defecto). Las nulas se ignoran en win-rate y
        aprendizaje; quedan registradas para auditoria.

        PnL SINTETICO (senal, no dinero real del usuario): +stake*payout si acierta,
        -stake si falla; sirve para que el bot mida su propio rendimiento y aprenda.
        """
        now = time.time() if now is None else now
        tf = self.timeframe_seconds
        # Resolucion SOLO contra el OHLC real de la vela operada: si el feed no lo
        # expone, no se resuelve (mejor no resolver que resolver sobre datos malos).
        real_candle_at = getattr(self.feed, "real_candle_at", None)
        if real_candle_at is None:
            return 0
        cutoff = now - tf
        n = 0
        nulas = 0
        for s in self.store.pending_older_than(int(cutoff)):
            ts = int(s["ts"])
            # Borde de entrada = el que se FIJO y guardo al emitir (entry_ts): la
            # tarjeta anuncio ESE borde y la vela operada abre ahi y vence en
            # borde+tf. Se liquida contra la MISMA vela que vio el humano. Fallback
            # legado (senales viejas sin entry_ts): recalcular desde ts.
            entry_border = s.get("entry_ts")
            entry_border = int(entry_border) if entry_border is not None else (
                ts - (ts % tf) + tf)
            expiry = entry_border + tf
            # NO resolver antes de que la vela operada CIERRE: si PO ya mando la
            # vela EN FORMACION, real_candle_at devolveria un cierre de mitad de
            # vela (resultado prematuro, puede no coincidir con el cierre real).
            # Se espera a que venza (now >= expiry) y recien ahi se liquida.
            if now < expiry:
                continue
            vela = real_candle_at(s["pair"], tf, entry_border)
            if vela is None:
                # Sin vela real de la operacion: esperar dentro del margen; pasado
                # el margen, NULA (no se inventa un cierre).
                if now - expiry < self.null_grace_seconds:
                    continue
                self.store.resolve_signal(s["id"], "NULL", 0.0)
                nulas += 1
                self.log.info("Senal NULA %s %s: sin vela real de la operacion "
                              "(borde %d, +%ds). No cuenta en win-rate ni aprendizaje.",
                              s["pair"], s["direction"], entry_border,
                              int(now - expiry))
                # AVISAR la NULA: antes se resolvia NULL en silencio y el humano se
                # quedaba sin resultado (parecia que la señal "no mando nada"). Ahora
                # se le dice que no se pudo medir (no cuenta como win ni loss).
                self._notificar_resultado(s, None, None, "nula")
                continue
            entry, exit_price = vela                 # open (borde) y close (vencimiento)
            if exit_price == entry:
                result, won = "tie", False
            elif s["direction"] == "CALL":
                won = exit_price > entry
                result = "win" if won else "loss"
            else:                                    # PUT
                won = exit_price < entry
                result = "win" if won else "loss"

            stake = self.risk.position_size()
            pnl = round(stake * self.PAYOUT_ASUMIDO, 2) if won else (
                0.0 if result == "tie" else -stake)
            self.store.resolve_signal(s["id"], result, pnl)
            if result != "tie":
                self.risk.register_result(s["pair"], pnl, won)

            # RESULTADO a Telegram: cuando vence la senal, avisa WIN/LOSS. En una
            # perdida, en vez de doblar (martingala, prohibido y peligroso), el par
            # entra en RECUPERACION: la proxima senal sera mas estricta y menor.
            self._notificar_resultado(s, entry, exit_price, result)
            n += 1
        if n or nulas:
            self.log.info("Resueltas %d senales reales, %d nulas (sin dato real)",
                          n, nulas)
        return n

    def _notificar_resultado(self, s: Dict[str, Any], entry: float,
                             exit_price: float, result: str) -> None:
        """Manda la tarjeta de RESULTADO (WIN/LOSS/EMPATE) al Telegram del bot.

        El par va CON barra en la tarjeta de resultado (GBP/AUD). La nota de
        recuperacion se agrega SOLO en perdida y si el RiskManager marca al par
        en recuperacion (in_recovery); nunca en WIN. En vez de doblar (martingala,
        prohibido), la proxima senal del par sera mas estricta y de menor tamano.
        """
        pair = s["pair"]
        modo_recuperacion = (result == "loss" and self.risk.in_recovery(pair))
        # HORA de la operacion (misma que anuncio la señal): el resultado la repite
        # para que el humano RELACIONE cada WIN/LOSS con su señal (antes el
        # resultado no traia hora -> con varias en vuelo no se sabia cual era).
        from datetime import datetime
        tf = self.timeframe_seconds
        # Hora en reloj LOCAL (entry_show_ts); entry_ts es el grid de PO (+2h) y solo
        # sirve para liquidar. Fallback a entry_ts por si una señal vieja no lo tiene.
        eb = s.get("entry_show_ts")
        if eb is None:
            eb = s.get("entry_ts")
        hora_op = ""
        if eb is not None:
            ent = datetime.fromtimestamp(int(eb)).astimezone()
            ven = datetime.fromtimestamp(int(eb) + tf).astimezone()
            hora_op = f"{ent.strftime('%H:%M')}→{ven.strftime('%H:%M')}"
        d = {
            "bot_name": self.name,
            "card_label": self.card_label or self.name,
            "par": pair,                       # con barra (GBP/AUD)
            "es_otc": self.mercado == "otc",
            "direccion": s["direction"],
            "resultado": result,
            "entrada": entry,
            "cierre": exit_price,
            "hora_operacion": hora_op,         # "11:59→12:00" para relacionar
            "modo_recuperacion": modo_recuperacion,
        }
        txt = self.formatter.format_result(d)
        if self.notifier and control.telegram_activo(self.id):
            self.notifier.send_text(txt)
        else:
            self.log.info("[DRY-RUN resultado] %s", txt.replace("\n", " | "))

    # ------------------------------------------------- salud / latido (visibilidad)
    def estado_operativo(self, now: Optional[float] = None) -> Dict[str, Any]:
        """
        Radiografia RAPIDA de por que emite o no AHORA: cuantos pares tienen velas
        para analizar y cuantos tienen pago dentro de la banda. Es lo que necesita
        el usuario para saber si el freno es el colector (sin velas), el pago (0 en
        banda) o el motor (hay datos y pago pero no hubo setup). Solo lee.
        """
        now = time.time() if now is None else now
        con_datos = 0
        en_banda: List = []
        con_pago: List = []                          # TODOS los pagos capturados
        for pair in self.pairs:
            try:
                c = self.feed.get_candles(pair, self.timeframe_seconds)
                if c and len(c.get("close", [])) >= 2:
                    con_datos += 1
                p = self._payout_de(pair)
                if p is not None:
                    con_pago.append((pair, p))
                    if self.payout_min <= p <= self.payout_max:
                        en_banda.append((pair, p))
            except Exception:
                continue
        emitidas_hora = len([t for t in self._emitted_ts if t >= now - 3600.0])
        # top: mejores pagos capturados (en la banda o no) -> revela si el mercado
        # paga poco (real de madrugada) o si directamente no se capturo pago.
        top = sorted(con_pago, key=lambda x: -x[1])[:6]
        return {"pares": len(self.pairs), "con_datos": con_datos,
                "en_banda": en_banda, "con_pago": len(con_pago), "top": top,
                "emitidas_hora": emitidas_hora}

    def _tarjeta_salud(self, prefijo: str, now: Optional[float] = None) -> str:
        """Tarjeta de estado para Telegram: dice si busca o QUE lo frena, en claro."""
        e = self.estado_operativo(now)
        n_banda = len(e["en_banda"])
        if e["con_datos"] == 0:
            diag = ("⏳ Sin velas aún: el colector está cargando o el mercado está "
                    "cerrado. En cuanto lleguen velas, analizo.")
        elif n_banda == 0:
            # Revelar los mejores pagos capturados: si hay pagos pero por debajo de
            # 72%, el mercado paga poco ahora (bajar el minimo o esperar); si no hay
            # NINGUN pago capturado, es problema de captura (no de banda).
            if e.get("con_pago", 0) == 0:
                extra = ("No se capturo NINGUN pago todavia (updateAssets). Espera "
                         "1-2 min; si sigue en 0, es la captura de pagos.")
            else:
                mejores = ", ".join(f"{p} {int(v)}%" for p, v in e.get("top", []))
                extra = f"Mejores pagos AHORA: {mejores}."
            diag = (f"🚫 0 pares con pago {int(self.payout_min)}-"
                    f"{int(self.payout_max)}%. {extra}")
        else:
            muestra = ", ".join(f"{p} {int(v)}%" for p, v in sorted(
                e["en_banda"], key=lambda x: -x[1])[:6])
            diag = (f"✅ Operativo: {n_banda} pares con buen pago ({muestra}). "
                    f"Buscando setups.")
        return (f"🩺 *{self.name}* — {prefijo}  ·  modo *{control.get_modo()}*\n"
                f"Pares: {e['pares']} · con datos: {e['con_datos']} · "
                f"pago {int(self.payout_min)}-{int(self.payout_max)}%: {n_banda}\n"
                f"Señales última hora: {e['emitidas_hora']}\n"
                f"{diag}")

    def _notificar_salud(self, prefijo: str, now: Optional[float] = None) -> None:
        """Manda la tarjeta de salud al Telegram del dueño (si está activo)."""
        txt = self._tarjeta_salud(prefijo, now)
        if self.notifier and control.telegram_activo(self.id):
            try:
                self.notifier.send_alert(txt)
            except Exception:
                self.log.warning("No se pudo enviar la tarjeta de salud")
        else:
            self.log.info("[DRY-RUN salud] %s", txt.replace("\n", " | "))

    # ------------------------------------------------------------- loop
    def run(self) -> None:
        """
        Loop principal: resolver vencidas + una pasada. Escanea MÁS SEGUIDO que el
        timeframe (cada `scan_interval`, tope 30s) para más análisis y reacción; el
        anti-duplicado evita repetir la misma señal dentro del ciclo. Manda una
        tarjeta de SALUD al arrancar y un latido cada hora (visibilidad: el usuario
        ve al toque si busca o qué lo frena, sin mirar logs).
        """
        self._running = True
        modo = self.aplicar_modo()                 # fija exigencia y cadencia inicial
        self.log.info("%s arrancado (%d pares, modo '%s', tf %ds). Feed: %s | "
                      "Telegram: %s", self.name, len(self.pairs), modo,
                      self.timeframe_seconds, type(self.feed).__name__,
                      "ON" if self.notifier else "DRY-RUN")
        self._notificar_salud("arranque")          # el bot avisa que está vivo
        ultimo_latido = time.time()
        while self._running:
            try:
                self.resolve_pending()       # aprende de las senales ya vencidas
                self.scan_once()             # busca nuevas (aplica el modo en vivo)
                # Latido cada hora: sigue vivo + estado (aunque esté callado).
                if time.time() - ultimo_latido >= 3600:
                    self._notificar_salud("latido (1h)")
                    ultimo_latido = time.time()
            except Exception:
                self.log.exception("Error en la pasada; el bot sigue vivo")
            # Cadencia segun el modo (rapido=15s .. lento=45s). scan_once() ya llamo
            # a aplicar_modo() y dejo self._scan_interval fresco: se reusa sin releer
            # el control de nuevo (si cambiaste el modo en el panel, ya esta aplicado).
            time.sleep(getattr(self, "_scan_interval", 30))

    def stop(self) -> None:
        self._running = False
