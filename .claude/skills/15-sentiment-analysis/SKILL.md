---
name: 15-sentiment-analysis
description: Quantum Trading Core · Sentimiento/noticias como FILTRO defensivo — SOLO Mercado Real (en OTC no aplica: precio sintético). Úsalo cuando el usuario diga "sentimiento", "noticias", "calendario económico", "Fear & Greed", "riesgo de noticia".
---

# 15 · Análisis de sentimiento / noticias

Sentimiento = leer el CONTEXTO (noticias, calendario, Fear & Greed) para NO operar
contra un evento fuerte. En Quantum Trading Core es **defensivo** (filtro), no una
señal de entrada. Nota: "reducir el tamaño de la posición" NO aplica aquí — el
sistema es de SEÑALES (no coloca ni dimensiona órdenes; ver Skill 06). Si el
sentimiento es extremo y contra la señal, el motor simplemente NO opera.

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
