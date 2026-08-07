@echo off
REM ============================================================
REM  ESTADO_FUZION_FX.bat  -  Ver si corren + cuantas velas hay.
REM ============================================================
title FUZION FX - Estado
cd /d "%~dp0"
echo.
echo ===================  PROCESOS  ==============================
python fuzion_fx\scripts\check_status.py
echo.
echo ===================  VELAS  =================================
python fuzion_fx\scripts\check_candles.py
echo.
pause
