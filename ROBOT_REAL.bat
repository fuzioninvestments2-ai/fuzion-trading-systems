@echo off
REM ============================================================
REM  ROBOT_REAL.bat  -  Robot del MERCADO REAL, SINCRONIZADO con
REM  el horario. Doble clic UNA vez y dejalo (desde ya):
REM   - SIEMPRE: refresca la base de anos (yfinance) y sube a la nube.
REM   - CUANDO ABRE el mercado (domingo noche): ademas baja 5s..1d
REM     desde Pocket Option (segunda cuenta / ssid_real.txt).
REM   - CUANDO CERRADO (finde): salta la parte de PO, solo yfinance.
REM
REM  Asi queda ARMADO: lo enciendes hoy y el solo empieza el domingo.
REM
REM  IMPORTANTE: la parte de PO usa tu SEGUNDA cuenta (ssid_real.txt).
REM  No tengas Fuzion FX (senales) encendido a la vez que este robot
REM  baja de PO: son la misma cuenta. Para parar: cierra la ventana.
REM ============================================================
title ROBOT REAL - Mercado real sincronizado (yfinance + PO)
cd /d "%USERPROFILE%\fuzion-trading-systems"

echo.
echo ============================================================
echo   ROBOT REAL ARMADO. Se cuida solo y arranca cuando abra el
echo   mercado (domingo noche). Cierra la ventana para parar.
echo ============================================================
echo.

:loop
echo [%date% %time%] Actualizando codigo...
git pull --no-edit
python -m pip install yfinance >nul 2>&1

echo [%date% %time%] Base de anos (yfinance): 1m..1d...
python -m bot.historical_loader

echo [%date% %time%] Comprobando si el mercado real esta ABIERTO...
python -c "import sys; from bot.market_hours import is_open; sys.exit(0 if is_open('EURUSD')[0] else 1)"
if %errorlevel%==0 (
  echo [%date% %time%] ABIERTO: bajando 5s..1d desde Pocket Option...
  python -m bot.download_history --real
) else (
  echo [%date% %time%] CERRADO: hoy solo yfinance. El domingo empieza PO solo.
)

echo [%date% %time%] Exportando y subiendo a la nube (datasets/real)...
python -m bot.dataset_export export REAL
git add datasets/real & git commit -m "datos REAL: historial sincronizado" & git pull --no-rebase --no-edit & git push

echo.
echo [%date% %time%] Ronda lista. Siguiente en 1 hora...
echo   (Ctrl+C ahora para salir del todo.)
timeout /t 3600 /nobreak >nul
goto loop
