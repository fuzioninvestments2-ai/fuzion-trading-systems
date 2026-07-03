@echo off
REM ============================================================
REM  ACUMULADOR.bat  -  Doble clic para APILAR historial en vivo
REM  (hacia adelante) y subirlo a la nube cada ronda.
REM
REM  IMPORTANTE: el BOT de Telegram debe estar APAGADO (una sola
REM  conexion por SSID). Dejalo corriendo el tiempo que quieras;
REM  cierra la ventana (o Ctrl+C) para parar.
REM ============================================================
title Acumulador de Historial - Pocket Option OTC (en vivo)
cd /d "%USERPROFILE%\fuzion-trading-systems"

echo.
echo ============================================================
echo   ASEGURATE de que el BOT de Telegram este APAGADO.
echo   Este acumulador apila historial HACIA ADELANTE y lo sube
echo   a la nube cada ronda. Dejalo corriendo; Ctrl+C para parar.
echo   Pulsa una tecla para empezar...
echo ============================================================
pause >nul

echo.
echo   Actualizando...
git pull

echo.
echo   Acumulando (majors OTC, 5s..1d) y subiendo a la nube...
python -m bot.accumulator --push

echo.
echo ============================================================
echo   Acumulador detenido. El historial quedo guardado.
echo ============================================================
pause >nul
