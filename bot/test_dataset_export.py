"""
bot/test_dataset_export.py
=========================
Valida el roundtrip export -> import del historial (BD -> CSV.gz -> BD). Sin red.
"""

import os
import tempfile

from bot.history import HistoryRepository
from bot.dataset_export import export_db, import_db


def _repo_con_datos():
    repo = HistoryRepository(":memory:")
    velas = [{"timestamp": i * 60000, "open": 1.1 + i * 0.001, "high": 1.2,
              "low": 1.0, "close": 1.15, "volume": i} for i in range(30)]
    repo.record_many("EURUSD_otc", "M1", velas)
    repo.record_many("EURUSD_otc", "tf300", velas[:10])
    return repo


def test_roundtrip():
    out = tempfile.mkdtemp()
    origen = _repo_con_datos()
    n_files = export_db(origen, out_dir=out)
    assert n_files == 2                                   # M1 + tf300
    archivos = sorted(os.listdir(out))
    assert any(a.endswith(".csv.gz") for a in archivos)
    print(f"OK export -> {n_files} archivos: {archivos}")

    # Importar en una BD nueva y comparar conteos.
    destino = HistoryRepository(":memory:")
    total = import_db(destino, in_dir=out)
    assert total == 40                                    # 30 + 10
    assert destino.count("EURUSD_otc", "M1") == 30
    assert destino.count("EURUSD_otc", "tf300") == 10
    print(f"OK import -> {total} velas restauradas (M1=30, tf300=10)")


def test_import_dir_vacio_no_rompe():
    destino = HistoryRepository(":memory:")
    assert import_db(destino, in_dir=tempfile.mkdtemp()) == 0
    print("OK import de carpeta vacía -> 0, sin error")


def test_export_determinista_mismos_bytes():
    """
    La MISMA data exportada dos veces debe dar BYTES idénticos. Antes gzip metía
    la marca de tiempo y cambiaban en cada corrida -> git re-subía todo. Con
    mtime=0 el archivo no cambia si la serie no cambió.
    """
    origen = _repo_con_datos()
    out = tempfile.mkdtemp()
    export_db(origen, out_dir=out)
    ruta = os.path.join(out, "EURUSD_otc__M1.csv.gz")
    with open(ruta, "rb") as f:
        primero = f.read()
    mtime1 = os.path.getmtime(ruta)
    # Re-exportar la misma data: bytes idénticos y NO se reescribe el archivo.
    export_db(origen, out_dir=out)
    with open(ruta, "rb") as f:
        segundo = f.read()
    assert primero == segundo, "gzip no determinista: los bytes cambiaron"
    assert os.path.getmtime(ruta) == mtime1, "se reescribió sin cambios"
    print("OK export determinista: misma data -> mismos bytes, sin reescribir")


def test_export_cambia_si_cambia_la_data():
    """Si la serie SÍ cambia (más velas), el archivo debe actualizarse."""
    repo = HistoryRepository(":memory:")
    base = [{"timestamp": i * 60000, "open": 1.1, "high": 1.2, "low": 1.0,
             "close": 1.15, "volume": i} for i in range(30)]
    repo.record_many("EURUSD_otc", "M1", base)
    out = tempfile.mkdtemp()
    export_db(repo, out_dir=out)
    ruta = os.path.join(out, "EURUSD_otc__M1.csv.gz")
    with open(ruta, "rb") as f:
        antes = f.read()
    # Añadir velas nuevas y re-exportar: los bytes deben cambiar.
    extra = [{"timestamp": (30 + i) * 60000, "open": 1.1, "high": 1.2,
              "low": 1.0, "close": 1.16, "volume": i} for i in range(5)]
    repo.record_many("EURUSD_otc", "M1", extra)
    export_db(repo, out_dir=out)
    with open(ruta, "rb") as f:
        despues = f.read()
    assert antes != despues, "no se actualizó pese a cambiar la data"
    print("OK export actualiza el archivo cuando la data cambia")


if __name__ == "__main__":
    test_roundtrip()
    test_import_dir_vacio_no_rompe()
    test_export_determinista_mismos_bytes()
    test_export_cambia_si_cambia_la_data()
    print("\nTODOS OK — export/import de datasets")
