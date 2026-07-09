"""
bot/skills/bot_real.py
======================
BOT DE SEÑALES para Mercado Real de Pocket Option. Reúne todos los skills en el
`SkillManager`, arma velas del feed en vivo, genera CONSENSO (dirección + confianza)
y EMITE la señal. NO coloca órdenes: el humano decide y opera. Registra el resultado
y todos los skills APRENDEN del movimiento real.

Diseño agnóstico al feed:
  - `procesar(df)` → analiza el DataFrame OHLC actual y devuelve la señal.
  - `aprender(real_direction)` → alimenta el aprendizaje con el resultado real.
  - `run_replay(df)` → recorre un histórico vela a vela (para probar sin red).
  - `run_live(ssid, asset, period)` → conecta al feed real por websocket.

Persistencia: pesos en `memoria/skill_weights.json`; snapshot para el dashboard en
`dashboards/estado.json`.
"""
import json
import os

from bot.skills.base_skill import NEUTRAL, CALL, PUT
from bot.skills.skill_manager import SkillManager
from bot.skills.skill_reversion import SkillReversion
from bot.skills.skill_momentum import SkillMomentum
from bot.skills.skill_regime import SkillMarketRegime
from bot.skills.skill_online_ml import SkillOnlineML

ESTADO_PATH = "dashboards/estado.json"
CONF_MIN = 0.55                 # confianza mínima del consenso para emitir señal


def crear_manager(weights_path="memoria/skill_weights.json"):
    """SkillManager con TODOS los skills registrados."""
    m = SkillManager(weights_path=weights_path)
    m.register_skill(SkillReversion())
    m.register_skill(SkillMomentum())
    m.register_skill(SkillMarketRegime())
    m.register_skill(SkillOnlineML())
    return m


class PocketOptionRealBot:
    def __init__(self, pair="EURUSD", timeframe=60, conf_min=CONF_MIN,
                 weights_path="memoria/skill_weights.json", on_signal=None,
                 estado_path=ESTADO_PATH):
        self.pair = pair
        self.timeframe = timeframe
        self.conf_min = conf_min
        self.manager = crear_manager(weights_path)
        self.on_signal = on_signal            # callback(signal_dict) para emitir
        self.estado_path = estado_path
        self.ultima = None                    # última señal pendiente de resultado
        self.total = 0
        self.aciertos = 0

    # --- núcleo ---
    def procesar(self, df):
        """Analiza el DataFrame OHLC hasta ahora y devuelve/emite la señal."""
        md = {"df": df, "pair": self.pair, "timeframe": self.timeframe}
        cons = self.manager.get_consensus(md)
        operar = cons["direction"] != NEUTRAL and cons["confidence"] >= self.conf_min
        señal = {
            "pair": self.pair, "timeframe": self.timeframe,
            "direccion": cons["direction"], "confianza": round(cons["confidence"], 3),
            "emitir": operar, "detalle": cons["details"],
            "precio": float(df["close"].iloc[-1]) if len(df) else None,
        }
        self.ultima = {"direccion": cons["direction"], "detalle": cons["details"],
                       "precio": señal["precio"]} if operar else None
        if operar and self.on_signal:
            self.on_signal(señal)
        self._guardar_estado(señal)
        return señal

    def aprender(self, real_direction):
        """Alimenta el aprendizaje con el resultado real de la última señal emitida."""
        if not self.ultima or real_direction not in (CALL, PUT):
            return
        acerto = self.ultima["direccion"] == real_direction
        self.total += 1
        self.aciertos += int(acerto)
        self.manager.registrar_win(acerto)
        self.manager.update_weights(real_direction, self.ultima["detalle"])
        self.manager.save_state()
        self.ultima = None

    def win_rate(self):
        return (self.aciertos / self.total * 100) if self.total else 0.0

    # --- dashboard ---
    def _guardar_estado(self, señal):
        try:
            os.makedirs(os.path.dirname(self.estado_path) or ".", exist_ok=True)
            estado = {
                "pair": self.pair, "señal": señal,
                "stats": self.manager.stats(),
                "win_rate_bot": round(self.win_rate(), 1),
                "operaciones": self.total,
            }
            with open(self.estado_path, "w", encoding="utf-8") as f:
                json.dump(estado, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # --- modos de ejecución ---
    def run_replay(self, df, expiry=1, warmup=60):
        """
        Recorre un histórico vela a vela: en cada punto genera señal y aprende del
        resultado real a `expiry` velas. Sirve para probar el bot SIN red y ver cómo
        se comporta y aprende. Devuelve resumen.
        """
        df = df.sort_values("timestamp").reset_index(drop=True)
        close = df["close"].astype(float).to_numpy()
        n = len(df)
        emitidas = 0
        for i in range(warmup, n - expiry):
            sub = df.iloc[max(0, i - 60):i + 1]
            s = self.procesar(sub)
            if not s["emitir"]:
                continue
            emitidas += 1
            real = CALL if close[i + expiry] > close[i] else (
                PUT if close[i + expiry] < close[i] else None)
            if real:
                self.aprender(real)
        return {"pair": self.pair, "señales_emitidas": emitidas,
                "operaciones_resueltas": self.total, "win_rate": round(self.win_rate(), 1),
                "pesos": self.manager.stats()["weights"]}

    async def run_live(self, ssid, asset=None, period=None):
        """
        Conecta al feed REAL de Pocket Option por websocket (solo lectura) y emite
        señales al cerrar cada vela. NO coloca órdenes. Requiere SSID de la cuenta.
        """
        from bot.candles import CandleBuilder
        from bot.pocket_client import PocketOptionClient

        asset = asset or self.pair
        period = period or self.timeframe
        builder = CandleBuilder(period)
        estado = {"ultimo_cierre": None}

        def on_tick(price, ts_ms):
            builder.add_tick(price, ts_ms)
            cerradas = builder.closed_candles()
            if not cerradas:
                return
            ultimo = cerradas[-1]["start"] if "start" in cerradas[-1] else len(cerradas)
            if estado["ultimo_cierre"] == ultimo:
                return
            estado["ultimo_cierre"] = ultimo
            df = builder.to_dataframe(include_forming=False)
            if len(df) >= 60:
                # Aprender del resultado de la señal anterior (vela ya cerrada).
                if self.ultima is not None:
                    prev = self.ultima["precio"]
                    now = float(df["close"].iloc[-1])
                    if prev is not None and now != prev:
                        self.aprender(CALL if now > prev else PUT)
                self.procesar(df)

        client = PocketOptionClient(ssid, on_tick=on_tick)
        await client.run(asset=asset, period=period)
