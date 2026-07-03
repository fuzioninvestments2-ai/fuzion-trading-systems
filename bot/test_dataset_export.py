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


if __name__ == "__main__":
    test_roundtrip()
    test_import_dir_vacio_no_rompe()
    print("\nTODOS OK — export/import de datasets")
