# shellcheck shell=bash
# Preparación común de los bancos de pruebas de servidor/despliegue (la usa
# tests/test_instalador_servidor.py): copia las funciones del script probado (todo menos la
# última línea, que llama a main) a un repositorio falso, las carga y sustituye Docker por una
# función que falla. Cada comprobación imprime «OK …» o «MAL …».
#
# Uso, desde un banco:  source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" <script>

SCRIPT_PROBADO=$1
BANCO=$(mktemp -d)
mkdir -p "$BANCO/repo/servidor/despliegue/perfiles" "$BANCO/repo/servidor/despliegue/modelos"
head -n -1 "$SCRIPT_PROBADO" >"$BANCO/repo/servidor/despliegue/lib.sh"
cp "$(dirname "$SCRIPT_PROBADO")"/perfiles/*.env "$BANCO/repo/servidor/despliegue/perfiles/"
cp "$(dirname "$SCRIPT_PROBADO")"/modelos/*.Modelfile "$BANCO/repo/servidor/despliegue/modelos/"
# shellcheck disable=SC1091
source "$BANCO/repo/servidor/despliegue/lib.sh"
trap 'rm -rf "$BANCO"' EXIT
trap - ERR

fallos=0
# comprobar "descripción" 'condición': la condición se evalúa en el momento de la llamada.
comprobar() {
	if eval "$2"; then
		echo "OK  $1"
	else
		echo "MAL $1"
		fallos=$((fallos + 1))
	fi
}
# falla "descripción" orden…: la orden (en una subshell) tiene que terminar con error.
falla() {
	local desc=$1
	shift
	if ("$@") >/dev/null 2>&1; then
		echo "MAL $desc"
		fallos=$((fallos + 1))
	else
		echo "OK  $desc"
	fi
}
terminar() {
	echo "Fallos: $fallos"
	exit "$fallos"
}
docker() { return 1; }

# En Git Bash (Windows) los permisos de Unix son una emulación y «mkdir -m 700» puede fallar
# dentro de una carpeta ya restringida: allí se crea la carpeta sin cambiar los permisos.
if [[ $(uname -o 2>/dev/null) == Msys ]]; then
	mkdir() {
		if [[ ${1:-} == -m ]]; then shift 2; fi
		command mkdir "$@"
	}
fi
