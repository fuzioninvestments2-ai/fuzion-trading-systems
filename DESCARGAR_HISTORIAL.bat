@echo off
REM ============================================================
REM  DESCARGAR_HISTORIAL.bat  -  Doble clic para bajar el
REM  historial MASIVO (rapido, en bloque). NO por Telegram.
REM
REM  IMPORTANTE: el BOT debe estar APAGADO al correr esto
REM  (esta descarga abre su propia conexion; no puede haber
REM   dos con el mismo SSID a la vez).
REM ============================================================
title Descargar Historial - Pocket Option OTC + FX
cd /d "%USERPROFILE%\fuzion-trading-systems"

echo.
echo ============================================================
echo   ASEGURATE de que el BOT este APAGADO (cierra su ventana).
echo   Pulsa una tecla para empezar la descarga...
echo ============================================================
pause >nul

echo.
echo   1) Actualizando y preparando librerias...
git pull
python -m pip install BinaryOptionsToolsV2 yfinance >nul 2>&1

echo.
echo   2) Descargando historial OTC en bloque (rapido)...
python -m bot.po_history_downloader

echo.
echo   3) Descargando historial REAL (FX) de los pares mayores...
python -m bot.historical_loader EURUSD GBPUSD USDJPY AUDUSD USDCAD XAUUSD

echo.
echo ============================================================
echo   LISTO. El historial quedo guardado en history.db
echo   Ahora arranca el bot con INICIAR_BOT (doble clic).
echo ============================================================
pause >nul
