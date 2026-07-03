@echo off
REM ============================================================
REM  INICIAR_OTC.bat  -  Bot "Fuzion OTC" (mercado OTC 24/7).
REM  Doble clic para actualizar y arrancar. Telegram e historial
REM  PROPIOS (separado del bot real, sin cruces).
REM  Token en .env:  TELEGRAM_BOT_TOKEN_OTC=...
REM ============================================================
title Fuzion OTC - Bot de senales (mercado OTC)
cd /d "%USERPROFILE%\fuzion-trading-systems"

echo.
echo   1) Trayendo la ultima version (git pull)...
git pull

echo.
echo   2) Arrancando Fuzion OTC... (para apagarlo: cierra esta ventana)
echo.
python -m bot.telegram_signals OTC

echo.
echo ============================================================
echo   Fuzion OTC se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
