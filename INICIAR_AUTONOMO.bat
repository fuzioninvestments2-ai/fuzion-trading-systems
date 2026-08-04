@echo off
REM ============================================================
REM  INICIAR_AUTONOMO.bat  -  Doble clic para ACTUALIZAR y ARRANCAR
REM  el BOT AUTONOMO del mercado REAL (FX). El bot trabaja SOLO en las
REM  4 temporalidades (1/2/3/5 min) y te manda por Telegram la tarjeta
REM  con GRAFICO (divisa, direccion, hora de entrada, vence, pago,
REM  acierto historico y pico). Demo, solo lectura, nunca coloca ordenes.
REM  No necesitas escribir nada: solo doble clic.
REM ============================================================
title FUZION FX - Motor Autonomo (REAL)
cd /d "%~dp0"

echo.
echo ============================================================
echo   1) Trayendo la ultima version (git pull)...
echo ============================================================
git pull

echo.
echo ============================================================
echo   2) Arrancando el motor autonomo... (para apagarlo: cierra
echo      esta ventana o pulsa Ctrl + C)
echo ============================================================
echo.
set PYTHONPATH=.
python -m bot.robot_reversion REAL TODOS --tiempos 1,2,3,5

echo.
echo ============================================================
echo   El motor se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
