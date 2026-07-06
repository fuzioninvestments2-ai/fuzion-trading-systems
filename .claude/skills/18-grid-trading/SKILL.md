---
name: 18-grid-trading
description: Quantum Trading Core · LÍMITE — sin grid/rejilla de órdenes (son órdenes automáticas, prohibido) y no encaja en binarias. Úsalo cuando el usuario diga "grid", "rejilla", "órdenes escalonadas", "niveles automáticos".
---

# 18 · Grid trading (LÍMITE del sistema)

Grid = sembrar muchas órdenes automáticas a distintos precios. Quantum Trading Core
**no lo hace**: son órdenes reales automáticas (ver `06`), prohibido por regla no
negociable. Los Soportes/Resistencias (Skill 01) se usan para NO operar pegado a
ellos, no para sembrar una rejilla.

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
