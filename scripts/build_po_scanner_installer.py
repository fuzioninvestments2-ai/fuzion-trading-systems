#!/usr/bin/env python3
"""Genera el instalador PowerShell de PO Chart Scanner PRO desde tools/po-chart-scanner/.

El instalador es de un solo uso: se copia y pega en PowerShell y escribe la
extension completa en Documentos. Este script es la unica fuente de verdad:
los archivos viven en el repo y el .ps1 se deriva de ellos, asi que nunca
pueden quedar desincronizados.

  python3 scripts/build_po_scanner_installer.py [--check]

--check verifica que el .ps1 en disco corresponde a los archivos actuales
(util en CI) y no lo reescribe.
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "po-chart-scanner"
OUT = ROOT / "tools" / "po-chart-scanner" / "install-po-chart-scanner.ps1"
FOLDER = "PO-Chart-Scanner-PRO-v4.3"

HEADER = f"""# ============================================================
# INSTALADOR - PO Chart Scanner PRO v4.3.0 CONTRARIAN
# ANTI-MANIPULACION (OTC)
#
# USO (3 pasos):
#   1) Copia TODO este texto (Ctrl+A, Ctrl+C)
#   2) Abre PowerShell y pegalo (clic derecho), Enter
#   3) Chrome: chrome://extensions -> Cargar sin empaquetar ->
#      selecciona la carpeta creada en Documentos
#
# NO borra tus otras versiones: se crea una carpeta NUEVA.
#
# GENERADO AUTOMATICAMENTE por scripts/build_po_scanner_installer.py
# No lo edites a mano: edita tools/po-chart-scanner/ y regeneralo.
# ============================================================

$base = Join-Path ([Environment]::GetFolderPath('MyDocuments')) '{FOLDER}'
Write-Host 'Instalando en:' $base

$files = @{{
"""

FOOTER = """}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$ok = 0; $bad = @()
foreach ($k in $files.Keys) {
  $p = Join-Path $base $k
  $d = Split-Path $p -Parent
  if (!(Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  [System.IO.File]::WriteAllText($p, $files[$k], $utf8)
  # verificacion byte a byte
  $read = [System.IO.File]::ReadAllText($p)
  if ($read -eq $files[$k]) { $ok++ } else { $bad += $k }
}

# verificacion de sellos de integridad
$sealed = 0
foreach ($k in $files.Keys) {
  if ($k -like '*.js' -or $k -like '*.css') {
    $p = Join-Path $base $k
    $t = [System.IO.File]::ReadAllText($p)
    if ($t -match '\\[PO-PRO-OK:[a-zA-Z.-]+\\]') { $sealed++ }
  }
}

Write-Host ''
if ($bad.Count -eq 0) {
  Write-Host ('INSTALACION PERFECTA: ' + $ok + '/' + $files.Count + ' archivos verificados, ' + $sealed + ' sellos OK') -ForegroundColor Green
} else {
  Write-Host ('ERRORES en: ' + ($bad -join ', ')) -ForegroundColor Red
}
Write-Host 'Carpeta:' $base
Write-Host 'Ahora ve a chrome://extensions y Carga sin empaquetar esa carpeta.'
"""


def payload_files():
    """Archivos que entran en el instalador, en orden estable."""
    out = []
    for p in sorted(SRC.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(SRC).as_posix()
        if rel.endswith(".ps1") or rel.startswith("test/") or rel == "README.md":
            continue
        out.append((rel, p.read_text(encoding="utf-8")))
    return out


def build():
    parts = [HEADER]
    for rel, text in payload_files():
        # Un here-string de PowerShell termina en una linea que empieza por '@.
        # Si el contenido tuviera una, el script se romperia al pegarlo.
        for line in text.splitlines():
            if line.startswith("'@"):
                sys.exit(f"ERROR: {rel} contiene una linea que empieza por \"'@\" "
                         "y romperia el here-string de PowerShell.")
        if "'" in rel:
            sys.exit(f"ERROR: nombre de archivo con comilla simple: {rel}")
        # PowerShell descarta el salto de linea que precede al cierre '@,
        # asi que anadimos uno extra para conservar el del archivo original.
        parts.append(f"  '{rel}' = @'\n{text}\n'@\n")
    parts.append(FOOTER)
    return "".join(parts)


def parse(ps_text):
    """Extrae los archivos de un instalador generado (para el round-trip)."""
    files, lines, i = {}, ps_text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("  '") and line.endswith("= @'"):
            name = line.strip()[1:line.strip().index("' =")]
            body, i = [], i + 1
            while lines[i] != "'@":
                body.append(lines[i])
                i += 1
            # PowerShell descarta el salto de linea anterior al cierre
            files[name] = "\n".join(body)
        i += 1
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verifica que el .ps1 esta sincronizado; no escribe")
    args = ap.parse_args()

    ps = build()
    originals = dict(payload_files())

    # Round-trip: lo que el instalador escribiria == lo que hay en el repo
    parsed = parse(ps)
    if set(parsed) != set(originals):
        sys.exit("ERROR round-trip: faltan o sobran archivos "
                 f"{set(originals) ^ set(parsed)}")
    for name, text in originals.items():
        if parsed[name] != text:
            sys.exit(f"ERROR round-trip: el contenido de {name} no coincide")

    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != ps:
            sys.exit("ERROR: install-po-chart-scanner.ps1 esta desactualizado. "
                     "Ejecuta: python3 scripts/build_po_scanner_installer.py")
        print(f"OK: instalador sincronizado ({len(originals)} archivos)")
        return

    OUT.write_text(ps, encoding="utf-8")
    total = sum(len(t) for t in originals.values())
    print(f"Instalador generado: {OUT.relative_to(ROOT)}")
    print(f"  {len(originals)} archivos, {total} caracteres de payload")
    print(f"  round-trip verificado: byte a byte OK")


if __name__ == "__main__":
    main()
