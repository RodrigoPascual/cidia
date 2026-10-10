#!/usr/bin/env bash
# Ejecuta TODA la batería (tests/test_*.py) en N grupos en paralelo, cada uno con su base de datos
# de pruebas. Los ficheros se reparten por tamaño para equilibrar los grupos.
# Uso: qa/pruebas_en_paralelo.sh [grupos] [carpeta_de_registros]
# Las bases se llaman cidia_t_<prefijo>_gN; el prefijo es CIDIA_TEST_BD (por defecto «par»), para
# que dos sesiones puedan pasar la batería a la vez sin borrarse las bases.
set -u
cd "$(dirname "$0")/.."
N="${1:-6}"
REG="${2:-_registros_pruebas}"
PREFIJO="${CIDIA_TEST_BD:-par}"
rm -rf "$REG"; mkdir -p "$REG"
PY=".venv/Scripts/python"
[ -x "$PY" ] || PY=".venv/bin/python"

# Reparto voraz: el fichero más grande al grupo con menos carga.
"$PY" - "$N" "$REG" <<'FIN'
import os, sys, glob
n, reg = int(sys.argv[1]), sys.argv[2]
ficheros = sorted(glob.glob("tests/test_*.py"), key=os.path.getsize, reverse=True)
grupos = [[0, []] for _ in range(n)]
for f in ficheros:
    g = min(grupos, key=lambda x: x[0])
    g[0] += os.path.getsize(f)
    g[1].append(f)
for i, (_, fs) in enumerate(grupos, start=1):
    open(os.path.join(reg, f"g{i}.lista"), "w").write(" ".join(fs))
FIN

for lista in "$REG"/g*.lista; do
  g=$(basename "$lista" .lista)
  ( CIDIA_TEST_BD="${PREFIJO}_$g" "$PY" -m pytest -q -p no:cacheprovider -rfE $(cat "$lista") > "$REG/$g.log" 2>&1
    echo "$g fin $?" >> "$REG/estado.txt" ) &
done
wait
for lista in "$REG"/g*.lista; do
  g=$(basename "$lista" .lista)
  echo "== $g: $(tail -1 "$REG/$g.log")"
done
grep -h "^FAILED\|^ERROR" "$REG"/g*.log || echo "Sin fallos."
