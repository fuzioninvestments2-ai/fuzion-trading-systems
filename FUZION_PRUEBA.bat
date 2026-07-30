@echo off
REM ============================================================
REM  FUZION_PRUEBA.bat  -  MODO PRUEBA (solo para VER que manda
REM  tarjetas). Pago minimo BAJO y pares JPY (los que mas se
REM  mueven), asi salen senales rapido para ganar confianza.
REM
REM  IMPORTANTE: esto NO es para operar en serio (pago bajo =
REM  mala ventaja). Para operar en serio usa FUZION_MATRIZ.bat.
REM  NO tener las dos ventanas abiertas a la vez (mismo SSID).
REM ============================================================
title FUZION FX - PRUEBA (pago bajo, solo para VER tarjetas)
cd /d "%~dp0"

echo.
echo   1) Trayendo la ultima version (git pull)...
git pull

echo.
echo   2) MODO PRUEBA: pares JPY y pago minimo 30%% (para ver senales).
echo      NO operar en serio con esto. Para apagar: cierra esta ventana.
echo.
python -m bot.robot_reversion REAL CHFJPY AUDJPY EURJPY GBPJPY CADJPY --tiempos 1,2,3,5 --pago 30

echo.
echo ============================================================
echo   La prueba se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
