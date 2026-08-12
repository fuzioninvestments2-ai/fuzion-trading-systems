@echo off
REM ============================================================
REM  VIGILANTE_FUZION_FX.bat  -  Doble clic para que el sistema
REM  se cuide SOLO. Arranca lo que falte (colector + 4 bots),
REM  los vigila y REINICIA lo que se caiga o quede mudo, y avisa
REM  por Telegram. Demo, solo lectura. Cierra la ventana para parar
REM  el vigilante (los bots siguen corriendo).
REM
REM  Con esto NO hace falta INICIAR_FUZION_FX: el vigilante levanta
REM  todo y lo mantiene vivo.
REM ============================================================
title FUZION FX - Vigilante 24/7
cd /d "%~dp0"
echo.
echo ============================================================
echo   Vigilante activo: levanta y cuida colector + 4 bots.
echo   Reinicia lo que se caiga o quede mudo. Avisa por Telegram.
echo   - NO cierres esta ventana mientras quieras que vigile.
echo ============================================================
echo.
python fuzion_fx\scripts\vigilante.py
echo.
echo   Vigilante detenido. Pulsa una tecla para cerrar.
pause >nul
