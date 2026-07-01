# 🏎️ Especificación del Bot de Trading — "Motor Ferrari"

> Documento maestro que organiza TODA la información y decisiones del proyecto.
> Bot de trading automatizado para **Pocket Option** (opciones binarias),
> inspirado en Dewbot / LIEBBOT, construido sobre el motor que ya validamos.

---

## 0. ⚠️ Nota de honestidad (leer PRIMERO)

Este documento organiza el objetivo del proyecto **tal como lo pidió el usuario**,
pero como desarrolladores responsables dejamos por escrito lo que es real:

- **Ningún bot garantiza ganancias.** Las cifras "hasta $500/día", "$1000+/día"
  o "win 90-100%" son **material de marketing**, no promesas alcanzables. En
  trading real nadie puede garantizar un porcentaje de acierto.
- Los mercados **OTC de Pocket Option son sintéticos** (los genera el bróker);
  un buen resultado en demo **no se traduce** automáticamente a ganancias.
- **El Martingale puede vaciar una cuenta** en una sola racha de pérdidas.
- **Regla de oro: DEMO primero, siempre.** Pasar a dinero real requiere
  confirmación explícita y guardarraíles activos.

El objetivo realista: un sistema **disciplinado, rápido, robusto y medible** que
elimine la emoción y gestione el riesgo — no una máquina de ganar dinero seguro.

---

## 1. 🎯 Objetivo del proyecto

Bot automatizado que ejecuta operaciones en Pocket Option basándose en análisis
técnico, gestionando el riesgo y deteniéndose al alcanzar objetivos definidos.
Operación 24/7, control desde **Telegram** y/o **app de escritorio**, con mejoras
continuas ("modo avanzado").

---

## 2. 📊 Modelo de referencia (Dewbot) — SOLO referencia

| Plan | Capital | "Ganancia potencial" (marketing) |
|------|---------|----------------------------------|
| Light | $50 | hasta $50/día |
| Prime | $120 | hasta $500/día |
| Pro | $200 | $1,000+/día |

Mecánica que SÍ replicaremos (es sensata):
- Configurar **Trade Capital** y **Target Profit**.
- **Detenerse automáticamente** al alcanzar el target profit de la sesión.
- Permitir **varias sesiones** al día.

Lo que NO replicamos: las promesas de rentabilidad.

---

## 3. ⚙️ Parámetros de configuración

**Principales:**
- `trade_capital` — dinero a arriesgar por sesión (ej. $50, $100, $500).
- `target_profit` — ganancia objetivo por sesión (ej. $2, $5, $10, $50, $100).
- `max_sessions_per_day` — máximo de sesiones por día (ej. 10).
- `auto_restart` — iniciar la siguiente sesión al completar una.

**Recomendaciones por capital (orientativas):**
| Capital | Target profit sugerido |
|---------|------------------------|
| $50–$100 | $2–$5 por sesión |
| $200 | $10 por sesión |
| $500+ | $50–$100 por sesión |
| $1000+ | $100+ por sesión |

---

## 4. 🔀 Modos de operación

**Modo Oscillate** (mercado lateral/rango):
- Compra en soportes, vende en resistencias.
- Detecta rangos de precio y opera dentro de ellos.
- (Encaja con nuestra estrategia de reversión actual.)

**Modo Slide** (tendencia fuerte):
- Sigue la tendencia dominante, opera a favor del momentum.
- (Requiere una estrategia de seguimiento de tendencia — a construir.)

---

## 5. 🧱 Stack Methods (apilamiento de confirmaciones)

Cuántos indicadores deben coincidir y con qué confianza mínima:

| Método | Indicadores que coinciden | Confianza mínima |
|--------|---------------------------|------------------|
| `conservative` | ≥ 4 | 80% |
| `moderate` | ≥ 3 | 70% |
| `aggressive` | ≥ 2 | 60% |

> Nota: nuestra estrategia de confluencia ya combina EMA + RSI + Estocástico;
> aquí la extenderemos a un sistema de "votos" con umbral de confianza.

---

## 6. ⏱️ Períodos de tiempo (timeframes)

M1 (1 min) · M5 (5 min) · M15 (15 min) · M30 (30 min) · H1 (1 hora).

---

## 7. 🛡️ Gestión de riesgo (guardarraíles OBLIGATORIOS)

- **DEMO por defecto.** Pasar a real: aviso grande + confirmación explícita.
- **Filtro de pago:** operar solo activos con payout ≥ 92% (si el feed lo da).
- **Martingale (opcional, con límites):**
  - Tope de pasos (ej. máx. 4, como en LIEBBOT). Nunca infinito.
  - Se desactiva si se alcanza el stop diario.
- **Stop diario obligatorio:** si la pérdida del día supera un límite, el bot
  **se apaga solo**. Es la defensa clave contra el desastre.
- **Detención por target:** al llegar al `target_profit`, cierra la sesión.
- **Límite de operaciones/día** (`max_sessions_per_day`).

---

## 8. 🏗️ Stack tecnológico (de la especificación)

- **Lenguaje:** Python 3.10+.
- **Automatización de navegador (a decidir):** Selenium 4.x o Playwright +
  ChromeDriver/EdgeDriver. *(Alternativa: conexión directa por WebSocket.)*
- **Análisis técnico:** pandas 2.0+, numpy 1.24+, ta-lib o pandas-ta.
  *(Ya tenemos indicadores propios en streaming; ta-lib es difícil de instalar
  en Windows — pandas-ta es más fácil.)*
- **Interfaz gráfica:** PyQt5/PyQt6 + matplotlib (gráficos en vivo).
- **Base de datos:** sqlite3 (local) / PostgreSQL (producción).
- **Tiempo real:** websocket-client, requests.
- **Utilidades:** schedule, python-dotenv, loguru.

---

## 9. 🔗 Mapeo con lo YA construido (no partimos de cero)

| Necesidad de la spec | Ya construido | Estado |
|----------------------|---------------|--------|
| Indicadores técnicos | `indicators/ema, rsi, stochastic` (streaming) + `core/indicators.py` (pandas) | ✅ |
| Estrategia / confluencia | `strategy/confluence.py` | ✅ (ampliar a "votos") |
| Conexión + reconexión | `connection/ws_client.py`, `bot/resilient_pocket_option.py` | ✅ |
| Validación de datos | `validation/timestamp_guard.py` | ✅ |
| Orquestador / sesiones | `bot/otc_bot.py`, `bot/run_demo.py` | ✅ base (falta sesiones/target) |
| Alertas Telegram | `monitoring/alerts.py` | ✅ existe, integrar |
| Config + presets | — | ⏳ por hacer |
| Gestión de riesgo (stop diario, martingale) | — | ⏳ por hacer |
| Filtro de payout ≥ 92% | — | ⏳ por hacer (depende del feed) |
| Modo Slide (tendencia) | — | ⏳ por hacer |
| Interfaz PyQt / panel | — | ⏳ por hacer |
| Bot de Telegram (comandos) | — | ⏳ por hacer |

---

## 10. ❓ Decisiones técnicas pendientes (a acordar con el usuario)

1. **¿Cómo conectamos a Pocket Option?**
   - **A) Navegador (Selenium/Playwright):** controla la web real de PO como un
     humano. Más parecido a Dewbot/LIEBBOT y más robusto ante cambios del socket,
     pero más pesado y lento.
   - **B) WebSocket directo:** lo que empezamos. Más rápido, pero frágil (PO puede
     cambiar el protocolo) y su autenticación real usa el formato
     `42["auth",{"sessionToken":...}]` (a corregir en el cliente existente).
2. **¿Primer control: Telegram o app de escritorio (PyQt)?**
3. **¿Martingale dentro, con los límites del punto 7?**

---

## 11. 🗺️ Roadmap por módulos (Regla 1: uno a la vez, validado)

1. **Config + presets** — parámetros del punto 3 en un archivo, con modos
   conservador/moderado/agresivo.
2. **Gestión de riesgo** — `target_profit`, `stop diario`, `max_sessions`,
   martingale con tope. (Protege el capital ANTES de automatizar.)
3. **Motor de sesiones** — ejecutar sesión → parar en target o stop → repetir.
4. **Estrategia ampliada** — sistema de "votos" (stack methods) + modo Slide.
5. **Filtro de payout ≥ 92%** — (cuando confirmemos que el feed da el payout).
6. **Conexión real** — según decisión del punto 10 (navegador o WebSocket).
7. **Control Telegram** — comandos /start /stop /estado /señal + envío de señales.
8. **Interfaz PyQt** (opcional) — panel estilo LIEBBOT con Run/Stop y gráficos.

Cada módulo: comentado (el "porqué"), robusto (try/except + reconexión),
validado con su script de prueba en terminal, y **demo primero**.

---

## 12. 📜 Reglas del proyecto (siempre)

1. **Modular progresivo** — no se avanza al siguiente módulo sin validar el actual.
2. **Comentar el porqué** — cada fórmula/decisión explicada.
3. **Errores robustos** — WebSockets/APIs con try/except y reconexión (backoff).
4. **Validación** — script de prueba antes de dar por terminado un archivo.
5. **Seguridad** — demo primero; credenciales (SSID) solo en `.env`, nunca en git.
