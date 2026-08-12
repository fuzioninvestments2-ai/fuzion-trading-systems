@echo off
REM ============================================================
REM  POR_QUE_NO_HAY_SENALES.bat  -  Doble clic.
REM  Actualiza el codigo y dice, en claro, POR QUE el bot no
REM  esta enviando senales (velas, pagos, pausa, motor).
REM  Corre con el sistema PRENDIDO (no lo apaga, solo lee).
REM ============================================================
title FUZION FX - Por que no hay senales
cd /d "%~dp0"

echo.
echo   Trayendo la ultima version (git pull)...
git pull

echo.
echo ============================================================
python fuzion_fx\scripts\por_que_no_hay_senales.py
echo ============================================================
echo.
echo   Copia y pegame la seccion "4) PAGOS" para aplicar el
echo   ajuste exacto. Pulsa una tecla para cerrar.
pause >nul
