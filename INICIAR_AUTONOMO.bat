@echo off
REM ============================================================
REM  INICIAR_AUTONOMO.bat  -  Doble clic para ACTUALIZAR y ARRANCAR
REM  el MOTOR AUTONOMO del mercado REAL (FX). El bot trabaja SOLO:
REM  lee las 4 temporalidades juntas y te avisa por Telegram cuando
REM  hay OPERAR. Demo, solo lectura, nunca coloca ordenes.
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
python -m bot.motor_autonomo REAL TODOS

echo.
echo ============================================================
echo   El motor se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
