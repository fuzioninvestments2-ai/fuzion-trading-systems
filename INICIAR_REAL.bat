@echo off
REM ============================================================
REM  INICIAR_REAL.bat  -  Bot "Fuzion FX" (mercado REAL Forex).
REM  Doble clic para actualizar y arrancar. Telegram e historial
REM  PROPIOS (separado del bot OTC, sin cruces).
REM  Token en .env:  TELEGRAM_BOT_TOKEN_REAL=...
REM  Solo monedas (Lun-Vie); calla en noticias de alto impacto.
REM ============================================================
title Fuzion FX - Bot de senales (mercado REAL Forex)
cd /d "%~dp0"

echo.
echo   1) Trayendo la ultima version (git pull)...
git pull

echo.
echo   2) Arrancando Fuzion FX... (para apagarlo: cierra esta ventana)
echo.
python -m bot.telegram_signals REAL

echo.
echo ============================================================
echo   Fuzion FX se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
