---
name: proyecto-otc
description: TODO lo específico del bot Fuzion OTC (carpeta, cuenta, token, datos, arranque, tarjeta). Úsalo cuando el usuario diga "el bot OTC", "arrancar OTC", "algo del OTC no funciona", "configurar OTC", o cualquier ajuste/corrección del proyecto OTC. Para el mercado real, usa `proyecto-real`.
---

# Proyecto OTC · Fuzion POption OTC

Bot de SEÑALES para Pocket Option OTC (velas sintéticas de PO, 24/7). Demo, solo
lectura, NO coloca órdenes. Este skill centraliza lo PROPIO del proyecto OTC; los
módulos técnicos compartidos están en los skills `01`..`10`.

## Identidad del proyecto (no se cruza con el real)
| Pieza | Valor OTC |
|---|---|
| Carpeta | `C:\Users\yeney\fuzion-otc` |
| Bot de Telegram | **@fuzion_ale_bot** — "Fuzion POption OTC" |
| Token (.env) | `TELEGRAM_BOT_TOKEN_OTC=...` |
| Cuenta Pocket Option / SSID | `ssid_otc.txt` |
| Base de datos | `history.db` |
| Datos en la nube | `datasets/otc` |
| Lanzador | `INICIAR_OTC.bat` |
| Perfil | `bot/profiles.OTC_PROFILE` (`usa_sistema=False` → tarjeta COMPLETA) |

## Arrancar
```
cd $env:USERPROFILE\fuzion-otc
.\INICIAR_OTC.bat
```
Deja ~1 min (que entren ticks en vivo). Telegram: `/start` → OTC Market → activo → tiempo.

## La tarjeta (lo que ve el trader)
Motor clásico (`analyze` + `_format_deep`): gráfico ancho arriba, ALERTA, Modo/ADX,
alineación + fractal, Lectura, VWAP, techo/piso, **panel de tiempos 5s→30m en 3
columnas** (1h+ se analizan por dentro, no se muestran), ⏱️ hora de entrada, Pago,
Mejores indicadores, aprendizaje real. Config visible en `bot/telegram_signals.py`.

## Reglas del proyecto
- Solo lectura; jamás órdenes. Solo velas reales de PO (nada inventado).
- No evasión de IP/VPN. SSID de la cuenta OTC en `ssid_otc.txt`.
- Cambios se prueban (`for t in bot/test_*.py`) y se commitean/pushean.

## Errores comunes (dónde ir)
- "Invalid token" → token mal copiado (distingue mayúsculas) → skill `08-notifications`.
- "pocos datos" → `02-market-data` (importar datasets → history.db).
- Conexión se cae → `01-api-connection`.
