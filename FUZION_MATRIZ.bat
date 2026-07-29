@echo off
REM ============================================================
REM  FUZION_MATRIZ.bat  -  La MATRIZ (una mente, 4 tiempos).
REM  UNA conexion a Pocket Option que emite los 4 bots por
REM  tiempo a la vez: FUZION FX 1M / 2M / 3M / 5M.
REM  Cada senal llega con su nombre, su acierto y su hora.
REM
REM  Necesita: ssid_real.txt  y  .env con TELEGRAM_BOT_TOKEN_REAL
REM  y TELEGRAM_CHAT_ID_REAL (ya configurados).
REM  NO abrir a la vez otro bot con el mismo ssid_real.txt.
REM ============================================================
title FUZION FX - MATRIZ (1m/2m/3m/5m)
cd /d "%~dp0"

echo.
echo   1) Trayendo la ultima version (git pull)...
git pull

echo.
echo   2) Arrancando la MATRIZ (4 tiempos)... (para apagar: cierra esta ventana)
echo.
python -m bot.robot_reversion REAL --tiempos 1,2,3,5 --pago 72

echo.
echo ============================================================
echo   La matriz se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
