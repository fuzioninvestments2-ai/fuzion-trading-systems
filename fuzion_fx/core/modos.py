"""
core/modos.py (fuzion_fx)
=========================
MODOS de operacion: la MISMA maquina, con mas o menos exigencia, para que el
usuario elija CARACTER — buscar muchas entradas (rapido) o pocas y mas seguras
(lento). Un solo lugar define los parametros de cada modo; el bot los aplica en
vivo (se puede cambiar desde el panel sin reiniciar).

Parametros por modo:
  umbral_convergencia -> cuanto tienen que coincidir las temporalidades (0..1).
  min_tf_convergencia -> cuantas temporalidades con dato hacen falta para exigir
                         la foto completa (si hay menos, cae al motor de 1 tf).
  min_confirmations   -> votos de indicadores en la tf de entrada (de 4).
  scan_interval       -> cada cuantos segundos rastrea (mas chico = mas energia).

PORQUE los valores: en 'rapido' baja el umbral y las confirmaciones para
ENCONTRAR mas entradas (mas señales, algo menos filtradas); en 'lento' sube todo
para operar SOLO con confluencia fuerte de muchos tiempos (menos señales, mas
seguras). 'normal' es el equilibrio. Sin red.
"""

from __future__ import annotations

from typing import Any, Dict

MODOS: Dict[str, Dict[str, Any]] = {
    # Mas entradas: convergencia liviana, 2 confirmaciones, rastreo rapido.
    "rapido": {"umbral_convergencia": 0.25, "min_tf_convergencia": 2,
               "min_confirmations": 2, "scan_interval": 15},
    # Equilibrio.
    "normal": {"umbral_convergencia": 0.35, "min_tf_convergencia": 3,
               "min_confirmations": 2, "scan_interval": 30},
    # Menos entradas, mas seguras: mucha convergencia y 3 confirmaciones.
    "lento":  {"umbral_convergencia": 0.55, "min_tf_convergencia": 4,
               "min_confirmations": 3, "scan_interval": 45},
}

MODO_DEFAULT = "rapido"


def params_modo(nombre: str) -> Dict[str, Any]:
    """Parametros del modo (copia). Nombre desconocido -> el default."""
    return dict(MODOS.get(str(nombre).lower(), MODOS[MODO_DEFAULT]))
