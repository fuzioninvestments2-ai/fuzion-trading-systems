@echo off
REM ============================================================
REM  INICIAR_RESUMEN_DIARIO.bat  -  Doble clic para arrancar el
REM  scheduler del RESUMEN DIARIO (00:00 UTC-4). Proceso aparte
REM  de los 4 bots: guarda resumenes\resumen_<bot>_FECHA.md y lo
REM  manda al Telegram de cada bot. Demo, solo lectura.
REM ============================================================
title FUZION FX - Resumen diario (00:00 UTC-4)
cd /d "%~dp0"
echo.
echo ============================================================
echo   Scheduler de resumen diario arrancado.
echo   - Genera el resumen de cada bot a las 00:00 UTC-4.
echo   - NO cierres esta ventana mientras quieras que siga.
echo   - Los .md quedan en la carpeta  resumenes\
echo ============================================================
echo.
python fuzion_fx\scripts\daily_summary_scheduler.py
pause
