@echo off
REM ============================================================
REM  INICIAR_ROBOT_REAL.bat  -  Robot de REVERSION (Fuzion FX).
REM  Doble clic: actualiza y arranca el vigilante en vivo.
REM  Vigila los pares fuertes, detecta el pico y te avisa por
REM  Telegram (@FuZionFzbot) cuando hay reversion con ventaja.
REM
REM  Necesita en esta carpeta:
REM   - ssid_real.txt          (tu sesion de Pocket Option demo)
REM   - .env con TELEGRAM_BOT_TOKEN_REAL=...   (token del bot)
REM  Y haber mandado un mensaje al bot en Telegram una vez.
REM
REM  NO lo corras a la vez que INICIAR_REAL.bat si comparten el
REM  mismo ssid_real.txt (Pocket Option rechaza doble conexion).
REM ============================================================
title Fuzion FX - Robot de reversion (mercado REAL)
cd /d "%~dp0"

echo.
echo   1) Trayendo la ultima version (git pull)...
git pull

echo.
echo   2) Arrancando el robot de reversion... (para apagarlo: cierra esta ventana)
echo.
python -m bot.robot_reversion REAL

echo.
echo ============================================================
echo   El robot se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
