"""
core/modos.py (fuzion_fx)
=========================
MODOS de operacion: la MISMA maquina, con mas o menos exigencia, para que el
usuario elija CARACTER — buscar muchas entradas (rapido) o pocas y mas seguras
(lento). Un solo lugar define los parametros de cada modo; el bot los aplica en
vivo (se puede cambiar desde el panel sin reiniciar).

Parametros por modo (la exigencia se controla por CONVERGENCIA, NO por
min_confirmations: ese queda en 2 por config, porque el motor tiene solo 4
indicadores votantes y exigir 3 lo deja casi mudo — medido 0.6%):
  umbral_convergencia -> cuanto tienen que coincidir las temporalidades (0..1).
  min_tf_convergencia -> cuantas temporalidades con dato hacen falta para exigir
                         la foto completa (si hay menos, cae al motor de 1 tf).
  scan_interval       -> cada cuantos segundos rastrea (mas chico = mas energia).

PORQUE los valores: en 'rapido' baja el umbral y pide menos tiempos para
ENCONTRAR mas entradas (mas señales); en 'lento' sube el umbral y pide muchos
tiempos alineados para operar SOLO con confluencia fuerte (menos, mas seguras).
La calidad la da la FOTO COMPLETA, no aflojar/apretar el motor de una tf. Sin red.
"""

from __future__ import annotations

from typing import Any, Dict

# 'convergencia' = cuanto MANDA la foto completa sobre el disparo de una tf:
#   "info"          -> NO bloquea; solo muestra la confluencia (rapido: mas señales).
#   "no_contradice" -> bloquea solo si la foto va en direccion OPUESTA (normal).
#   "confirma"      -> exige que la foto APOYE la misma direccion (lento: mas seguro).
MODOS: Dict[str, Dict[str, Any]] = {
    # Mas entradas: la convergencia informa pero NO frena (mercado real es ruidoso;
    # exigir foto perfecta dejaba todo mudo). Rastreo rapido.
    "rapido": {"umbral_convergencia": 0.25, "min_tf_convergencia": 2,
               "convergencia": "info", "scan_interval": 15},
    # Equilibrio: no opera contra la foto completa.
    "normal": {"umbral_convergencia": 0.40, "min_tf_convergencia": 3,
               "convergencia": "no_contradice", "scan_interval": 30},
    # Menos entradas, mas seguras: la foto DEBE confirmar la direccion.
    "lento":  {"umbral_convergencia": 0.60, "min_tf_convergencia": 4,
               "convergencia": "confirma", "scan_interval": 45},
}

MODO_DEFAULT = "rapido"


def params_modo(nombre: str) -> Dict[str, Any]:
    """Parametros del modo (copia). Nombre desconocido -> el default."""
    return dict(MODOS.get(str(nombre).lower(), MODOS[MODO_DEFAULT]))
