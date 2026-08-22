@echo off
REM ============================================================
REM  ANALISIS_VISUAL.bat  -  Doble clic. No hay que tipear nada.
REM  Arma el PANEL VISUAL de DONDE PIERDE el bot (por setup,
REM  tiempo, par, hora y acumulado) y lo abre como imagen.
REM  Solo LEE los resultados reales; no toca el bot en vivo.
REM ============================================================
title FUZION FX - Analisis visual (donde se pierde)
cd /d "%~dp0"

echo   Trayendo la ultima version (git pull)...
git pull

echo.
echo   Armando el panel visual...
python fuzion_fx\scripts\analisis_visual.py --abrir

echo.
echo ============================================================
echo   Se guardo/abrio: fuzion_fx\data\analisis_visual.png
echo   Verde = supera break-even  ·  Rojo = pierde  ·  Gris = poca muestra
echo ============================================================
echo.
pause
