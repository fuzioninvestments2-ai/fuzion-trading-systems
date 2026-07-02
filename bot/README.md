# Bot de señales — Pocket Option OTC (Telegram)

Bot que lee los precios **reales** de Pocket Option (cuenta **demo**, solo lectura)
y te da señales educativas por Telegram con botones interactivos: eliges mercado →
activo → tiempo → "Iniciar análisis" y recibes una lectura con dirección,
alineación de tiempos, patrones, niveles y alertas de protección.

> ⚠️ **Honestidad, primero.** Ningún bot acierta siempre ni conoce la fórmula
> secreta de Pocket Option. Este bot aporta **disciplina**: opera solo cuando hay
> confluencia real y **calla** (avisa NO OPERAR) cuando el mercado está confuso,
> plano, vacío o manipulado. **No coloca órdenes**: solo lee y explica. Todo en
> **demo**. Su propósito es aprender y decidir mejor, no prometer ganancias.

---

## 1. Instalación

Requisitos: **Python 3.10+**.

```bash
pip install -r bot/requirements.txt
```

(Es un subconjunto ligero; el `requirements.txt` de la raíz trae librerías pesadas
—hmmlearn, brokers— que este bot no necesita.)

## 2. Configuración (2 archivos, nunca se versionan)

**a) `ssid.txt`** — tu sesión de Pocket Option (demo). En la web de PO, abre las
herramientas de desarrollador (F12) → pestaña Network → busca la conexión
websocket y copia el mensaje de auth completo. Se ve así:

```
42["auth",{"session":"...","isDemo":1,"uid":...,"platform":2}]
```

Pégalo en `ssid.txt` en la raíz del proyecto.

**b) `.env`** — el token de tu bot de Telegram (te lo da @BotFather):

```
TELEGRAM_BOT_TOKEN=123456:ABC-tu-token-aqui
```

> 🔒 **Seguridad:** `ssid.txt` y `.env` están en `.gitignore` (no se suben). Si
> alguna vez pegaste tu SSID o token en un chat, **renuévalos** (re-login en PO;
> `/revoke` en @BotFather).

## 3. Arrancar

```bash
python -m bot.telegram_signals
```

Verás `🤖 Bot de SEÑALES en marcha [PRECIOS REALES]`. Abre tu bot en Telegram y
pulsa `/start`. Sin `ssid.txt` funciona en modo simulado (solo interfaz).

---

## 4. Cómo leer la señal

La guía completa, línea por línea, está en
[`docs/GUIA_DE_LECTURA.md`](../docs/GUIA_DE_LECTURA.md). En resumen:

- **Veredicto:** ✅ OPERAR / 🟡 OPCIONAL / 🚫 NO OPERAR.
- **Alineación (0–100%):** cuántas temporalidades coinciden (tu confianza).
- **Modo (Oscillate/Slide):** el bot **cambia el peso de sus indicadores** según
  haya tendencia o rango.
- **Alertas de protección:** manipulación, indecisión, vacío de mercado, doji,
  pegado a techo/piso, pago bajo.

**Regla de oro:** ante la duda, **NO operes**. "No operar" es una respuesta válida
y frecuente por diseño.

---

## 5. Mapa del proyecto (qué hace cada pieza)

**Motor de análisis**
- `deep_analysis.py` — la "ecuación" multi-temporalidad: un analista por tiempo;
  el veredicto es fuerte solo si varios tiempos coinciden.
- `scoring_strategy.py` — 8 indicadores que **votan** (RSI, MACD, Bollinger,
  medias, estocástico, Donchian, **VWAP**, **patrones**), con pesos que se
  ajustan **por tiempo y por régimen** (`weights_for`) y detección de régimen
  con ADX (`regime`).
- `candles.py` — construye velas OHLC desde ticks (volumen = nº de ticks).

**Lecturas adicionales**
- `candle_patterns.py` — doji (indecisión), martillo, envolventes, marubozu.
- `vwap.py` — precio "justo" ponderado por actividad (nivel de referencia).
- `levels.py` — soporte/resistencia (techo y piso) por pivotes.
- `chart.py` — dibuja el gráfico de velas con las líneas de techo/piso.

**Protección**
- `manipulation.py` — detecta spike, congelado, estallido de volatilidad.
- `void_detector.py` — detecta el **vacío del mercado** (huecos/silencio del feed).
- `market_hours.py` — horario (OTC 24/7; real Lun–Vie).
- `payout.py` — extrae el % de pago de forma robusta (validación por rango).

**Aprendizaje**
- `calibration.py` + `backtester.py` — aprenden el **umbral** de confianza óptimo.
- `weight_learning.py` — aprende qué **indicadores** aciertan más en cada activo.
- `signal_log.py` — registra cada señal y **resuelve su resultado real**; el
  aprendizaje de pesos usa esas señales reales cuando hay bastantes.
- `history.py` — repositorio SQLite de velas.
- `collector.py` — colector 24/7 que acumula historial y **prioriza** el activo
  que estás mirando.

**Conexión y bot**
- `pocket_client.py` — cliente websocket de Pocket Option (con reconexión).
- `pocket_service.py` — orquesta todo lo anterior y arma la lectura.
- `telegram_signals.py` — el bot de Telegram con botones (**punto de arranque**).

> Nota: el paquete conserva módulos del prototipo inicial (`otc_bot.py`,
> `run_simulado.py`, `resilient_*.py`) por compatibilidad; el flujo vivo actual
> es el de `telegram_signals.py` → `pocket_service.py`.

---

## 6. Las 4 reglas de desarrollo (`clauderules.md`)

1. **Desarrollo modular y progresivo** (una pieza a la vez, sin duplicar).
2. **Comentar el porqué** (la matemática/razón de cada cambio).
3. **Robustez**: try/except y reconexión automática en red/websockets.
4. **Test de validación** antes de dar por terminado cada archivo.

## 7. Tests

```bash
for t in bot/test_*.py; do python -m "bot.$(basename ${t%.py})"; done
```

Actualmente **25 suites de test**, todas en verde. Cada módulo tiene su
`test_*.py` que corre **sin red** (determinista).

---

## 8. Honestidad y propósito

Este bot **mide y protege**, no adivina. Aprende de sus propios aciertos reales,
que es lo más cercano a la verdad que un software puede hacer — pero el pasado no
garantiza el futuro, y en OTC (precios sintéticos del bróker) hay que tomarlo con
más cautela todavía. Las opciones binarias son de **alto riesgo**; la mayoría de
traders minoristas pierde. Úsalo para **aprender a leer el mercado** y decidir con
disciplina, siempre en **demo**.
