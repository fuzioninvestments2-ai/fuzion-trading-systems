@echo off
REM ============================================================
REM  VEREDICTO_REAL.bat  -  Doble clic. No hay que tipear nada.
REM  Corre el VEREDICTO HONESTO sobre tu historial real (23 anios):
REM    1) ML de direccion (validacion dura, ROI con tu pago real).
REM    2) Edge de reversion 5m/Cierre (Bonferroni + anio x anio + par x par).
REM  Guarda todo en VEREDICTO_REAL.txt (se abre solo en Notepad) y
REM  lo muestra en pantalla. Solo LEE datos; no toca el bot en vivo.
REM ============================================================
title FUZION FX - Veredicto honesto (historial real)
cd /d "%~dp0"
set SALIDA=%~dp0VEREDICTO_REAL.txt

echo   Trayendo la ultima version (git pull)...
git pull

echo. > "%SALIDA%"
echo ============================================================ >> "%SALIDA%"
echo   VEREDICTO REAL - generado por VEREDICTO_REAL.bat >> "%SALIDA%"
echo ============================================================ >> "%SALIDA%"

echo. >> "%SALIDA%"
echo   [1] MOTOR / ML DE DIRECCION (el enfoque del bot en vivo) >> "%SALIDA%"
echo   ------------------------------------------------------------ >> "%SALIDA%"
python fuzion_fx\scripts\ml_direccion.py >> "%SALIDA%" 2>&1

echo. >> "%SALIDA%"
echo   [2] EDGE DE REVERSION 5m / sesion CIERRE (validacion dura) >> "%SALIDA%"
echo   ------------------------------------------------------------ >> "%SALIDA%"
python -m bot.validar_edge >> "%SALIDA%" 2>&1

echo.
type "%SALIDA%"
echo.
echo ============================================================
echo   Se guardo en VEREDICTO_REAL.txt (se abre ahora en Notepad).
echo   Copia de ahi las lineas finales de cada bloque y pegamelas.
echo ============================================================
start "" notepad "%SALIDA%"
echo.
pause >nul
