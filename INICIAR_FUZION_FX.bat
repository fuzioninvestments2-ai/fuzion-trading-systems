@echo off
REM ============================================================
REM  INICIAR_FUZION_FX.bat  -  Doble clic para ARRANCAR Fuzion FX
REM  (colector + 4 bots: 1m/2m/3m/5m). Demo, solo lectura.
REM ============================================================
title FUZION FX - Colector + 4 bots
cd /d "%~dp0"
echo.
echo ============================================================
echo   Arrancando Fuzion FX: colector + 4 bots (1m/2m/3m/5m)...
echo ============================================================
echo.
python fuzion_fx\scripts\start_all.py
echo.
echo ============================================================
echo   Los 5 procesos estan corriendo en segundo plano.
echo   - NO cierres esta ventana mientras quieras que sigan.
echo   - Las senales llegaran a cada bot de Telegram (F1..F).
echo   - Para detener: doble clic en DETENER_FUZION_FX.bat
echo ============================================================
pause
