---
name: 07-position-manager
description: Gestión de posiciones — Fuzion NO abre ni administra posiciones (no coloca órdenes); la "gestión" sana es disciplina + registro de la señal. Úsalo cuando el usuario diga "gestionar la posición", "cerrar la operación", "trailing/stop", "cuántas abiertas", "administrar trades", o al pensar en manejar operaciones abiertas.
---

# 07 · Gestión de posiciones (LÍMITE del proyecto)

Fuzion **no abre ni administra posiciones**: no coloca órdenes (ver `06`). En
opciones binarias, además, la "posición" es una expiración fija (no hay stop ni
trailing). Este skill documenta qué SÍ hace el bot en lugar de gestionar trades.

## Qué reemplaza a la "gestión de posiciones"
- **Disciplina de entrada** (`04-strategy-logic`): la señal solo sale con
  alineación mínima (7/12 OTC, 8/12 real) y a favor de la EMA200-1H. Filtra las
  malas ANTES, que es donde se gana en binarias.
- **Protección** (`05-protection`): bloquea payout malo, noticias, sesión mala,
  manipulación, vacío, datos basura.
- **Registro** (`11-database-persistence`, `signal_log`): cada señal se guarda y
  luego se marca acierto/fallo. Ese es el "estado" que se administra: el
  **historial**, no una orden abierta.

## Por qué no hay "trailing/stop/cierre"
- No hay orden que cerrar: el bot no la abrió.
- La binaria expira sola en el tiempo elegido; el resultado lo mide el registro.
- Un módulo que "cierre posiciones" implicaría colocar/cancelar órdenes reales —
  justo lo prohibido por el proyecto (`no negociable`).

## OTC vs Real
Igual para ambos proyectos: ninguno gestiona posiciones. Cuenta/token/carpeta:
`proyecto-otc` y `proyecto-real`.

## Probar
```bash
# El "estado" que se administra es el registro de señales, no órdenes abiertas:
python bot/test_signal_log.py
```
