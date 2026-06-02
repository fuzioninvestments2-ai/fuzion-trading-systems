#!/bin/bash
# FUZION — Inicia el sistema en modo paper trading
# Uso: ./scripts/start_paper_trading.sh [--broker alpaca|ibkr|bybit|okx]

set -e

BROKER=${2:-alpaca}
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== FUZION Paper Trading ==="
echo "Broker: $BROKER"
echo "Directorio: $ROOT_DIR"

# Cargar .env si existe
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

export PAPER_BROKER=$BROKER
export PAPER_TRADING=true

# Verificar setup
python scripts/paper_trading_setup.py

# Crear directorios necesarios
mkdir -p logs models results cache

# Iniciar servidor API
echo ""
echo "Iniciando servidor API en modo paper..."
echo "Puerto: 8000 | Docs: http://localhost:8000/docs"
echo ""
python main.py api
