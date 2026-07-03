@echo off
REM ============================================================
REM  ROBOT_AUTO.bat  -  Sistema CONTINUO y AUTOMATICO.
REM  Doble clic UNA vez y dejalo. Baja/refresca el historial de
REM  todos los majors OTC hacia adelante, lo sube a la nube cada
REM  ronda, y SI SE CAE se REINICIA solo. No necesitas estar.
REM
REM  IMPORTANTE:
REM   - El BOT de Telegram debe estar APAGADO (una conexion por SSID).
REM   - Tu PC debe seguir ENCENDIDA (si la apagas, se detiene).
REM   - Para parar: cierra esta ventana.
REM ============================================================
title ROBOT AUTO - Acumulador continuo Pocket Option
cd /d "%USERPROFILE%\fuzion-trading-systems"

echo.
echo ============================================================
echo   ROBOT AUTOMATICO EN MARCHA. Dejalo corriendo; se cuida solo.
echo   (BOT de Telegram APAGADO. Cierra la ventana para parar.)
echo ============================================================
echo.

:loop
echo [%date% %time%] Actualizando codigo...
git pull --no-edit

echo [%date% %time%] Arrancando acumulador (todos los majors, sube a la nube)...
python -m bot.accumulator --push

echo.
echo [%date% %time%] El acumulador se detuvo. Reinicio en 30s...
echo   (Ctrl+C ahora para salir del todo.)
timeout /t 30 /nobreak >nul
goto loop
