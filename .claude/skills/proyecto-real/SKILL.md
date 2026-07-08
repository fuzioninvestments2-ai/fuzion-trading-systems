---
name: proyecto-real
description: TODO lo específico del bot Fuzion Mercado Real / FX (carpeta, cuenta, token, datos, arranque, horario). Úsalo cuando el usuario diga "el bot real", "mercado real", "arrancar el real", "activar el real el domingo", "configurar FX", o cualquier ajuste del proyecto REAL. Para OTC, usa `proyecto-otc`.
---

# Proyecto REAL · Fuzion POption FX

Bot de SEÑALES para el MERCADO REAL de Pocket Option: SOLO monedas (22 pares
forex, nada de cripto ni metales). Lun-Vie con horario. Demo, solo lectura, NO
coloca órdenes. Este skill centraliza lo PROPIO del proyecto REAL; los módulos
técnicos compartidos están en los skills `01`..`10`.

## Identidad del proyecto (no se cruza con el OTC)
| Pieza | Valor REAL |
|---|---|
| Carpeta | `C:\Users\yeney\fuzion-real` |
| Bot de Telegram | **@FuZionFzbot** — "Fuzion POption FX" |
| Token (.env) | `TELEGRAM_BOT_TOKEN_REAL=...` |
| Cuenta Pocket Option / SSID | `ssid_real.txt` |
| Base de datos | `history_real.db` |
| Datos en la nube | `datasets/real` |
| Lanzador | `INICIAR_REAL.bat` |
| Perfil | `bot/profiles.REAL_PROFILE` (22 pares; veta cripto/metales) |

## Diferencias con OTC (protección extra)
- **Horario**: Lun-Vie, sesiones Londres/NY; fuera de sesión, calla.
- **Noticias**: no operar antes/durante/después de alto impacto.
- **Spread**: bloquea si > 2 pips.
- **Alineación mínima**: 8/12 (OTC es 7/12).
- **Fuentes de datos**: Pocket Option + TradingView (CSV) + yfinance de respaldo.
- Sub-minuto: se LEE como contexto, pero el menú real no ofrece entradas de 5s.

## Estudio del mercado (por qué FX SÍ vale la pena, a diferencia de OTC)
El FX real NO es sintético: tiene oferta/demanda de bancos, así que PUEDE tener
memoria. El estudio honesto lo confirma en los datos reales disponibles (EURCAD):

```bash
python -m bot.estudio_fx        # autocorrelación, %up, predictor y motor por TF + OOS
python bot/test_estudio_fx.py   # valida la mecánica (sin red)
```

**Hallazgo (EURCAD, único par con historia decente):** autocorrelación de retornos
**−0.05 a −0.11** en 1m-30m (el OTC daba ~0). Es memoria real: reversión de corto
plazo. PERO el motor cae out-of-sample (5m 60%→46%), así que aún NO es un borde
probado — es sobreajuste hasta tener más datos. Conclusión disciplinada: hay
estructura que investigar, falta MÁS DATO REAL para decidir.

## Flujo de datos (TradingView → estudio → backtest)
El entorno cloud **bloquea** las descargas (403). Exporta en TU PC y usa el ingestor:
1. En TradingView exporta cada par → guarda como `datos/raw/PAR_TIMEFRAME.csv`
   (ej. `EURUSD_1m.csv`, `EURUSD_5m.csv`). Timeframes: 1m,2m,3m,5m,15m,30m,1h,4h.
2. Ingerir (convierte al formato interno `datasets/PAR__CLAVE.csv.gz`):
   ```bash
   python -m bot.ingest_tradingview
   ```
3. Estudiar y backtestear (los tiempos que OPERAS: 1m,2m,3m,5m):
   ```bash
   python -m bot.estudio_fx --pairs all --timeframes 1m,2m,3m,5m,15m,30m,1h
   python -m bot.skills.backtest_ensemble --pairs all --timeframes 1m,2m,3m,5m
   ```
Buscar: pares con winOOS > 52% (borde real). Detalle en `datos/raw/README.md`.
> Regla: NO se inventan datos. Sin fuente real, un timeframe se marca "sin datos".

## Sistema de skills inteligentes (`bot/skills/`)
Ensemble que VOTA dirección y APRENDE de resultados reales (no de sí mismo). Solo
señales; el humano ejecuta. Skills: reversión (autocorrelación), momentum. El
`SkillManager` sube/baja el peso de cada skill según acierte en vivo. Backtest
honesto out-of-sample en `bot/skills/backtest_ensemble.py`. Test: `bot/skills/test_skills.py`.

## Arrancar (mercado abierto)
```
cd $env:USERPROFILE\fuzion-real
.\INICIAR_REAL.bat
```
Cargar historial real primero si hace falta: `python -m bot.historical_loader`.

## Reglas del proyecto
- SOLO monedas (decisión firme). Nada de cripto/metales.
- Solo lectura; jamás órdenes. No evasión de IP/VPN.
- SSID de la cuenta REAL en `ssid_real.txt` (distinta cuenta que OTC).

## Errores comunes (dónde ir)
- "Invalid token" → token de @FuZionFzbot mal copiado → skill `08-notifications`.
- Sin datos reales → `02-market-data` (`historical_loader`, TradingView/yfinance).
- Horario/sesión/noticias bloquean → es PROTECCIÓN correcta → skill `05-protection`.
