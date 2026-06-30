# Bot OTC (Pocket Option) — Modo Simulado

Este paquete es una **capa nueva y aislada** para señales de opciones binarias
OTC. **No modifica** el sistema FUZION existente (`main.py`, `broker/`, `core/`).
Reutiliza módulos ya validados del proyecto en lugar de duplicarlos.

> ⚠️ **Aviso honesto:** las opciones binarias son productos de **ALTO RIESGO**.
> La mayoría de los traders minoristas pierden dinero. Ningún bot garantiza
> ganancias. Empieza y quédate en **demo** todo el tiempo que necesites.

---

## ¿Qué hace?

Coordina, tick a tick, este flujo:

```
precio (feed)  ─►  estrategia de confluencia  ─►  guardia de timestamp  ─►  log
                   (EMA + RSI + Estocástico)      (descarta si deriva > 500 ms)
```

En **modo simulado** las señales solo se **registran**; NO se envía ninguna orden.

---

## Piezas (y qué reutiliza)

| Archivo | Rol | Reutiliza |
|---|---|---|
| `otc_bot.py` | Orquestador (`OTCSignalBot`): coordina el flujo | `strategy/`, `validation/` |
| `run_simulado.py` | Arranque en modo simulado con feed de prueba | `otc_bot`, `strategy/`, `validation/` |
| `resilient_connector.py` | Reconexión genérica con backoff exponencial + jitter | — |
| `resilient_pocket_option.py` | Cliente Pocket Option **con reconexión** (subclase) | `broker/pocket_option_client.py` |
| `test_*.py` | Pruebas de validación (Regla 4) | — |

**Diseño:** SOLID (responsabilidad única + inyección de dependencias). La
subclase `ResilientPocketOptionClient` añade reconexión **sin tocar** el cliente
original (principio abierto/cerrado).

---

## Cómo ejecutarlo

Requisitos (ya en `requirements.txt`): `numpy`, `websockets`, `websocket-client`.

```bash
# Simulación completa (sin red, sin credenciales, sin órdenes)
python3 bot/run_simulado.py

# Pruebas de validación
python3 bot/test_otc_bot.py
python3 bot/test_resilient.py
```

---

## Estado actual

- [x] Indicadores en streaming (EMA, RSI, Estocástico) — O(1), buffer circular
- [x] Estrategia de confluencia + backtest descriptivo
- [x] Guardia de timestamp (descarta señales con deriva > 500 ms)
- [x] Orquestador en modo simulado
- [x] Reconexión robusta para Pocket Option (subclase no invasiva)
- [ ] **Conexión real a la cuenta demo** (requiere tu `SSID` de Pocket Option)
- [ ] Bucle en vivo: cliente real → estrategia → registro de señales (demo)

---

## Próximo paso (requiere tu decisión)

Para conectar a tu **cuenta demo real** de Pocket Option hace falta tu
credencial **`SSID`** (token de sesión). Eso es información sensible:

- **NUNCA** se versiona en git (va en `.env` / variables de entorno).
- Se usa solo contra el endpoint **demo** (`demo-api-v3.po.market`).
- Aun en demo, primero se valida que solo **lea precios y registre señales**,
  sin enviar órdenes, hasta que tú confirmes lo contrario.

Cuando quieras dar ese paso, te explico cómo obtener el `SSID` y cómo guardarlo
de forma segura, antes de escribir nada.
