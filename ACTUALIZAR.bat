@echo off
REM ============================================================
REM  ACTUALIZAR.bat  -  UN SOLO doble clic:
REM    1) Baja la ultima version (forzado, sin trabarse).
REM    2) Apaga lo viejo.
REM    3) Arranca todo limpio (colector + 4 bots + panel).
REM  No hay que pegar nada en PowerShell. Este es EL boton.
REM ============================================================
title FUZION FX - Actualizar y arrancar
cd /d "%~dp0"
set RAMA=claude/junior-dev-supervision-2wle9i

echo.
echo   1) Bajando la ultima version...
git fetch origin %RAMA%
git reset --hard origin/%RAMA%
echo.
echo   Version cargada:
git log --oneline -1
echo.

echo   2) Apagando lo viejo...
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM python.exe  >nul 2>&1
timeout /t 2 >nul

echo   3) Arrancando limpio...
wscript "%~dp0FUZION.vbs"

echo.
echo ============================================================
echo   LISTO. En 2-3 minutos empiezan a llegar las senales a
echo   Telegram (de a una, con su tarjeta completa).
echo ============================================================
echo.
pause
