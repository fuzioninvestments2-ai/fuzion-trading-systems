---
name: 05-risk-management
description: Quantum Trading Core · Filtros ESTRICTOS de seguridad antes del motor (win-rate ≥60%, alineación ≥80%, indicadores, S/R, anti-basura). Bloquea señales de baja calidad. Úsalo cuando el usuario diga "filtros", "por qué rechazó", "payout", "manipulación", "datos basura".
---

# 05 · Gestión de riesgo (filtros estrictos)

Puerta de calidad ANTES del motor cuántico. El foco es NO PERDER: mejor no operar
que operar una señal mediocre. NO coloca órdenes ni stop-loss (es de señales).

## `validate_strict_filters()` → `bot/validacion_senal.validate_signal(datos)`
Si CUALQUIERA falla → NO OPERAR con motivo exacto:
- **Alineación ≥ 80%** · **Win-rate histórico ≥ 60%** (tras 10 señales medidas) ·
  **Umbral aprendido ≥ 25%**.
- **Indicadores (RSI/Estocástico/MACD/Bandas) ≥ 60%**; nada en 45-55% (ruido).
- **Pegado a S/R** (< 15 pips) → NO OPERAR.
- **Timeframes completos** (Skill 13).
Umbrales calibrables arriba del módulo. En el motor cuántico en vivo se aplican los
que casan con la escala real (S/R, win-rate, umbral, convergencia); los de 60% por
indicador quedan informativos (bloquearlos a ciegas = nunca operar).

## Barreras adicionales
- **Payout** (`bot/payout.py`): <75% bloquea; 85-92% avisa (el trader opera a 92%).
- **Manipulación** (`bot/manipulation.py`): spike que REBOTA (wick fabricado) → NO
  operar (un movimiento direccional real NO se bloquea).
- **Vacío/plano** (`bot/void_detector.py`) · **Anti-basura** (`bot/data_quality.py`)
  · **Noticias/Sesión** (real: `bot/news_filter.py`, `bot/market_hours.py`).

## Probar
```bash
python bot/test_validacion_senal.py
python bot/test_filtros.py
python bot/test_manipulation.py
```
