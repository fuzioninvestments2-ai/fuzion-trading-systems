@echo off
chcp 65001 >nul
echo ============================================================
echo   DESCARGA MASIVA FX - Dukascopy (Fuzion Mercado Real)
echo ============================================================
echo   LOS 13 TIEMPOS desde 2003:
echo   5s,10s,15s,30s,1m,2m,3m,5m,10m,15m,30m,1h,4h
echo   22 pares forex
echo ------------------------------------------------------------
echo   Resume activo: si lo cortas y lo vuelves a lanzar, sigue
echo   donde quedo. Los segundos (resampleo de 1s) son lo mas
echo   lento; puede tardar dias segun tu internet. Dejalo correr.
echo ============================================================
echo.
echo Inicio: %date% %time%
echo.

python -m bot.dukascopy_deep --desde 2003-01-01

echo.
echo Verificando lo descargado...
python -m bot.dukascopy_deep --verificar

echo.
echo Fin: %date% %time%
echo PROCESO COMPLETADO
pause
