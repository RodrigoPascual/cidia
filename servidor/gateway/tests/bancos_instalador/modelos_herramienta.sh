#!/usr/bin/env bash
# Herramienta cidia: modelos derivados (el de búsqueda con contexto propio) con Ollama simulado.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

DIR=$BANCO/inst
detectar_dir
mkdir -p "$DIR_DESP/perfiles" "$DIR_DESP/modelos" "$DIR/secretos"
cp "$BANCO/repo/servidor/despliegue/perfiles/msi.env" "$DIR_DESP/perfiles/"
cp "$BANCO/repo/servidor/despliegue/modelos/"*.Modelfile "$DIR_DESP/modelos/"
printf 'CIDIA_PERFIL=msi\nCIDIA_PUERTO=18700\n' >"$ENV_FILE"
calcular_urls
CID=cid-ollama # lo pone «necesitar ollama» en orden_modelos

# Ollama simulado en el contenedor «cid-ollama» (postgres no está en marcha: solo cuenta el perfil).
# MODELOS son los modelos que tiene; PARAMETROS, los PARAMETER de cada uno; «ollama create» guarda
# el Modelfile que recibe por la entrada. Las llamadas a docker exec se anotan en LLAMADAS.
LLAMADAS=$BANCO/llamadas
RECIBIDO=$BANCO/modelfile-recibido
MODELOS="ministral-3:8b"
declare -A PARAMETROS=()
CREAR_FALLA=0
OLLAMA_EN_MARCHA=1
DERIVADO=qwen3-embedding-cidia:0.6b
BASE=qwen3-embedding:0.6b
docker() {
	local a m
	case $1 in
	ps)
		for a in "$@"; do
			if [[ $a == label=com.docker.compose.service=ollama ]] && ((OLLAMA_EN_MARCHA)); then echo cid-ollama; fi
		done
		;;
	exec)
		shift
		if [[ $1 == -i || $1 == -it ]]; then shift; fi
		echo "exec $*" >>"$LLAMADAS"
		shift
		case "$1 $2" in
		"ollama list")
			echo "NAME ID SIZE MODIFIED"
			for m in $MODELOS; do echo "$m abc 639 MB 2 days ago"; done
			;;
		"ollama show")
			m=${*: -1}
			[[ " $MODELOS " == *" $m "* ]] || return 1
			if [[ $3 == --parameters && -n ${PARAMETROS[$m]:-} ]]; then
				# shellcheck disable=SC2086  # «clave valor» en dos columnas, como Ollama
				printf '%-30s %s\n' ${PARAMETROS[$m]}
			fi
			;;
		"ollama pull") MODELOS+=" $3" ;;
		"ollama create")
			((!CREAR_FALLA)) || return 1
			cat >"$RECIBIDO"
			[[ " $MODELOS " == *" $3 "* ]] || MODELOS+=" $3"
			PARAMETROS[$3]=$(awk 'toupper($1) == "PARAMETER" { print $2, $3 }' "$RECIBIDO")
			;;
		esac
		;;
	*) return 0 ;;
	esac
}
curl() { return 0; }
dc() { :; }
esperar_salud() { return 0; }
SI=1
llamadas() { grep -c "$1" "$LLAMADAS" || true; }

echo "== Definición del derivado"
F=$(modelfile_de "$DERIVADO")
comprobar "el de búsqueda del perfil msi es un derivado" '[[ $(leer_var "$DIR_DESP/perfiles/msi.env" CIDIA_LLM_MODELO_EMBEDDINGS) == "$DERIVADO" && -f $F ]]'
comprobar "el nombre sigue conteniendo qwen3-embedding (instrucción de las preguntas)" '[[ $DERIVADO == *qwen3-embedding* ]]'
comprobar "los del registro no son derivados" '! modelfile_de ministral-3:8b >/dev/null && ! modelfile_de "$BASE" >/dev/null'
comprobar "parte de qwen3-embedding:0.6b" '[[ $(base_de "$F") == "$BASE" ]]'
comprobar "con contexto de 4096" 'grep -qx "PARAMETER num_ctx 4096" "$F"'
comprobar "perfil: el derivado" '[[ $(modelos_del_perfil | paste -sd " ") == "ministral-3:8b $DERIVADO" ]]'
comprobar "necesarios: también la base" '[[ $(modelos_necesarios | sort | paste -sd " ") == "$(printf "%s\n" ministral-3:8b "$DERIVADO" "$BASE" | sort | paste -sd " ")" ]]'

echo "== modelos descargar en una instalación nueva"
: >"$LLAMADAS"
modelos_descargar >"$BANCO/salida" 2>&1
comprobar "descarga la base" 'grep -qx "exec cid-ollama ollama pull $BASE" "$LLAMADAS"'
comprobar "no intenta descargar el derivado" '[[ $(llamadas "pull $DERIVADO") == 0 ]]'
comprobar "crea el derivado con el Modelfile por la entrada" 'grep -qx "exec cid-ollama ollama create $DERIVADO -f /dev/stdin" "$LLAMADAS" && cmp -s "$RECIBIDO" "$F"'
comprobar "primero la base y después el derivado" '(($(grep -n "pull $BASE" "$LLAMADAS" | cut -d: -f1) < $(grep -n "create $DERIVADO" "$LLAMADAS" | cut -d: -f1)))'
comprobar "lo cuenta" 'grep -q "$DERIVADO creado a partir de $BASE (num_ctx 4096)" "$BANCO/salida"'

echo "== modelos descargar otra vez"
: >"$LLAMADAS"
modelos_descargar >"$BANCO/salida" 2>&1
comprobar "nada que hacer" 'grep -q "ya están descargados" "$BANCO/salida" && [[ $(llamadas "pull\|create") == 0 ]]'
modelos_descargar "$DERIVADO" >"$BANCO/salida" 2>&1
comprobar "pedido a mano y ya creado" 'grep -q "$DERIVADO ya está creado" "$BANCO/salida" && [[ $(llamadas "pull\|create") == 0 ]]'

echo "== Derivado con otro contexto (Modelfile cambiado o creado a mano)"
PARAMETROS[$DERIVADO]="num_ctx 32768"
: >"$LLAMADAS"
modelos_descargar >"$BANCO/salida" 2>&1
comprobar "lo vuelve a crear sin descargar nada" '[[ $(llamadas "create $DERIVADO") == 1 && $(llamadas pull) == 0 ]]'
comprobar "y queda con 4096" '[[ ${PARAMETROS[$DERIVADO]} == "num_ctx 4096" ]]'

echo "== arrancar crea el derivado si falta y ya está la base (sin red)"
MODELOS="ministral-3:8b $BASE"
unset 'PARAMETROS[$DERIVADO]'
: >"$LLAMADAS"
orden_arrancar >"$BANCO/salida" 2>&1
comprobar "lo crea" '[[ $(llamadas "create $DERIVADO") == 1 ]] && grep -q "$DERIVADO creado" "$BANCO/salida"'
comprobar "sin descargar nada" '[[ $(llamadas pull) == 0 ]]'
: >"$LLAMADAS"
preparar_derivados >"$BANCO/salida" 2>&1
comprobar "al día: no hace nada ni dice nada" '[[ $(llamadas create) == 0 && ! -s $BANCO/salida ]]'

echo "== Sin la base, arrancar avisa pero no descarga ni falla"
MODELOS="ministral-3:8b"
: >"$LLAMADAS"
rc=0
preparar_derivados >"$BANCO/salida" 2>&1 || rc=$?
comprobar "no falla" '[[ $rc == 0 ]]'
comprobar "dice qué falta y cómo arreglarlo" 'grep -q "Falta $BASE, del que se crea $DERIVADO" "$BANCO/salida" && grep -q "cidia modelos descargar" "$BANCO/salida"'
comprobar "sin descargas ni creaciones" '[[ $(llamadas "pull\|create") == 0 ]]'

echo "== Fallos al crear"
MODELOS="ministral-3:8b $BASE"
CREAR_FALLA=1
rc=0
preparar_derivados >"$BANCO/salida" 2>&1 || rc=$?
comprobar "arrancar sigue" '[[ $rc == 0 ]] && grep -q "No se ha podido crear $DERIVADO" "$BANCO/salida"'
falla "modelos descargar termina con error" modelos_descargar
CREAR_FALLA=0
OLLAMA_EN_MARCHA=0
: >"$LLAMADAS"
comprobar "sin Ollama en marcha no hace nada" 'preparar_derivados >/dev/null 2>&1 && [[ ! -s $LLAMADAS ]]'
OLLAMA_EN_MARCHA=1

echo "== Listado y borrado"
CID=cid-ollama
modelos_descargar >/dev/null 2>&1
modelos_listar >"$BANCO/salida" 2>&1
comprobar "el derivado es del perfil" 'grep -q "$DERIVADO .* perfil" "$BANCO/salida"'
comprobar "la base no sale como ajena" 'grep -q "$BASE .* base de un modelo derivado" "$BANCO/salida"'
falla "no borra la base sin --forzar" modelos_borrar "$BASE"
falla "ni el derivado" modelos_borrar "$DERIVADO"
terminar
