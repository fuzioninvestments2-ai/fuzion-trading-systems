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
cd /d "%~dp0"

echo.
echo ============================================================
echo   ROBOT AUTOMATICO EN MARCHA. Dejalo corriendo; se cuida solo.
echo   (BOT de Telegram APAGADO. Cierra la ventana para parar.)
echo ============================================================
echo.

:loop
echo [%date% %time%] Actualizando codigo...
git pull --no-edit

echo.
echo [%date% %time%] FASE 1: descarga PROFUNDA 5s..1d de TODOS los OTC (de 5 en 5).
echo   Reanudable: salta los que ya esten completos. Sube a la nube al final.
python -m bot.download_history --all --batch 5
python -m bot.dataset_export export OTC
python -m bot.cloud_push "datasets/otc" "datos OTC: descarga profunda 5s-1d"

echo.
echo [%date% %time%] FASE 2: acumular hacia adelante y subir cada ronda...
python -m bot.accumulator --push

echo.
echo [%date% %time%] El robot se detuvo. Reinicio en 30s...
echo   (Ctrl+C ahora para salir del todo.)
timeout /t 30 /nobreak >nul
goto loop
