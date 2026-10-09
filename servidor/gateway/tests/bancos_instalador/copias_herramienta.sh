#!/usr/bin/env bash
# Herramienta cidia: copia de seguridad, rotación y restauración con Docker simulado.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

DIR=$BANCO/inst
detectar_dir
mkdir -p "$DIR_DESP/perfiles" "$DIR/secretos" "$DIR/datos/ficheros"
printf 'CIDIA_LLM_MODELO_CHAT=mi-modelo:8b\n' >"$DIR_DESP/perfiles/mi-planta.env"
printf 'CIDIA_PERFIL=mi-planta\nCIDIA_PUERTO=18700\nCIDIA_PG_PASSWORD=abc\n' >"$ENV_FILE"
echo "Usuario: admin" >"$DIR/secretos/admin-inicial.txt"
echo "manual v1" >"$DIR/datos/ficheros/manual.pdf"

# Docker simulado: un contenedor por servicio; pg_dump escribe un volcado reconocible y
# pg_restore guarda lo que recibe.
RESTAURADO=$BANCO/restaurado
docker() {
	case $1 in
	ps) echo cid123 ;;
	exec)
		shift
		if [[ $1 == -i || $1 == -it ]]; then shift; fi
		shift
		case $1 in
		psql) if [[ $* == *pg_database_size* ]]; then echo 4096; fi ;;
		pg_dump) echo "VOLCADO de la base" ;;
		pg_restore) cat >>"$RESTAURADO" ;;
		*) return 0 ;;
		esac
		;;
	*) return 0 ;;
	esac
}
dc() { :; }
esperar_salud() { return 0; }
SI=1

echo "== Copia con rotación (--conservar 2)"
mkdir -p "$COPIAS/cidia-20200101-000000" "$COPIAS/cidia-20200102-000000"
orden_copia --conservar 2 >/dev/null
mapfile -t copias < <(listar_copias)
comprobar "quedan 2 copias, las más recientes" '[[ ${#copias[@]} == 2 && ${copias[0]} == cidia-20200102-000000 ]]'
C=$COPIAS/${copias[1]}
comprobar "volcado de la base" '[[ $(cat "$C/cidia.dump") == "VOLCADO de la base" ]]'
comprobar "sin base de WeKnora no hay su volcado" '[[ ! -e $C/weknora.dump ]]'
comprobar "datos empaquetados" 'tar -tzf "$C/datos.tar.gz" | grep -q datos/ficheros/manual.pdf'
comprobar "configuración con los secretos" 'tar -tzf "$C/configuracion.tar.gz" | grep -q secretos/cidia.env'
comprobar "y con el perfil activo" 'tar -tzf "$C/configuracion.tar.gz" | grep -q perfiles/mi-planta.env'
comprobar "sin la contraseña inicial" '! tar -tzf "$C/configuracion.tar.gz" | grep -q admin-inicial'
comprobar "sumas de comprobación correctas" '(cd "$C" && sha256sum -c --quiet SHA256SUMS)'
comprobar "no queda la carpeta parcial" '[[ -z $(find "$COPIAS" -name ".*parcial") ]]'
falla "--conservar 0 rechazado" orden_copia --conservar 0

echo "== Restauración"
echo "manual v2" >"$DIR/datos/ficheros/manual.pdf"
orden_restaurar "${copias[1]}" --sin-copia >/dev/null
comprobar "pg_restore recibe el volcado" 'grep -q "VOLCADO de la base" "$RESTAURADO"'
comprobar "datos/ vuelve a la versión de la copia" '[[ $(cat "$DIR/datos/ficheros/manual.pdf") == "manual v1" ]]'
comprobar "la carpeta anterior se guarda" '[[ $(cat "$DIR"/datos.previo-*/ficheros/manual.pdf) == "manual v2" ]]'

# Una copia manipulada o inexistente no se restaura.
echo "otro" >"$C/cidia.dump"
falla "copia dañada rechazada" orden_restaurar "${copias[1]}" --sin-copia
falla "copia inexistente rechazada" orden_restaurar no-existe
terminar
