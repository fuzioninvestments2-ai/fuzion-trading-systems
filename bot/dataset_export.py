"""
bot/dataset_export.py
====================
Exporta/importa el historial (history.db) a archivos PORTABLES (CSV comprimido)
en la carpeta datasets/, para subirlo a GitHub (persistencia en la nube) y
reusarlo en otra máquina o en un VPS.

Flujo:
  1) En tu PC descargas el historial (DESCARGAR_HISTORIAL.bat) -> history.db.
  2) `python -m bot.dataset_export export`  -> datasets/*.csv.gz
  3) commit + push de datasets/ a GitHub (queda en la nube).
  4) En otra máquina: `python -m bot.dataset_export import` -> history.db.

Un archivo por (activo, temporalidad): datasets/{activo}__{tf}.csv.gz. Así solo
se re-suben los que cambian. Sin dependencias extra (gzip + csv estándar).

SRP: solo mueve datos entre la BD y archivos. Sin red.
"""

import csv
import gzip
import io
import os

_COLS = ["timestamp", "open", "high", "low", "close", "volume"]


def _datasets_dir():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "datasets")


def export_db(repo, out_dir=None):
    """Vuelca cada (activo, temporalidad) de la BD a un CSV.gz. Devuelve nº archivos."""
    out_dir = out_dir or _datasets_dir()
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for row in repo.assets_tracked():
        asset, tf = row["asset"], row["timeframe"]
        df = repo.get_recent(asset, tf, 10_000_000)      # todo lo que haya
        if df is None or len(df) == 0:
            continue
        safe = asset.replace("/", "-").replace(" ", "_")
        path = os.path.join(out_dir, f"{safe}__{tf}.csv.gz")
        with gzip.open(path, "wt", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_COLS)
            for _, r in df.iterrows():
                w.writerow([int(r["timestamp"]), r["open"], r["high"],
                            r["low"], r["close"], r.get("volume", 0)])
        n += 1
    return n


def import_db(repo, in_dir=None):
    """Carga los CSV.gz de datasets/ a la BD (INSERT OR REPLACE). Devuelve nº velas."""
    in_dir = in_dir or _datasets_dir()
    if not os.path.isdir(in_dir):
        return 0
    total = 0
    for fn in sorted(os.listdir(in_dir)):
        if not fn.endswith(".csv.gz") or "__" not in fn:
            continue
        base = fn[:-len(".csv.gz")]
        safe, tf = base.rsplit("__", 1)
        asset = safe.replace("-", "/")                   # aprox inverso legible
        velas = []
        with gzip.open(os.path.join(in_dir, fn), "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    velas.append({"timestamp": int(r["timestamp"]),
                                  "open": float(r["open"]), "high": float(r["high"]),
                                  "low": float(r["low"]), "close": float(r["close"]),
                                  "volume": float(r.get("volume", 0) or 0)})
                except (TypeError, ValueError, KeyError):
                    continue
        if velas:
            repo.record_many(asset, tf, velas)
            total += len(velas)
    return total


def _main():
    """
    CLI por bot (para no mezclar en la nube):
      python -m bot.dataset_export export OTC   -> history.db     -> datasets/otc/
      python -m bot.dataset_export export REAL  -> history_real.db-> datasets/real/
      python -m bot.dataset_export import REAL   (a la inversa)
    Sin perfil usa la history.db común y datasets/ (compatibilidad).
    """
    import sys
    from bot.history import HistoryRepository
    modo = sys.argv[1] if len(sys.argv) > 1 else "export"
    perfil = sys.argv[2] if len(sys.argv) > 2 else None
    if perfil:
        from bot.profiles import get_profile
        p = get_profile(perfil)
        db_path, carpeta, etiqueta = p.db_path, p.datasets_dir, p.titulo
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path, carpeta, etiqueta = (os.path.join(root, "history.db"),
                                      _datasets_dir(), "comun")
    repo = HistoryRepository(db_path)
    if modo == "import":
        n = import_db(repo, in_dir=carpeta)
        print(f"[{etiqueta}] Importadas {n} velas desde {carpeta}")
    else:
        n = export_db(repo, out_dir=carpeta)
        print(f"[{etiqueta}] Exportados {n} archivos a {carpeta} "
              f"(commit + push para la nube)")


if __name__ == "__main__":
    _main()
