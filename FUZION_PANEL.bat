@echo off
REM ============================================================
REM  FUZION_PANEL.bat  -  Doble clic para abrir la APP de control
REM  de Fuzion FX (botones: Arrancar / Detener / Estado / Resumen).
REM  Demo, solo lectura. No coloca ordenes.
REM ============================================================
cd /d "%~dp0"
REM pythonw abre la app SIN ventana negra de consola; si no esta,
REM cae a python normal.
start "" pythonw fuzion_fx\scripts\control_panel.py
if errorlevel 1 start "" python fuzion_fx\scripts\control_panel.py
