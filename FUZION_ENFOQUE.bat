@echo off
REM ============================================================
REM  FUZION_ENFOQUE.bat  -  REACCION EN TIEMPO REAL.
REM  Vigila POCOS pares (aqui 3) SIN quedar ciego: al no rotar
REM  entre 18, cada cierre de vela se detecta al instante y la
REM  hora de entrada es exacta (milisegundos de reaccion).
REM
REM  EL PORQUE: Pocket Option deja UNA conexion mirando UN par a
REM  la vez. Con muchos pares hay rotacion = retraso. Con pocos
REM  pares, reaccion real. La velocidad se paga con cobertura.
REM
REM  Cambia los 3 pares por los que TU operas.
REM ============================================================
title FUZION FX - ENFOQUE (tiempo real, pocos pares)
cd /d "%~dp0"

echo.
echo   1) Trayendo la ultima version (git pull)...
git pull

echo.
echo   2) ENFOQUE en tiempo real: EURCHF AUDCAD EURGBP (cambialos si quieres).
echo      Reaccion al instante y hora exacta. Para apagar: cierra esta ventana.
echo.
python -m bot.robot_reversion REAL EURCHF AUDCAD EURGBP --tiempos 1,2,3,5 --pago 72

echo.
echo ============================================================
echo   El enfoque se detuvo. Pulsa una tecla para cerrar.
echo ============================================================
pause >nul
