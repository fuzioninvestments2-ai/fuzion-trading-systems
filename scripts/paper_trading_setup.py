#!/usr/bin/env python
"""
FUZION — Setup de Paper Trading

Verifica que todo esté configurado antes de iniciar el modo paper.
Pasos:
  1. Verifica .env con credenciales de broker
  2. Verifica conectividad con el broker seleccionado
  3. Verifica acceso a datos de mercado
  4. Lanza el servidor API en modo paper
  5. Registra la fecha de inicio (para el contador de 30 días mínimos)
"""
import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


REQUIRED_ENV = {
    "alpaca": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
    "ibkr":   [],                   # usa TWS local, no necesita API key en .env
    "bybit":  ["BYBIT_API_KEY", "BYBIT_SECRET_KEY"],
    "okx":    ["OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE"],
}

PAPER_STATE_FILE = Path("logs/paper_trading_state.json")


def check_env(broker: str) -> bool:
    missing = [k for k in REQUIRED_ENV.get(broker, []) if not os.getenv(k)]
    if missing:
        print(f"  ✗ Variables faltantes en .env: {', '.join(missing)}")
        return False
    print(f"  ✓ Variables de entorno OK para {broker}")
    return True


def check_dotenv() -> bool:
    env_file = Path(".env")
    if not env_file.exists():
        print("  ✗ .env no encontrado — ejecuta: cp .env.example .env")
        return False
    from dotenv import load_dotenv
    load_dotenv()
    print("  ✓ .env cargado")
    return True


async def check_broker(broker: str) -> bool:
    try:
        if broker == "alpaca":
            from broker.alpaca_client import AlpacaClient
            client = AlpacaClient(paper=True)
            info = await client.get_account_info()
            print(f"  ✓ Alpaca paper conectado — equity: ${info.equity:,.2f}")
            return True
        elif broker == "ibkr":
            print("  ℹ IBKR: asegúrate de que TWS esté corriendo en puerto 7497")
            return True
        elif broker == "bybit":
            from broker.bybit_client import BybitClient
            client = BybitClient(testnet=True)
            info = await client.get_account_info()
            print(f"  ✓ Bybit testnet conectado — equity: ${info.equity:,.2f}")
            return True
        else:
            print(f"  ℹ Broker '{broker}' no verificado automáticamente")
            return True
    except Exception as e:
        print(f"  ✗ Error conectando a {broker}: {e}")
        return False


def check_market_data() -> bool:
    try:
        import yfinance as yf
        ticker = yf.Ticker("SPY")
        hist = ticker.history(period="5d")
        if hist is not None and not hist.empty:
            print(f"  ✓ Datos de mercado OK — SPY último cierre: ${hist['Close'].iloc[-1]:.2f}")
            return True
        print("  ✗ No se obtuvieron datos de mercado (¿sin internet?)")
        return False
    except Exception as e:
        print(f"  ✗ Error obteniendo datos: {e}")
        return False


def record_paper_start(broker: str):
    PAPER_STATE_FILE.parent.mkdir(exist_ok=True)
    state = {}
    if PAPER_STATE_FILE.exists():
        with open(PAPER_STATE_FILE) as f:
            state = json.load(f)

    if broker not in state:
        state[broker] = {
            "start_date": datetime.utcnow().isoformat(),
            "days_elapsed": 0,
            "can_go_live": False,
        }
        with open(PAPER_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"  ✓ Inicio de paper trading registrado: {state[broker]['start_date']}")
    else:
        from datetime import datetime as dt
        start = dt.fromisoformat(state[broker]["start_date"])
        days = (dt.utcnow() - start).days
        state[broker]["days_elapsed"] = days
        state[broker]["can_go_live"] = days >= 30
        with open(PAPER_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        status = "✓ PUEDE ir a live" if days >= 30 else f"✗ Faltan {30 - days} días para poder ir a live"
        print(f"  {status} (días en paper: {days}/30)")


async def main():
    print("\n" + "="*60)
    print("  FUZION — Verificación de Paper Trading")
    print("="*60)

    broker = os.getenv("PAPER_BROKER", "alpaca").lower()
    print(f"\n[1] Broker seleccionado: {broker}")

    print("\n[2] Verificando .env...")
    if not check_dotenv():
        sys.exit(1)

    print(f"\n[3] Verificando variables de entorno para {broker}...")
    if not check_env(broker):
        print("\n  Edita .env con tus API keys antes de continuar.")
        sys.exit(1)

    print("\n[4] Verificando datos de mercado...")
    check_market_data()

    print(f"\n[5] Verificando conexión con {broker}...")
    await check_broker(broker)

    print("\n[6] Registrando estado de paper trading...")
    record_paper_start(broker)

    print("\n" + "="*60)
    print("  Para iniciar el servidor en modo paper:")
    print("  python main.py api")
    print("\n  RECUERDA: Mínimo 30 días en paper antes de ir a live.")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
