---
name: 07-position-manager
description: Quantum Trading Core · LÍMITE — el bot NO abre ni administra posiciones (no coloca órdenes); lo que "administra" es el registro de señales. Úsalo cuando el usuario diga "gestionar la posición", "cerrar la operación", "trailing/stop", "administrar trades".
---

# 07 · Gestión de posiciones (LÍMITE del sistema)

Quantum Trading Core **no abre ni administra posiciones**: no coloca órdenes (ver
`06`). En binarias, además, la "posición" es una expiración fija (no hay stop ni
trailing). Este skill documenta qué SÍ hace el sistema en lugar de gestionar trades.

## Qué reemplaza a la "gestión de posiciones"
- **Disciplina de entrada** (Motor Cuántico, Skill 04): la señal solo sale con
  convergencia y probabilidad ≥90%. Filtra las malas ANTES (donde se gana en binarias).
  Si el motor cambia de dirección antes de la expiración, es una NUEVA lectura — el
  humano decide.
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
