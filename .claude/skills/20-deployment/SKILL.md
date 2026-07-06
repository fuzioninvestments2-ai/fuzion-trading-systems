---
name: 20-deployment
description: Quantum Trading Core · Arranque, lanzadores .bat, robot 24/7, health check y (diseño) Docker/VPS. Úsalo cuando el usuario diga "arrancar el bot", "el .bat", "robot 24/7", "Docker", "VPS", "que corra solo", "reiniciar".
---

# 20 · Despliegue y operación 24/7

Cómo se arranca y se mantiene corriendo, en dos carpetas separadas.

## Health check (auto-restart)
El robot vigila que los 9 timeframes sigan respondiendo (Skill 13): si dejan de
llegar, fuerza una reconexión interna del websocket (socket "vivo pero mudo") y, si
no se recupera, reinicia el proceso. Los `.bat` `ROBOT_*` reinician si el bot cae.

## Docker / VPS (DISEÑO, pendiente)
`Dockerfile` + `docker-compose.yml` con auto-restart y un health check que reinicie
si el Skill 13 detecta timeframes caídos. Hoy corre en Windows con los `.bat`; el
contenedor sería el siguiente paso para VPS 24/7.

## Dos carpetas (un proyecto por carpeta)
- `fuzion-otc` → bot OTC. `fuzion-real` → bot REAL. Cada `.bat` usa `%~dp0` (su
  propia carpeta) y hace `git pull` al arrancar (trae los últimos cambios).

## Lanzadores (doble clic en Windows)
- `INICIAR_OTC.bat` / `INICIAR_REAL.bat` — arrancan el bot de Telegram del bot.
- `ROBOT_AUTO.bat` / `ROBOT_REAL.bat` — robot 24/7: descarga/acumula y SUBE a la
  nube solo; si se cae, se REINICIA (reinicio interno de la conexión).
- `DESCARGAR_HISTORIAL.bat`, `SUBIR_HISTORIAL.bat`, `ACUMULADOR.bat`.

## Subida a la nube (robusta)
- `bot/cloud_push.py` — reintenta pull+push hasta entrar (no pierde la ronda).
- Export DETERMINISTA (gzip mtime=0): solo sube lo que cambió.

## Reglas
- El bot de Telegram y el robot NO a la vez con el mismo SSID (una conexión).
- Tu PC encendida para que el robot siga; se detiene si la apagas.

## Arrancar OTC
```
cd $env:USERPROFILE\fuzion-otc
.\INICIAR_OTC.bat
```
