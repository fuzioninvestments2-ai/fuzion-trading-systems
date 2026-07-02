"""
bot/payout.py
=============
Extrae el % de PAGO (payout) de un activo desde la lista `updateAssets` de
Pocket Option, de forma ROBUSTA.

EL PROBLEMA: el formato de cada activo en `updateAssets` es un array posicional
y el índice exacto del payout NO está documentado públicamente; puede variar.
Coger a[5] "a ciegas" es frágil: si esa posición trae un id o una bandera, el
filtro de "pago bajo" del usuario falla justo cuando más importa.

LA SOLUCIÓN (honesta): un payout es un PORCENTAJE, así que TIENE que caer en un
rango sensato. Validamos por rango en vez de confiar en una posición fija:
  1) Probamos primero el índice observado (best-effort).
  2) Si no es un payout plausible, ESCANEAMOS el resto de campos numéricos y nos
     quedamos con el mejor candidato dentro del rango de payout.
Así, aunque PO reordene el array, seguimos encontrando el pago correcto.

SRP: solo parsea. Sin red. Determinista y testeable.
"""

# Rango plausible de un payout de opción binaria (en %). Por debajo de MIN no es
# un pago real (sería un flag/porcentaje raro); por encima de MAX es imposible.
PAYOUT_MIN = 20
PAYOUT_MAX = 100

# Índices donde se ha observado el payout (se prueban en orden). Best-effort.
_INDICES_PREFERIDOS = (5, 3, 4, 6)


def _es_payout_plausible(v):
    """True si `v` parece un payout (%): número finito dentro del rango."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if f != f:                      # NaN
        return False
    return PAYOUT_MIN <= f <= PAYOUT_MAX


def extract_payout(asset_entry):
    """
    Devuelve el payout (%) de un activo (`asset_entry` = un elemento de la lista
    updateAssets) o None si no se encuentra uno plausible.

    Prefiere los índices observados; si ninguno es plausible, escanea el array y
    escoge el candidato más ALTO dentro del rango (el payout suele ser el número
    "grande" del bloque; ids y flags quedan fuera de rango o son más pequeños).
    """
    if not isinstance(asset_entry, (list, tuple)):
        return None

    # 1) Índices preferidos (rápido y estable si PO no cambió el formato).
    for i in _INDICES_PREFERIDOS:
        if i < len(asset_entry) and _es_payout_plausible(asset_entry[i]):
            return float(asset_entry[i])

    # 2) Fallback: escanear campos numéricos y quedarnos con el mayor plausible.
    candidatos = [float(v) for v in asset_entry if _es_payout_plausible(v)]
    if candidatos:
        return max(candidatos)
    return None


def parse_assets(assets):
    """
    Recorre la lista completa `updateAssets` y devuelve {symbol: payout}.
    Cada activo: [id, "SYMBOL", "Nombre", ...]; usamos el campo string como clave
    (símbolo tipo 'EURUSD_otc'). Ignora entradas sin símbolo o sin payout.
    """
    out = {}
    if not isinstance(assets, list):
        return out
    for a in assets:
        if not isinstance(a, (list, tuple)) or len(a) < 2:
            continue
        # El símbolo es el primer campo string del bloque (normalmente a[1]).
        symbol = None
        for v in a[1:]:
            if isinstance(v, str) and v:
                symbol = v
                break
        if symbol is None:
            continue
        payout = extract_payout(a)
        if payout is not None:
            out[symbol] = payout
    return out
