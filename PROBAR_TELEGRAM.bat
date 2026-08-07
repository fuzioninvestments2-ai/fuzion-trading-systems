@echo off
REM ============================================================
REM  PROBAR_TELEGRAM.bat  -  Manda un mensaje de prueba a los 4 bots.
REM ============================================================
title FUZION FX - Probar Telegram
cd /d "%~dp0"
echo.
echo   Enviando mensaje de prueba a los 4 bots (F1..F)...
echo.
python fuzion_fx\scripts\test_telegram.py
echo.
pause
