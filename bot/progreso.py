"""
bot/progreso.py
===============
Reporte RÁPIDO del progreso de la descarga (solo LEE la base, no toca el robot ni
la cuenta de Pocket Option). Muestra cuántos activos ya tienen historial completo.

Uso (en una PowerShell nueva, dentro de la carpeta del proyecto):
  python -m bot.progreso          # OTC (history.db)
  python -m bot.progreso real     # mercado real (history_real.db)

"Completo" = >= 5000 velas M1 (lo que sirve Pocket Option hacia atrás).
"""

COMPLETO_M1 = 5000


def _reporte(db_path, etiqueta):
    from bot.history import HistoryRepository
    repo = HistoryRepository(db_path)
    activos = sorted({fila["asset"] for fila in repo.assets_tracked()})
    if not activos:
        print(f"[{etiqueta}] Aún no hay datos guardados.")
        return
    completos = [a for a in activos if repo.count(a, "M1") >= COMPLETO_M1]
    parciales = len(activos) - len(completos)
    print(f"[{etiqueta}] Activos vistos: {len(activos)}")
    print(f"  Completos (>=5000 velas 1m): {len(completos)}")
    print(f"  En progreso / parciales:     {parciales}")
    # Muestra los últimos 5 activos con más velas (los más avanzados).
    top = sorted(activos, key=lambda a: repo.count(a, "M1"), reverse=True)[:5]
    print("  Más avanzados:")
    for a in top:
        print(f"    {a}: {repo.count(a, 'M1')} velas 1m")


def _main():
    import sys
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1 and sys.argv[1].lower() == "real":
        _reporte(os.path.join(raiz, "history_real.db"), "REAL")
    else:
        _reporte(os.path.join(raiz, "history.db"), "OTC")


if __name__ == "__main__":
    _main()
