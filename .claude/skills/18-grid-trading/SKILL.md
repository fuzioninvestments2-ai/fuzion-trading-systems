---
name: 18-grid-trading
description: Grid / rejilla de órdenes — Fuzion NO lo hace (son órdenes automáticas, prohibido); por qué no encaja en binarias y la alternativa sana. Úsalo cuando el usuario diga "grid", "rejilla", "órdenes escalonadas", "poner niveles de compra/venta automáticos", o al pensar en trading de rejilla.
---

# 18 · Grid trading (LÍMITE del proyecto)

Grid = sembrar muchas órdenes automáticas a distintos precios (una rejilla).
Fuzion **no lo hace**: son órdenes reales automáticas (ver `06`), prohibido por
regla no negociable.

## Por qué NO — y por qué no encaja en binarias
- El grid es de mercados con posición continua y precio que oscila (spot/futuros).
  La **binaria expira** en un tiempo fijo: no hay posición que "rellenar" en una
  rejilla; el concepto no aplica.
- Automatizar una malla de entradas sobre precios OTC **sintéticos** (que PO
  reinicia) multiplica el riesgo sin ventaja real.
- Fuego automático sin humano = justo lo que el proyecto evita.

## La alternativa sana
- Una señal por activo, cuando el sistema alinea (`04`, `13`), con protección
  (`05`). Calidad sobre cantidad.
- Varios pares se manejan con la **watchlist** (`12-multi-pair-manager`), que es
  vigilar muchos activos — NO sembrar órdenes en cada uno.

## OTC vs Real
Prohibido en **ambos** proyectos.

## Probar
```bash
grep -rInE "grid|rejilla|malla_ordenes" bot/ || echo "OK: sin grid trading"
```
