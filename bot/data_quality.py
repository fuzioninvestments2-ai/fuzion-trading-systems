"""
bot/data_quality.py
===================
BARRERA DE SEGURIDAD de datos. Reconoce series de velas BASURA (vacías, corruptas,
planas, con NaN) y las DESECHA antes de que el sistema las lea. Así se evitan
"sintonías absurdas": una lectura sobre datos degenerados que daría una señal sin
sentido y comprometería el proyecto.

Qué se considera basura (y por qué):
  - Pocas velas          -> no hay lectura fiable.
  - NaN en OHLC          -> hueco/corrupción; los indicadores darían basura.
  - Precio <= 0          -> imposible en un precio real.
  - high < low           -> vela corrupta (invertida).
  - Serie PLANA (rango ~0)-> todas las velas iguales: indicadores degenerados
                            (RSI sin definir, medias = precio) => señal absurda.
  - Saltos imposibles    -> un cambio >50% entre velas contiguas = dato roto.

Dos usos:
  1) En tiempo de análisis: frames_limpios() deja pasar SOLO los tiempos válidos.
  2) En el disco: escanear_datasets() encuentra los archivos basura para limpiarlos.

SRP: solo juzga calidad de datos. Sin red. Testeable con asserts.
"""

MIN_VELAS = 10           # por debajo de esto una temporalidad no se usa
SALTO_MAX = 0.5          # cambio relativo máximo entre velas contiguas (50%)


def calidad_serie(df, min_velas=MIN_VELAS):
    """
    Juzga una serie de velas OHLC. Devuelve (valida: bool, motivo: str).
    'valida' = los datos son sanos para leer indicadores; si no, es basura.
    """
    if df is None or len(df) < min_velas:
        n = 0 if df is None else len(df)
        return False, f"pocas velas ({n}<{min_velas})"
    for c in ("open", "high", "low", "close"):
        if c not in df.columns:
            return False, f"falta columna {c}"
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    # NaN en cualquier OHLC.
    if bool(o.isna().any() or h.isna().any() or l.isna().any() or c.isna().any()):
        return False, "valores NaN (hueco/corrupción)"
    # Precios no positivos.
    if bool((c <= 0).any() or (o <= 0).any()):
        return False, "precio <= 0 (imposible)"
    # Vela invertida (high por debajo de low).
    if bool((h < l).any()):
        return False, "high < low (vela corrupta)"
    # Serie PLANA: todas las velas prácticamente iguales -> degenerada.
    rango = float(c.max() - c.min())
    escala = abs(float(c.iloc[-1])) or 1.0
    if rango / escala <= 1e-6:
        return False, "serie plana (degenerada)"
    # Salto imposible entre velas contiguas (dato roto).
    cambios = (c.astype(float).diff().abs() / c.astype(float).shift().abs())
    if bool((cambios > SALTO_MAX).any()):
        return False, f"salto > {int(SALTO_MAX*100)}% entre velas (dato roto)"
    return True, "ok"


def frames_limpios(frames, min_velas=MIN_VELAS):
    """
    Filtra un dict {tf: df}: devuelve (limpios, descartados) donde `descartados`
    es {tf: motivo}. La barrera: al sistema solo entran tiempos VÁLIDOS.
    """
    limpios, descartados = {}, {}
    for tf, df in frames.items():
        valida, motivo = calidad_serie(df, min_velas)
        if valida:
            limpios[tf] = df
        else:
            descartados[tf] = motivo
    return limpios, descartados


# --------------------------- limpieza en disco ----------------------------

def _contar_filas_csv_gz(ruta):
    """Cuenta filas de datos (sin cabecera) de un .csv.gz. -1 si no se puede leer."""
    import gzip
    try:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            n = sum(1 for _ in f)
        return max(0, n - 1)                      # menos la cabecera
    except Exception:
        return -1


def escanear_datasets(carpeta, min_filas=MIN_VELAS):
    """
    Recorre los .csv.gz de una carpeta y devuelve la lista de BASURA:
    [{'archivo', 'filas', 'motivo'}] (vacíos, ilegibles o con < min_filas).
    NO borra nada: solo reconoce. Para borrar, usa limpiar_datasets().
    """
    import os
    basura = []
    if not os.path.isdir(carpeta):
        return basura
    for fn in sorted(os.listdir(carpeta)):
        if not fn.endswith(".csv.gz"):
            continue
        ruta = os.path.join(carpeta, fn)
        filas = _contar_filas_csv_gz(ruta)
        if filas < 0:
            basura.append({"archivo": fn, "filas": filas, "motivo": "ilegible"})
        elif filas < min_filas:
            basura.append({"archivo": fn, "filas": filas,
                           "motivo": f"pocas filas (<{min_filas})"})
    return basura


def limpiar_datasets(carpeta, min_filas=MIN_VELAS, borrar=False):
    """
    Encuentra archivos basura y (si borrar=True) los elimina. Devuelve la lista
    de basura encontrada. Por defecto NO borra (solo reporta), para no perder
    datos por accidente.
    """
    import os
    basura = escanear_datasets(carpeta, min_filas)
    if borrar:
        for b in basura:
            try:
                os.remove(os.path.join(carpeta, b["archivo"]))
            except OSError:
                pass
    return basura


def _main():
    """
    CLI: reporta (o limpia) archivos basura de datasets/.
      python -m bot.data_quality            # OTC, solo reporta
      python -m bot.data_quality real       # real, solo reporta
      python -m bot.data_quality otc --borrar  # OTC, BORRA la basura
    """
    import sys
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = [a.lower() for a in sys.argv[1:]]
    sub = "real" if "real" in args else "otc"
    borrar = "--borrar" in args
    carpeta = os.path.join(raiz, "datasets", sub)
    basura = limpiar_datasets(carpeta, borrar=borrar)
    if not basura:
        print(f"[{sub}] Sin archivos basura. Todo limpio.")
        return
    accion = "BORRADOS" if borrar else "encontrados (usa --borrar para eliminar)"
    print(f"[{sub}] {len(basura)} archivos basura {accion}:")
    for b in basura[:50]:
        print(f"  {b['archivo']}  ({b['filas']} filas, {b['motivo']})")
    if len(basura) > 50:
        print(f"  ... y {len(basura) - 50} más")


if __name__ == "__main__":
    _main()
