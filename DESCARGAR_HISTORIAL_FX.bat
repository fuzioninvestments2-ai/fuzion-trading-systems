@echo off
chcp 65001 >nul
echo ============================================================
echo   DESCARGA MASIVA FX - Dukascopy (Fuzion Mercado Real)
echo ============================================================
echo   1m,5m,10m,15m,30m,1h,4h  desde 2003  (profundo)
echo   2m,3m  derivados del 1m
echo   5s,10s,15s,30s  ventana reciente (30 dias)
echo   22 pares forex
echo ------------------------------------------------------------
echo   Resume activo: si lo cortas y lo vuelves a lanzar, sigue
echo   donde quedo. Puede tardar horas. Dejalo corriendo.
echo ============================================================
echo.
echo Inicio: %date% %time%
echo.

python -m bot.dukascopy_deep --desde 2003-01-01 --dias-segundos 30

echo.
echo Verificando lo descargado...
python -m bot.dukascopy_deep --verificar

echo.
echo Fin: %date% %time%
echo PROCESO COMPLETADO
pause
