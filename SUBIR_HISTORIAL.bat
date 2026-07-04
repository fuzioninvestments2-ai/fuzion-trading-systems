@echo off
REM ============================================================
REM  SUBIR_HISTORIAL.bat  -  Sube el historial exportado
REM  (carpeta datasets/) a GitHub, para tenerlo en la NUBE.
REM  Antes: corre DESCARGAR_HISTORIAL (genera datasets/).
REM ============================================================
title Subir Historial a la nube (GitHub)
cd /d "%~dp0"

echo   Exportando lo ultimo a datasets/ ...
python -m bot.dataset_export export

echo.
echo   Subiendo datasets/ a GitHub ...
git add datasets/
git commit -m "datos: historial OTC/FX exportado"
git push

echo.
echo ============================================================
echo   LISTO. El historial quedo guardado en la nube (GitHub).
echo ============================================================
pause >nul
