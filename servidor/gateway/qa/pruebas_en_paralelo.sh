#!/usr/bin/env bash
# Ejecuta la batería completa en 6 grupos en paralelo, cada uno con su base de datos de pruebas.
# Uso: qa/pruebas_en_paralelo.sh [carpeta_de_registros]
set -u
cd "$(dirname "$0")/.."
REG="${1:-_registros_pruebas}"
mkdir -p "$REG"
PY=".venv/Scripts/python"
[ -x "$PY" ] || PY=".venv/bin/python"
declare -A GRUPOS=(
  [g1]="tests/test_base.py tests/test_consulta.py tests/test_openai.py"
  [g2]="tests/test_documentos.py tests/test_weknora.py tests/test_aportaciones.py"
  [g3]="tests/test_captura.py tests/test_instrucciones.py"
  [g4]="tests/test_planta.py tests/test_formacion.py tests/test_iluo.py"
  [g5]="tests/test_evaluacion.py tests/test_progreso.py tests/test_admin.py tests/test_inicio.py"
  [g6]="tests/test_espacio.py tests/test_mcp.py tests/test_semilla.py tests/test_instalador_servidor.py"
)
for g in "${!GRUPOS[@]}"; do
  ( CIDIA_TEST_BD="par_$g" "$PY" -m pytest -q -p no:cacheprovider -rfE ${GRUPOS[$g]} > "$REG/$g.log" 2>&1; echo "$g fin $?" >> "$REG/estado.txt" ) &
done
wait
for g in $(printf '%s\n' "${!GRUPOS[@]}" | sort); do
  echo "== $g: $(tail -1 "$REG/$g.log")"
done
grep -h "^FAILED\|^ERROR" "$REG"/g*.log || echo "Sin fallos."
