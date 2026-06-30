"""
Paquete `bot`: orquestador del bot OTC (Pocket Option) en modo simulado.

Reutiliza, sin duplicar lógica, los módulos ya validados del proyecto:
  - strategy.confluence   (señales CALL/PUT/NONE)
  - validation.timestamp_guard (descarta señales con deriva > 500 ms)

NO toca el sistema FUZION existente (main.py, broker/, core/). Está pensado
para, más adelante, sustituir el feed simulado por el cliente real de Pocket
Option en modo demo, sin reescribir el orquestador.
"""
