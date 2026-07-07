# Quantum Trading Core — Skills

Sistema unificado de SEÑALES (solo lectura, no coloca órdenes) para Pocket Option.
Núcleo: **9 timeframes (5s-15m)** → indicadores (dir+fuerza) → **Probabilidad
Cuántica** + **Convergencia Logarítmica** → OPERAR solo con **90%+**. Código en
`bot/` (motor: `bot/cuantico.py`).

Son **DOS proyectos** que comparten el mismo motor: **(OTC)** y **(Mercado Real/FX)**.

## Flujo del sistema (cómo conectan los skills)
```
02 Datos (9 TF) ─┐
03 Indicadores ──┼─► 05 Riesgo (filtros) ─► 04 MOTOR CUÁNTICO ─► 08 Alerta/Tarjeta
13 Salud TF ─────┘        (bloquea malas)     (prob + convergencia)   10 Panel
01 S/R (no pegado) ───────────────────────────────┘                   11 DB · 09 Backtest
06/07/17/18 = LÍMITE: la EJECUCIÓN la hace el humano (no coloca órdenes)
```

## Skills POR PROYECTO
| Skill | Proyecto | Carpeta | Bot Telegram |
|-------|----------|---------|--------------|
| `proyecto-otc` | **OTC** | `fuzion-otc` | @fuzion_ale_bot |
| `proyecto-real` | **Mercado Real** | `fuzion-real` | @FuZionFzbot |

## Los 20 skills (Quantum Trading Core)
| # | Skill | Rol en el sistema |
|---|-------|-------------------|
| 01 | api-connection | Conexión + Soportes/Resistencias (no operar a <15 pips) |
| 02 | market-data | Datos OHLC de los 9 timeframes (5s-15m) |
| 03 | indicators | Dirección (+1/-1) y fuerza (0-1) por indicador y tiempo |
| 04 | strategy-logic | **MOTOR CENTRAL**: probabilidad cuántica + convergencia |
| 05 | risk-management | Filtros estrictos antes del motor (win-rate/alineación/S-R) |
| 06 | order-execution | **LÍMITE**: la ejecución la hace el humano |
| 07 | position-manager | **LÍMITE**: no administra posiciones (registro) |
| 08 | notifications | Telegram + tarjeta (prob, convergencia, hora de entrada) |
| 09 | backtesting | Simulación sobre historial real (9 TF) + win-rate medido |
| 10 | monitoring-logging | Panel ASCII de los 9 tiempos + logs |
| 11 | database-persistence | sqlite: velas + señales con prob/convergencia |
| 12 | multi-pair-manager | Escaneo de pares con filtro cuántico |
| 13 | multi-timeframe | Los 9 tiempos: pesos 15/50/35% + salud de datos |
| 14 | parameter-optimization | Ajuste de pesos/umbrales por rendimiento |
| 15 | sentiment-analysis | Noticias/sentimiento (filtro, solo Real) |
| 16 | security-encryption | Secretos (.env, SSID, keys) — nunca en git |
| 17 | dca-strategy | **LÍMITE**: sin DCA/martingala |
| 18 | grid-trading | **LÍMITE**: sin grid |
| 19 | web-dashboard | Dashboard web de solo lectura (diseño/pendiente) |
| 20 | deployment | .bat, robot 24/7, health check, Docker/VPS (diseño) |

## Skills de LÍMITE (no negociable)
`06`, `07`, `17`, `18` conservan su nombre pero **documentan el límite**: el sistema
es de SEÑALES (regla `no negociable` de `CLAUDE.md`). Cuando el Motor (04) da
`operate: True`, la orden la coloca el HUMANO. No contienen lógica que ejecute
órdenes, DCA ni grid. Cambiar eso exigiría confirmación explícita y, aun así, solo
demo + confirmación manual por operación.
