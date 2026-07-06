---
name: 17-dca-strategy
description: Quantum Trading Core · LÍMITE — sin DCA/martingala (implica colocar órdenes reales, prohibido). Cada lectura pasa por el filtro 90% del Motor (Skill 04), no se promedia a ciegas. Úsalo cuando el usuario diga "DCA", "promediar", "martingala", "doblar tras perder".
---

# 17 · DCA / promediar (LÍMITE del sistema)

DCA y su primo la **martingala** = añadir órdenes tras una pérdida. Quantum Trading
Core **no lo hace**: implica colocar órdenes reales (ver `06`), prohibido por regla
no negociable. Si algún día se explorara, CADA entrada tendría que pasar el filtro
del 90% del Motor Cuántico (Skill 04) — nunca promediar a ciegas.

## Por qué NO — y por qué es peligroso en binarias
- Cada binaria es todo-o-nada y expira sola: no hay "precio promedio" que mejore;
  solo se **acumula riesgo**.
- Doblar tras perder (martingala) parece infalible y **quiebra la cuenta** en una
  racha normal de fallos. Es el patrón que más rápido funde dinero.
- Choca con el propósito del bot: **disciplina y protección**, no perseguir
  pérdidas.

## Qué usa Fuzion en su lugar
- **Selección, no promedio**: solo entra cuando la alineación (7/12 OTC, 8/12
  real) y la EMA200-1H concuerdan (`04-strategy-logic`). Menos entradas, mejores.
- **Protección** (`05`) que calla en condiciones malas.
- **Registro y aprendizaje** (`09`, `14`): mejora eligiendo mejor, no doblando.

## OTC vs Real
Prohibido en **ambos** proyectos por igual.

## Estado real del código (honesto)
Existe un modelo de **martingala** en `bot/risk_manager.py` (+ preset "agresivo"
en `bot/config.py`), pero SOLO en la capa de **simulación/backtest**
(`motor_service`, `session`, `run_motor_sim`): calcula un stake hipotético, **no
coloca órdenes**. El bot de señales en vivo (`telegram_signals` → `pocket_service`)
NO lo usa. Aun así contradice esta regla; recomendado **neutralizarlo** (forzar
`martingale_enabled=False` y quitar el doblado del preset) para que ni el
simulador modele martingala.

## Probar
```bash
# El flujo vivo no debe tocar martingala (el simulador es aparte):
grep -rInE "martingal" bot/pocket_service.py bot/telegram_signals.py \
  || echo "OK: el flujo vivo no usa martingala"
```
