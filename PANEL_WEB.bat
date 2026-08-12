@echo off
REM ============================================================
REM  PANEL_WEB.bat  -  Doble clic para abrir el TABLERO web de
REM  Fuzion FX en el navegador. Muestra en vivo: acierto real por
REM  bot, pagos y filtro, transacciones, grafico real, mapa del
REM  proyecto y bloqueo por noticias. Solo lectura.
REM  Se abre solo en http://127.0.0.1:8770  (cierra la ventana para parar).
REM ============================================================
title FUZION FX - Panel web
cd /d "%~dp0"
echo.
echo   Abriendo el tablero en el navegador (http://127.0.0.1:8770)...
echo   NO cierres esta ventana mientras quieras ver el panel.
echo.
python fuzion_fx\dashboard\server.py
pause
