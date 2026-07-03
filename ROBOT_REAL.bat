@echo off
REM ============================================================
REM  ROBOT_REAL.bat  -  Mercado REAL en PARALELO (yfinance).
REM  Doble clic y dejalo en SU PROPIA ventana. Baja el historial
REM  REAL (forex, oro, plata, BTC, ETH: 2+ anos), exporta y lo
REM  sube a la nube; luego espera 1 hora y repite.
REM
REM  NO usa Pocket Option: es HTTP normal. Por eso puede correr
REM  A LA VEZ que ROBOT_AUTO (OTC) sin pelearse por el SSID.
REM  Para parar: cierra esta ventana.
REM ============================================================
title ROBOT REAL - Mercado real (yfinance) en paralelo
cd /d "%USERPROFILE%\fuzion-trading-systems"

echo.
echo ============================================================
echo   ROBOT REAL EN MARCHA (paralelo al OTC). Se cuida solo.
echo   Cierra la ventana para parar.
echo ============================================================
echo.

:loop
echo [%date% %time%] Actualizando codigo...
git pull --no-edit
python -m pip install yfinance >nul 2>&1

echo [%date% %time%] Descargando historial REAL (2+ anos) ...
python -m bot.historical_loader

echo [%date% %time%] Exportando y subiendo a la nube ...
python -m bot.dataset_export export
git add datasets/ & git commit -m "datos: historial REAL (yfinance)" & git push

echo.
echo [%date% %time%] Listo. Siguiente actualizacion en 1 hora...
echo   (Ctrl+C ahora para salir del todo.)
timeout /t 3600 /nobreak >nul
goto loop
