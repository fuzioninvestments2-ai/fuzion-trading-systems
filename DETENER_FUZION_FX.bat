@echo off
REM ============================================================
REM  DETENER_FUZION_FX.bat  -  Doble clic para APAGAR todo.
REM ============================================================
title FUZION FX - Detener
cd /d "%~dp0"
echo.
echo   Deteniendo colector + 4 bots...
echo.
python fuzion_fx\scripts\stop_all.py
echo.
pause
