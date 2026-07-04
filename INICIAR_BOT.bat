@echo off
REM ============================================================
REM  INICIAR_BOT.bat  —  Doble clic para ACTUALIZAR y ARRANCAR
REM  el bot de senales de Pocket Option OTC (Telegram).
REM  No necesitas escribir ni pegar nada: solo doble clic.
REM ============================================================
title Bot de Senales - Pocket Option OTC
cd /d "%~dp0"

echo.
echo ============================================================
echo   1) Trayendo la ultima version (git pull)...
echo ============================================================
git pull

echo.
echo ============================================================
echo   2) Arrancando el bot... (para apagarlo: cierra esta ventana)
echo ============================================================
echo.
python -m bot.telegram_signals

echo.
echo ============================================================
echo   El bot se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
