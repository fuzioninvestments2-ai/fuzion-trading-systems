"""
bot/signal_menu.py
==================
Lógica del MENÚ INTERACTIVO de señales (botones), estilo Dewbot/Baloo.

Flujo: mercado -> activo -> tiempo -> "Start Analysis" -> señal (UP/DOWN + motivo).

Está SEPARADO de Telegram (SRP + testabilidad): aquí solo se decide qué texto y
qué botones mostrar en cada paso, y cómo se produce el análisis. La capa de red
(telegram_signals.py) traduce esto a botones reales de Telegram.

⚠️ HONESTIDAD: por ahora los precios son SIMULADOS (el motor no está conectado a
Pocket Option todavía). El análisis es real sobre datos simulados; cuando
conectemos el feed real, la misma interfaz servirá sin cambios.
"""

import math
import random
import time

from bot.config import TradingConfig
from bot.candles import CandleBuilder
from bot.scoring_strategy import ScoringStrategy, CALL, PUT, HOLD

# Mercados y activos de Pocket Option (lista amplia y estándar).
# NOTA: la disponibilidad exacta varía por día/país/hora. Los OTC funcionan 24/7.
MARKETS = {
    "otc": {"label": "🔄 OTC Market (Forex)", "assets": [
        # Majors OTC
        "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "USD/CHF OTC",
        "USD/CAD OTC", "AUD/USD OTC", "NZD/USD OTC",
        # Crosses OTC
        "EUR/GBP OTC", "EUR/JPY OTC", "EUR/CHF OTC", "EUR/CAD OTC",
        "EUR/AUD OTC", "EUR/NZD OTC", "GBP/JPY OTC", "GBP/AUD OTC",
        "GBP/CAD OTC", "GBP/CHF OTC", "AUD/JPY OTC", "AUD/CAD OTC",
        "AUD/CHF OTC", "AUD/NZD OTC", "CAD/JPY OTC", "CAD/CHF OTC",
        "CHF/JPY OTC", "NZD/JPY OTC", "NZD/CAD OTC",
        # Exóticos OTC (típicos de Pocket Option)
        "USD/INR OTC", "USD/EGP OTC", "USD/BRL OTC", "USD/PKR OTC",
        "USD/BDT OTC", "USD/NGN OTC", "USD/ARS OTC", "USD/COP OTC",
        "USD/PHP OTC", "USD/IDR OTC", "USD/MXN OTC", "USD/DZD OTC",
        "USD/CLP OTC", "USD/THB OTC", "USD/MYR OTC", "USD/SGD OTC",
        "USD/CNH OTC", "USD/TRY OTC", "MAD/USD OTC", "ZAR/USD OTC",
        "KES/USD OTC", "TND/USD OTC", "YER/USD OTC", "JOD/USD OTC",
        "LBP/USD OTC", "BHD/CNY OTC", "OMR/CNY OTC", "AED/CNY OTC",
        "SAR/CNY OTC", "QAR/CNY OTC"]},
    "real": {"label": "🌐 Real Market (Forex)", "assets": [
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD", "AUD/USD",
        "NZD/USD", "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/CAD", "EUR/AUD",
        "GBP/JPY", "GBP/AUD", "GBP/CAD", "GBP/CHF", "AUD/JPY", "AUD/CAD",
        "AUD/NZD", "CAD/JPY", "CHF/JPY", "NZD/JPY"]},
    "crypto": {"label": "💎 Cryptocurrencies", "assets": [
        "Bitcoin OTC", "Ethereum OTC", "Litecoin OTC", "Ripple OTC",
        "Bitcoin Cash OTC", "Dogecoin OTC", "Cardano OTC", "Polkadot OTC",
        "Chainlink OTC", "Solana OTC", "TRON OTC", "BNB OTC",
        "Avalanche OTC", "Polygon OTC", "Stellar OTC", "Monero OTC",
        "EOS OTC", "Dash OTC", "Toncoin OTC", "Shiba Inu OTC"]},
    "stocks": {"label": "📈 Stocks OTC", "assets": [
        "Apple OTC", "Tesla OTC", "Microsoft OTC", "Amazon OTC",
        "Alphabet (Google) OTC", "Meta OTC", "Netflix OTC", "Nvidia OTC",
        "Intel OTC", "AMD OTC", "McDonald's OTC", "Coca-Cola OTC",
        "Pfizer OTC", "Johnson & Johnson OTC", "Boeing OTC", "Visa OTC",
        "Mastercard OTC", "American Express OTC", "Citigroup OTC",
        "JPMorgan OTC", "Alibaba OTC", "Baidu OTC", "Snapchat OTC",
        "Ford OTC", "FedEx OTC", "Twitter (X) OTC"]},
    "commodities": {"label": "🛢️ Commodities OTC", "assets": [
        "Gold OTC", "Silver OTC", "Platinum OTC", "Palladium OTC",
        "Brent Oil OTC", "WTI Crude Oil OTC", "Natural Gas OTC"]},
    "indices": {"label": "📊 Indices OTC", "assets": [
        "US 500 OTC", "US 30 OTC", "US 100 OTC", "Germany 30 OTC",
        "UK 100 OTC", "Japan 225 OTC", "Euro 50 OTC", "France 40 OTC",
        "Australia 200 OTC", "Hong Kong 33 OTC"]},
}

TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1"]


def _simulate_candles(asset, timeframe, n=260):
    """
    Genera velas SIMULADAS para un activo/tiempo. La semilla depende del activo,
    el tiempo y el minuto actual, así el "análisis" cambia con el tiempo y da
    resultados distintos por activo (se siente vivo). NO es Pocket Option.
    """
    seed = abs(hash((asset, timeframe, int(time.time() // 60)))) % (2 ** 31)
    rng = random.Random(seed)
    cb = CandleBuilder(60)
    price = 100.0 + rng.uniform(-5, 5)
    drift = rng.uniform(-0.03, 0.03)        # ligera tendencia aleatoria
    ts = 0
    for _ in range(n * 3):                  # 3 ticks por vela
        price += drift + rng.uniform(-0.4, 0.4)
        cb.add_tick(price, ts)
        ts += 20_000
    return cb.to_dataframe()


def _reason_from_votes(votes, side):
    """Arma un texto legible con los indicadores que apoyan la dirección."""
    nombres = {"rsi": "RSI", "macd": "MACD", "bollinger": "Bollinger",
               "moving_averages": "Medias móviles", "stochastic": "Estocástico"}
    apoyan = [nombres[k] for k, v in votes.items() if v == side]
    if not apoyan:
        return "sin confluencia clara de indicadores"
    return ", ".join(apoyan)


class SignalMenu:
    """
    Controlador del menú. Mantiene el estado de cada usuario (qué eligió) y
    produce (texto, botones). `botones` es una lista de FILAS; cada fila es una
    lista de tuplas (etiqueta, dato_callback).
    """

    def __init__(self):
        self._state = {}       # user_id -> {"market","asset","timeframe"}

    def _st(self, user_id):
        return self._state.setdefault(user_id, {})

    # --- Pantallas ---

    def main_menu(self):
        text = "📊 *Elige el tipo de mercado:*"
        rows = [[(m["label"], f"market:{key}")] for key, m in MARKETS.items()]
        return text, rows

    def market_menu(self, user_id, market_key):
        if market_key not in MARKETS:
            return self.main_menu()
        self._st(user_id)["market"] = market_key
        self._st(user_id).pop("asset", None)
        assets = MARKETS[market_key]["assets"]
        # Tres activos por fila -> se ve más "cuadrado" y compacto.
        rows = []
        for i in range(0, len(assets), 3):
            fila = [(a, f"asset:{a}") for a in assets[i:i + 3]]
            rows.append(fila)
        rows.append([("⬅️ Volver", "back:main")])
        return f"Mercado: *{MARKETS[market_key]['label']}*\nAhora elige el activo:", rows

    def asset_menu(self, user_id, asset):
        self._st(user_id)["asset"] = asset
        rows = []
        # Tiempos en filas de 3.
        for i in range(0, len(TIMEFRAMES), 3):
            fila = [(tf, f"tf:{tf}") for tf in TIMEFRAMES[i:i + 3]]
            rows.append(fila)
        rows.append([("⬅️ Volver", "back:market")])
        return f"Activo: *{asset}*\nElige el tiempo de expiración:", rows

    def timeframe_menu(self, user_id, tf):
        self._st(user_id)["timeframe"] = tf
        st = self._st(user_id)
        text = (f"Activo: *{st.get('asset')}*\nTiempo: *{tf}*\n\n"
                f"Pulsa para analizar:")
        rows = [[("🚀 Start Analysis", "analyze")],
                [("⬅️ Volver", "back:asset")]]
        return text, rows

    def analyze(self, user_id):
        """Ejecuta el análisis y devuelve (texto_señal, botones)."""
        st = self._st(user_id)
        asset, tf = st.get("asset"), st.get("timeframe")
        if not asset or not tf:
            return "Primero elige mercado, activo y tiempo.", [[("⬅️ Menú", "back:main")]]

        df = _simulate_candles(asset, tf)
        # En modo manual bajamos algo la exigencia para dar una dirección.
        cfg = TradingConfig(stack_method="aggressive")
        cfg.min_confidence = 0.25
        _, _, d = ScoringStrategy(cfg).analyze(df)

        call_s, put_s = d.get("call_score", 0), d.get("put_score", 0)
        conf = d.get("confidence", 0)
        votes = d.get("votes", {})

        if call_s > put_s:
            direccion, side = "⬆️ *UP* (CALL)", CALL
        elif put_s > call_s:
            direccion, side = "⬇️ *DOWN* (PUT)", PUT
        else:
            direccion, side = "⏸️ *Sin señal clara* (espera)", HOLD

        motivo = _reason_from_votes(votes, side) if side != HOLD else \
            "los indicadores no coinciden"

        text = (f"📈 *{asset}*  |  ⏱️ *{tf}*\n"
                f"Dirección: {direccion}\n"
                f"Confianza: *{conf:.0%}*\n"
                f"Motivo: {motivo}\n\n"
                f"⚠️ _Datos SIMULADOS (aún no conectado a Pocket Option). "
                f"No es una recomendación; ningún bot acierta siempre._")
        rows = [[("🔁 Analizar de nuevo", "analyze")],
                [("📊 Otro activo", "back:market"), ("🏠 Menú", "back:main")]]
        return text, rows

    # --- Enrutador de botones ---

    def handle_callback(self, user_id, data):
        """
        Recibe el 'dato' del botón pulsado y devuelve (texto, botones).
        """
        if data == "back:main":
            return self.main_menu()
        if data.startswith("market:"):
            return self.market_menu(user_id, data.split(":", 1)[1])
        if data == "back:market":
            key = self._st(user_id).get("market", "otc")
            return self.market_menu(user_id, key)
        if data.startswith("asset:"):
            return self.asset_menu(user_id, data.split(":", 1)[1])
        if data == "back:asset":
            return self.asset_menu(user_id, self._st(user_id).get("asset", ""))
        if data.startswith("tf:"):
            return self.timeframe_menu(user_id, data.split(":", 1)[1])
        if data == "analyze":
            return self.analyze(user_id)
        return self.main_menu()
