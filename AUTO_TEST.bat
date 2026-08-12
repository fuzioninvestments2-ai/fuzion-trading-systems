@echo off
REM ============================================================
REM  AUTO_TEST.bat  -  Doble clic. Actualiza y verifica que el
REM  bot este sano (corre toda la bateria de pruebas, sin red).
REM ============================================================
title FUZION FX - Auto verificacion
cd /d "%~dp0"

echo.
echo   Trayendo la ultima version (git pull)...
git pull

echo.
echo ============================================================
python fuzion_fx\scripts\autotest.py
echo ============================================================
echo.
pause
