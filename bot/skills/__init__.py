"""
bot/skills/
===========
Sistema de skills inteligentes para el MERCADO REAL (FX). Cada skill es un
componente que analiza el mercado y VOTA una dirección con confianza; el
`SkillManager` combina los votos con pesos que APRENDEN del resultado REAL del
mercado (no de una simulación inventada).

Principios NO negociables (heredados del proyecto):
  - SOLO SEÑALES: ningún skill coloca órdenes. La ejecución la hace el humano.
  - HONESTIDAD: se aprende del movimiento real del precio, nunca de un resultado
    fabricado. Un borde solo cuenta si sobrevive out-of-sample.
  - NO DUPLICAR: se reutilizan los indicadores/velas del paquete `bot`.
"""
