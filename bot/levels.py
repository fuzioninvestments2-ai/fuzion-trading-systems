"""
bot/levels.py
=============
Detecta niveles de SOPORTE (piso) y RESISTENCIA (techo) de las velas recientes.

EL PORQUÉ: el precio tiende a "rebotar" en zonas donde antes giró. Marcar esas
zonas ayuda a leer si estamos cerca de un techo (posible rechazo → PUT) o de un
piso (posible rebote → CALL). Es el "techo y piso" que pediste.

Método (sencillo y honesto): PIVOTES locales. Un pivote-alto es una vela cuyo
máximo es mayor que el de sus vecinas (un "pico"); un pivote-bajo, al revés (un
"valle"). Agrupamos pivotes cercanos para no dibujar mil líneas casi iguales, y
nos quedamos con las zonas más recientes/repetidas.

SRP: solo calcula niveles. Sin red. Determinista y testeable.
Trabaja sobre un DataFrame con columnas high/low/close.
"""


def _pivots_altos(high, izq=2, der=2):
    """Índices de velas cuyo máximo supera a sus `izq`/`der` vecinas (picos)."""
    out = []
    n = len(high)
    for i in range(izq, n - der):
        v = high[i]
        if all(v >= high[i - j] for j in range(1, izq + 1)) and \
           all(v >= high[i + j] for j in range(1, der + 1)):
            out.append(i)
    return out


def _pivots_bajos(low, izq=2, der=2):
    """Índices de velas cuyo mínimo es menor que sus vecinas (valles)."""
    out = []
    n = len(low)
    for i in range(izq, n - der):
        v = low[i]
        if all(v <= low[i - j] for j in range(1, izq + 1)) and \
           all(v <= low[i + j] for j in range(1, der + 1)):
            out.append(i)
    return out


def _agrupar(valores, tol):
    """
    Agrupa valores que estén a menos de `tol` (en precio) y devuelve el promedio
    de cada grupo. EL PORQUÉ: dos pivotes casi al mismo precio son el MISMO nivel;
    no queremos dibujar dos líneas pegadas.
    """
    if not valores:
        return []
    ordenados = sorted(valores)
    grupos = [[ordenados[0]]]
    for v in ordenados[1:]:
        if abs(v - grupos[-1][-1]) <= tol:
            grupos[-1].append(v)
        else:
            grupos.append([v])
    return [sum(g) / len(g) for g in grupos]


def detect_levels(df, izq=2, der=2, tol_pct=0.0008, max_niveles=3):
    """
    Devuelve dict {soportes: [precios], resistencias: [precios]}.

    izq/der   : cuántas velas a cada lado deben ser menores/mayores para que un
                punto cuente como pivote (mayor = pivotes más "fuertes").
    tol_pct   : tolerancia para agrupar niveles, como fracción del precio.
    max_niveles: máximo de líneas a devolver por lado (las más cercanas al precio
                actual, que son las relevantes ahora).
    """
    res = {"soportes": [], "resistencias": []}
    if df is None or len(df) < (izq + der + 1):
        return res

    high = [float(x) for x in df["high"]]
    low = [float(x) for x in df["low"]]
    price = float(df["close"].iloc[-1])
    tol = price * tol_pct

    resist = _agrupar([high[i] for i in _pivots_altos(high, izq, der)], tol)
    sop = _agrupar([low[i] for i in _pivots_bajos(low, izq, der)], tol)

    # Resistencias relevantes: las que están POR ENCIMA del precio (techo real),
    # ordenadas por cercanía. Soportes: las que están POR DEBAJO (piso real).
    resist_arriba = sorted([r for r in resist if r >= price],
                           key=lambda r: r - price)
    sop_abajo = sorted([s for s in sop if s <= price],
                       key=lambda s: price - s)

    # Si no hay por encima/debajo (precio en el extremo), usamos las más cercanas.
    res["resistencias"] = (resist_arriba or
                           sorted(resist, key=lambda r: abs(r - price)))[:max_niveles]
    res["soportes"] = (sop_abajo or
                       sorted(sop, key=lambda s: abs(s - price)))[:max_niveles]
    return res
