#!/bin/bash
echo "=== FUZION Trading Systems — Setup ==="
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
cp config/credentials.yaml.example config/credentials.yaml 2>/dev/null || true
mkdir -p logs models results cache
echo "=== Setup completado ==="
echo "Edita .env con tus credenciales antes de continuar."
echo "Para iniciar el servidor: python main.py api"
echo "Para backtest:            python scripts/run_backtest.py --symbol SPY"
