---
name: 15-sentiment-analysis
description: Sentimiento / contexto de noticias — SOLO para el Mercado Real (FX); en OTC no aplica (precio sintético, sin noticias reales). Úsalo cuando el usuario diga "sentimiento", "noticias del mercado", "calendario económico", "riesgo de noticia", "por qué no operar con noticia", o al tocar news_filter.
---

# 15 · Análisis de sentimiento / noticias

Sentimiento = leer el CONTEXTO del mercado (noticias, calendario económico) para
NO operar contra un evento fuerte. En Fuzion es **defensivo** (protege), no una
señal de entrada.

## Regla honesta: OTC vs Real (dos proyectos distintos)
- **Mercado Real (FX)** → SÍ aplica. Los precios reales reaccionan a noticias
  (tipos, NFP, IPC). El filtro `bot/news_filter.py` bloquea antes/durante/después
  de un evento de alto impacto. Esto pertenece al proyecto **`proyecto-real`**.
- **OTC** → **NO aplica**. Los precios OTC de Pocket Option son **sintéticos**: no
  los mueve ninguna noticia real. Meter "sentimiento de noticias" en OTC sería
  inventar una relación que no existe (contra la regla de honestidad). En OTC el
  contexto se lee con el mercado mismo (régimen ADX, manipulación, vacío).

## Qué hace hoy (Real)
- `news_filter`: ventana de silencio alrededor de noticias de alto impacto.
- `market_hours` / `clasificar_sesion`: sesiones buenas (Londres/NY) vs a evitar.
Juntos son el "sentimiento operativo": cuándo el mercado está en condiciones sanas.

## Ampliación posible (si se pide, solo Real)
Feed de calendario económico externo → marcar horas de riesgo. Sería un módulo
nuevo, con reconexión robusta (Regla 3) y su `test_*.py` sin red. Solo tiene
sentido en `proyecto-real`.

## Probar
```bash
python bot/test_news_filter.py
python bot/test_market_hours.py
```
