#!/usr/bin/env bash
# instalar-servidor.sh: deja un equipo con Ubuntu 22.04 o 24.04 (amd64 o arm64) listo como
# servidor CidIA. Sirve para el portátil MSI con GPU NVIDIA, para el servidor de pruebas ARM
# y para cualquier PC o servidor de una empresa.
#
#   sudo bash instalar-servidor.sh                 instalación guiada (pregunta lo necesario)
#   bash instalar-servidor.sh --comprobar          solo comprueba el equipo y la instalación
#   sudo bash instalar-servidor.sh --desinstalar   borra CidIA de este equipo (pide confirmación)
#
# Qué hace: comprueba el equipo; instala Docker Engine desde el repositorio oficial de Docker
# y, si hay GPU NVIDIA, el NVIDIA Container Toolkit desde el repositorio oficial de NVIDIA;
# prepara <dir>/{cidia,datos,secretos,registros,copias}; genera los secretos sin mostrarlos;
# construye y arranca los servicios con docker compose; descarga los modelos del perfil; crea
# la cuenta de administración y muestra la dirección para el instalador de los portátiles.
#
# Es idempotente: se puede volver a ejecutar sin perder datos ni secretos. Solo toca el
# proyecto de Docker Compose «cidia»: nunca usa 'docker system prune' ni otros contenedores.
# Todo lo que hace queda en <dir>/registros/instalacion-FECHA.log.

set -Eeuo pipefail
umask 022
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}

SCRIPT=$(readlink -f "${BASH_SOURCE[0]}")
DIR_SCRIPT=$(dirname "$SCRIPT")
REPO_ORIGEN=$(cd "$DIR_SCRIPT/../.." && pwd) # copia del repositorio desde la que se ejecuta
ARGS_ORIGINALES=("$@")
PROYECTO=cidia
ETIQUETA="label=com.docker.compose.project=$PROYECTO"
UID_DATOS=1000 # usuario de los contenedores gateway y asr
PUERTO_DEFECTO=18700
SOCKET_DOCKER=/var/run/docker.sock  # su grupo lo necesita el servicio espacio-trabajo
ENLACE_CIDIA=/usr/local/bin/cidia    # orden de administración en el PATH
FECHA_INICIO=$(date +%Y%m%d-%H%M%S)

# ----------------------------------------------------------------------------- opciones

MODO=instalar # instalar | comprobar | desinstalar
PERFIL="" DIR="" DIRECCION="" PUERTO="" PUBLICAR="" REPO_URL="" RAMA=""
CON_WEKNORA=0 CON_ESPACIO=0 SIN_MODELOS=0 SIN_GPU=0 SIN_ENERGIA=0 SI=0

uso() {
	cat <<'EOF'
Instalador del servidor CidIA (Ubuntu 22.04/24.04, amd64 o arm64)

Uso: sudo bash instalar-servidor.sh [opciones]

  --perfil NOMBRE   msi (GPU NVIDIA 12-16 GB), generico (cualquier PC sin GPU) u oracle
                    (pruebas en ARM). Sin esta opción se propone según el equipo.
  --dir CARPETA     carpeta de la instalación (por defecto /opt/cidia)
  --ip DIRECCION    IP o nombre con el que los portátiles llegarán al servidor
  --puerto N        puerto del servidor CidIA (por defecto 18700)
  --lan             publicar CidIA en la red local (0.0.0.0)
  --solo-local      publicar solo en este equipo (127.0.0.1)
  --con-weknora     activar también WeKnora (motor de conocimiento opcional)
  --con-espacio     activar el espacio de trabajo aislado del agente
  --sin-modelos     no descargar los modelos ahora (luego: sudo cidia modelos descargar)
  --sin-gpu         no usar la GPU aunque exista
  --sin-ajustes-energia  no ofrecer desactivar la suspensión del equipo
  --repo URL        clonar el código con git en lugar de copiar esta carpeta (--rama RAMA)
  --si              aceptar las respuestas propuestas sin preguntar
  --comprobar       solo comprobaciones: no instala ni cambia nada
  --desinstalar     parar y borrar todo lo de CidIA de este equipo (pide confirmación)
  -h, --ayuda       esta ayuda

Después de instalar, la administración diaria se hace con: sudo cidia ayuda
EOF
}

leer_opciones() {
	local valor
	while (($#)); do
		valor=""
		case $1 in
		--*=*) valor=${1#*=} ;;
		esac
		case $1 in
		--perfil | --perfil=*) PERFIL=${valor:-${2:?falta el perfil}} ;;
		--dir | --dir=*) DIR=${valor:-${2:?falta la carpeta}} ;;
		--ip | --ip=*) DIRECCION=${valor:-${2:?falta la dirección}} ;;
		--puerto | --puerto=*) PUERTO=${valor:-${2:?falta el puerto}} ;;
		--repo | --repo=*) REPO_URL=${valor:-${2:?falta la URL del repositorio}} ;;
		--rama | --rama=*) RAMA=${valor:-${2:?falta la rama}} ;;
		--lan) PUBLICAR=lan ;;
		--solo-local) PUBLICAR=local ;;
		--con-weknora) CON_WEKNORA=1 ;;
		--con-espacio) CON_ESPACIO=1 ;;
		--sin-modelos) SIN_MODELOS=1 ;;
		--sin-gpu) SIN_GPU=1 ;;
		--sin-ajustes-energia) SIN_ENERGIA=1 ;;
		--si | -y) SI=1 ;;
		--comprobar) MODO=comprobar ;;
		--desinstalar) MODO=desinstalar ;;
		-h | --ayuda | --help)
			uso
			exit 0
			;;
		*)
			printf 'Opción desconocida: %s\n\n' "$1" >&2
			uso >&2
			exit 2
			;;
		esac
		# Las opciones con valor en forma «--opcion valor» consumen también el siguiente argumento.
		case $1 in
		--perfil | --dir | --ip | --puerto | --repo | --rama) shift ;;
		esac
		shift
	done
}

# ----------------------------------------------------------------------------- mensajes y registro

if [[ -t 1 && -z ${NO_COLOR:-} && ${TERM:-dumb} != dumb ]]; then
	C_R=$'\e[0m' C_N=$'\e[1m' C_T=$'\e[2m' C_ROJO=$'\e[31m' C_VERDE=$'\e[32m' C_AMAR=$'\e[33m' C_AZUL=$'\e[34m' C_CIAN=$'\e[36m'
	TTY_SALIDA=1
else
	C_R='' C_N='' C_T='' C_ROJO='' C_VERDE='' C_AMAR='' C_AZUL='' C_CIAN=''
	TTY_SALIDA=0
fi
INTERACTIVO=0
if [[ -t 0 && -t 1 ]]; then INTERACTIVO=1; fi

REGISTRO="" # fichero de registro (primero en /tmp; al crear la carpeta se mueve a registros/)
PASO=0
PASOS_TOTAL=10
ERRORES=0
AVISOS=()

reg() { if [[ -n $REGISTRO ]]; then printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$REGISTRO" 2>/dev/null || true; fi; }
paso() {
	PASO=$((PASO + 1))
	printf '\n%s[%d/%d] %s%s\n' "$C_N$C_AZUL" "$PASO" "$PASOS_TOTAL" "$*" "$C_R"
	reg "== [$PASO/$PASOS_TOTAL] $*"
}
ok() {
	printf '  %s✔%s %s\n' "$C_VERDE" "$C_R" "$*"
	reg "OK    $*"
}
info() {
	printf '  %s•%s %s\n' "$C_CIAN" "$C_R" "$*"
	reg "INFO  $*"
}
aviso() {
	printf '  %s!%s %s\n' "$C_AMAR" "$C_R" "$*"
	reg "AVISO $*"
	AVISOS+=("$*")
}
fallo() {
	printf '  %s✘%s %s\n' "$C_ROJO" "$C_R" "$*" >&2
	reg "ERROR $*"
	ERRORES=$((ERRORES + 1))
}
tenue() {
	printf '    %s%s%s\n' "$C_T" "$*" "$C_R"
	reg "      $*"
}
morir() {
	fallo "$*"
	if [[ -n $REGISTRO ]]; then printf '\n  Registro completo: %s\n' "$REGISTRO" >&2; fi
	exit 1
}
# Solo informa de fallos dentro de funciones: si lo que falla es la llamada final a main, el
# motivo ya se ha mostrado.
# shellcheck disable=SC2329  # se invoca desde la trampa ERR
error_inesperado() {
	((${#FUNCNAME[@]} > 2)) || return 0
	printf '\n  %s✘ Error inesperado en la línea %s:%s %s\n' "$C_ROJO" "$1" "$C_R" "$2" >&2
	reg "ERROR inesperado en la línea $1: $2"
	if [[ -n $REGISTRO ]]; then printf '  Registro completo: %s\n' "$REGISTRO" >&2; fi
}
trap 'error_inesperado "$LINENO" "$BASH_COMMAND"' ERR

# preguntar VARIABLE "texto" "valor propuesto": sin terminal o con --si se queda la propuesta.
preguntar() {
	local __var=$1 texto=$2 propuesta=${3:-} resp=""
	if ((SI || !INTERACTIVO)); then
		printf -v "$__var" '%s' "$propuesta"
		reg "PREGUNTA $texto -> $propuesta (automático)"
		return 0
	fi
	read -r -p "  ? $texto${propuesta:+ [$propuesta]}: " resp || true
	printf -v "$__var" '%s' "${resp:-$propuesta}"
	reg "PREGUNTA $texto -> ${resp:-$propuesta}"
}

# confirmar "pregunta" s|n -> 0 si la respuesta es sí. Con --si, sí; sin terminal, lo propuesto.
confirmar() {
	local texto=$1 defecto=${2:-s} resp pista="[S/n]"
	if [[ $defecto == n ]]; then pista="[s/N]"; fi
	if ((SI)); then
		reg "PREGUNTA $texto -> sí (--si)"
		return 0
	fi
	if ((!INTERACTIVO)); then
		reg "PREGUNTA $texto -> $defecto (sin terminal)"
		[[ $defecto == s ]]
		return
	fi
	read -r -p "  ? $texto $pista " resp || true
	resp=${resp:-$defecto}
	reg "PREGUNTA $texto -> $resp"
	[[ ${resp,,} == s* || ${resp,,} == y* ]]
}

# ejecutar "descripción" orden…: guarda la salida en el registro y muestra un indicador con
# el tiempo transcurrido. Si falla, enseña las últimas líneas del registro y devuelve 1.
ejecutar() {
	local desc=$1 pid t0=$SECONDS i=0 marcos=$'|/-\\' rc=0
	shift
	reg "\$ $*"
	if ((TTY_SALIDA)); then
		(
			trap - ERR
			"$@"
		) >>"$REGISTRO" 2>&1 &
		pid=$!
		while kill -0 "$pid" 2>/dev/null; do
			printf '\r  %s %s %s(%d s)%s' "${marcos:i++%4:1}" "$desc" "$C_T" "$((SECONDS - t0))" "$C_R"
			sleep 0.5
		done
		wait "$pid" || rc=$?
		printf '\r\e[K'
	else
		"$@" >>"$REGISTRO" 2>&1 || rc=$?
	fi
	if ((rc == 0)); then
		ok "$desc ($((SECONDS - t0)) s)"
		return 0
	fi
	fallo "$desc: ha fallado (código $rc). Últimas líneas del registro:"
	tail -n 20 "$REGISTRO" | sed 's/^/      /' >&2
	return 1
}

# ----------------------------------------------------------------------------- utilidades

leer_var() {
	[[ -r $1 ]] || return 0
	local v
	v=$(grep -E "^[[:space:]]*$2=" "$1" | tail -n1 | cut -d= -f2-) || true
	v=${v%$'\r'}
	v=${v#\"}
	v=${v%\"}
	v=${v#\'}
	v=${v%\'}
	printf '%s' "$v"
}

tiene_var() { [[ -r $1 ]] && grep -qE "^[[:space:]]*$2=" "$1"; }

# poner_var FICHERO CLAVE VALOR: sustituye la línea (o la añade) conservando dueño y permisos.
poner_var() {
	local f=$1 k=$2 v=$3 tmp
	tmp=$(mktemp "$(dirname "$f")/.cidia-env.XXXXXX")
	if [[ -f $f ]]; then
		awk -v k="$k" -v v="$v" '
			$0 ~ "^[[:space:]]*" k "=" { if (!hecho) print k "=" v; hecho = 1; next }
			{ print }
			END { if (!hecho) print k "=" v }' "$f" >"$tmp"
		chmod --reference="$f" "$tmp"
		chown --reference="$f" "$tmp" 2>/dev/null || true
	else
		printf '%s=%s\n' "$k" "$v" >"$tmp"
		chmod 600 "$tmp"
	fi
	mv -f "$tmp" "$f"
}

ancestro_existente() {
	local p=$1
	while [[ ! -e $p ]]; do p=$(dirname "$p"); done
	printf '%s' "$p"
}

gib_libres() {
	local g
	g=$(df -P -k "$1" 2>/dev/null | awk 'NR == 2 { printf "%d", $4 / 1048576 }') || true
	printf '%s' "${g:-0}"
}

ip_principal() {
	local ip=""
	ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}') || true
	if [[ -z $ip ]]; then ip=$(hostname -I 2>/dev/null | awk '{print $1}') || true; fi
	printf '%s' "${ip:-127.0.0.1}"
}

# Quita usuario y contraseña (o token) de las URL para mostrarlas o guardarlas en el registro.
# Con un argumento limpia ese texto; sin argumentos, la entrada estándar.
url_sin_credenciales() {
	if (($#)); then
		sed -E 's#://[^/@[:space:]]+@#://#g' <<<"$1"
	else
		sed -E 's#://[^/@[:space:]]+@#://#g'
	fi
}

es_local() { [[ $1 == localhost || $1 == 127.* ]]; }

ip_a_entero() {
	local a b c d
	IFS=. read -r a b c d <<<"$1"
	printf '%d' $(((a << 24) + (b << 16) + (c << 8) + d))
}

# solapan RED1 RED2: 0 si dos subredes IPv4 (CIDR) se solapan.
solapan() {
	local r1=${1%/*} r2=${2%/*} m1=32 m2=32 m mascara
	if [[ $1 == */* ]]; then m1=${1#*/}; fi
	if [[ $2 == */* ]]; then m2=${2#*/}; fi
	m=$((m1 < m2 ? m1 : m2))
	mascara=$(((0xFFFFFFFF << (32 - m)) & 0xFFFFFFFF))
	((($(ip_a_entero "$r1") & mascara) == ($(ip_a_entero "$r2") & mascara)))
}

# Docker: con root, directamente; sin root, con el grupo docker o con sudo sin contraseña.
DOCKER=(docker)
preparar_docker_cli() {
	DOCKER=(docker)
	if ((EUID != 0)) && command -v docker >/dev/null && ! docker info >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
		DOCKER=(sudo -n docker)
	fi
}
docker_ok() { command -v docker >/dev/null && "${DOCKER[@]}" info >/dev/null 2>&1; }
contenedor() { "${DOCKER[@]}" ps -q --filter "$ETIQUETA" --filter "label=com.docker.compose.service=$1" 2>/dev/null | head -n1; }

DC_ARGS=()
dc() { "${DOCKER[@]}" "${DC_ARGS[@]}" "$@"; }

# puerto_ocupado_ajeno N: 0 si otro programa escucha en el puerto, 1 si está libre o es de
# CidIA y 2 si está en uso pero no se puede saber de quién (comprobación sin acceso a Docker).
puerto_ocupado_ajeno() {
	local p=$1
	ss -Hltn "sport = :$p" 2>/dev/null | grep -q . || return 1
	if docker_ok; then
		if "${DOCKER[@]}" ps --filter "$ETIQUETA" --format '{{.Ports}}' 2>/dev/null | grep -q ":$p->"; then return 1; fi
		return 0
	fi
	if command -v docker >/dev/null && ((EUID != 0)); then return 2; fi
	return 0
}

puerto_libre_desde() {
	local p
	for ((p = $1; p < $1 + 80; p++)); do
		if ! ss -Hltn "sport = :$p" 2>/dev/null | grep -q .; then
			printf '%s' "$p"
			return 0
		fi
	done
	return 1
}

# ----------------------------------------------------------------------------- rutas

fijar_rutas() {
	if [[ $DIR != / ]]; then DIR=${DIR%/}; fi
	REPO=$DIR/cidia
	DIR_DESP=$REPO/servidor/despliegue
	ENV_FILE=$DIR/secretos/cidia.env
	HERRAMIENTA=$DIR_DESP/cidia
}

# Carpeta de la instalación: --dir, CIDIA_DIR, la del proyecto en marcha, la que contiene esta
# copia del código (si ya es una instalación) o /opt/cidia.
detectar_dir() {
	local wd=""
	if [[ -z $DIR && -n ${CIDIA_DIR:-} ]]; then DIR=$CIDIA_DIR; fi
	if [[ -z $DIR ]] && docker_ok; then
		wd=$("${DOCKER[@]}" ps -a --filter "$ETIQUETA" --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null | head -n1) || true
		if [[ -n $wd && -d $wd/../../../secretos ]]; then DIR=$(cd "$wd/../../.." && pwd); fi
	fi
	if [[ -z $DIR && -d $REPO_ORIGEN/../secretos ]]; then DIR=$(cd "$REPO_ORIGEN/.." && pwd); fi
	DIR=${DIR:-/opt/cidia}
	[[ $DIR == /* ]] || DIR=$(pwd)/$DIR
	# Ruta canónica (sin «..», «.» ni enlaces): así las comprobaciones de carpetas protegidas no
	# se pueden esquivar con «--dir /opt/cidia/..» o con un enlace a una carpeta del sistema.
	DIR=$(readlink -m -- "$DIR")
	fijar_rutas
}

fichero_perfil() {
	if [[ -f $DIR_DESP/perfiles/$1.env ]]; then
		printf '%s' "$DIR_DESP/perfiles/$1.env"
	else
		printf '%s' "$REPO_ORIGEN/servidor/despliegue/perfiles/$1.env"
	fi
}

# ----------------------------------------------------------------------------- 1. comprobaciones

SO_ID="" SO_VERSION="" SO_NOMBRE="" SO_CODENAME="" ARQ="" NUCLEOS=0 CPU_MODELO="" RAM_GIB=0
GPU_HW=0 GPU_DRIVER=0 GPU_NOMBRE="" GPU_VRAM_MIB=0 GPU_USAR=0 TOOLKIT_OK=0
DOCKER_CLI=0 DOCKER_VERSION="" DOCKER_ORIGEN="" COMPOSE_VERSION=""
ES_PORTATIL=0 ES_ESCRITORIO=0 SUSPENSION_OFF=0 OTROS_CONTENEDORES=0

comprobar_equipo() {
	local d libre_dir libre_docker raiz_docker minimo recomendado servidor codigo

	# Sistema operativo
	# shellcheck disable=SC1091  # /etc/os-release es del equipo donde se instala
	if [[ -r /etc/os-release ]]; then
		SO_ID=$(. /etc/os-release && printf '%s' "${ID:-}")
		SO_VERSION=$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")
		SO_NOMBRE=$(. /etc/os-release && printf '%s' "${PRETTY_NAME:-}")
		SO_CODENAME=$(. /etc/os-release && printf '%s' "${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}")
	fi
	if [[ $SO_ID == ubuntu && ($SO_VERSION == 22.04 || $SO_VERSION == 24.04) ]]; then
		ok "Sistema: $SO_NOMBRE"
	elif [[ $SO_ID == ubuntu || $SO_ID == debian ]]; then
		aviso "Sistema: ${SO_NOMBRE:-desconocido}. CidIA se prueba en Ubuntu 22.04 y 24.04; en este puede funcionar, pero no está verificado."
	else
		aviso "Sistema: ${SO_NOMBRE:-desconocido}. Solo se admiten Ubuntu 22.04/24.04: aquí solo se puede seguir si Docker ya está instalado."
	fi

	# Arquitectura
	ARQ=$(dpkg --print-architecture 2>/dev/null || uname -m)
	case $ARQ in
	x86_64) ARQ=amd64 ;;
	aarch64) ARQ=arm64 ;;
	esac
	if [[ $ARQ == amd64 || $ARQ == arm64 ]]; then ok "Arquitectura: $ARQ"; else fallo "Arquitectura $ARQ no admitida (solo amd64 y arm64)."; fi

	# Procesador y memoria
	NUCLEOS=$(nproc 2>/dev/null || echo 1)
	CPU_MODELO=$(LC_ALL=C lscpu 2>/dev/null | sed -n 's/^Model name:[[:space:]]*//p' | head -n1) || true
	if ((NUCLEOS >= 4)); then ok "Procesador: ${CPU_MODELO:-desconocido} · $NUCLEOS núcleos"; else aviso "Procesador: $NUCLEOS núcleos. Se recomiendan 4 o más."; fi
	RAM_GIB=$(awk '/^MemTotal/ { printf "%d", ($2 / 1048576) + 0.5 }' /proc/meminfo)
	if ((RAM_GIB >= 16)); then
		ok "Memoria: $RAM_GIB GB"
	elif ((RAM_GIB >= 8)); then
		aviso "Memoria: $RAM_GIB GB. Funciona con modelos pequeños; para la configuración completa se recomiendan 16 GB o más."
	else
		fallo "Memoria: $RAM_GIB GB. CidIA necesita al menos 8 GB."
	fi

	# Disco: carpeta de la instalación y carpeta de Docker (imágenes y modelos)
	minimo=25 recomendado=50
	libre_dir=$(gib_libres "$(ancestro_existente "$DIR")")
	raiz_docker=/var/lib/docker
	if docker_ok; then raiz_docker=$("${DOCKER[@]}" info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker); fi
	libre_docker=$(gib_libres "$(ancestro_existente "$raiz_docker")")
	for d in "$libre_dir:$DIR" "$libre_docker:$raiz_docker"; do
		if ((${d%%:*} >= recomendado)); then
			ok "Disco libre en ${d#*:}: ${d%%:*} GB"
		elif ((${d%%:*} >= minimo)); then
			aviso "Disco libre en ${d#*:}: ${d%%:*} GB. Se recomiendan $recomendado GB (imágenes, modelos y documentos)."
		else
			fallo "Disco libre en ${d#*:}: ${d%%:*} GB. Hacen falta al menos $minimo GB."
		fi
	done

	# GPU NVIDIA: hardware (por PCI, sin depender de lspci) y controlador (nvidia-smi)
	for d in /sys/bus/pci/devices/*; do
		if [[ $(cat "$d/vendor" 2>/dev/null) == 0x10de && $(cat "$d/class" 2>/dev/null) == 0x03* ]]; then GPU_HW=1; fi
	done
	if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
		GPU_DRIVER=1
		IFS=, read -r GPU_NOMBRE GPU_VRAM_MIB d < <(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits | head -n1)
		GPU_VRAM_MIB=${GPU_VRAM_MIB// /}
		[[ $GPU_VRAM_MIB =~ ^[0-9]+$ ]] || GPU_VRAM_MIB=0
		ok "GPU: $GPU_NOMBRE · $((GPU_VRAM_MIB / 1024)) GB de memoria · controlador ${d// /}"
		if ((GPU_VRAM_MIB < 10000)); then aviso "La GPU tiene menos de 10 GB: el modelo de 8B irá en parte por el procesador."; fi
	elif ((GPU_HW)); then
		aviso "Hay una GPU NVIDIA, pero no tiene el controlador instalado (nvidia-smi no responde)."
	else
		info "Sin GPU NVIDIA: los modelos funcionarán en el procesador."
	fi

	# cgroups (Ollama solo ve los límites de memoria con cgroups v2)
	if [[ $(stat -fc %T /sys/fs/cgroup 2>/dev/null) == cgroup2fs ]]; then
		ok "cgroups v2"
	else
		aviso "cgroups v1: Ollama no ve el límite de memoria de su contenedor (ver manual, «Solución de problemas»)."
	fi

	# Docker
	if command -v docker >/dev/null; then
		DOCKER_CLI=1
		# shellcheck disable=SC2016  # ${Status} es un campo de dpkg-query, no una variable de bash
		if dpkg-query -W -f='${Status}' docker-ce 2>/dev/null | grep -q 'install ok installed'; then
			DOCKER_ORIGEN="repositorio oficial de Docker"
		elif dpkg-query -W -f='${Status}' docker.io 2>/dev/null | grep -q 'install ok installed'; then
			DOCKER_ORIGEN="paquete docker.io de Ubuntu"
		elif command -v snap >/dev/null && snap list docker >/dev/null 2>&1; then
			DOCKER_ORIGEN="snap"
		else
			DOCKER_ORIGEN="origen desconocido"
		fi
		if docker_ok; then
			servidor=$("${DOCKER[@]}" version --format '{{.Server.Version}}' 2>/dev/null) || true
			DOCKER_VERSION=$servidor
			if [[ $DOCKER_ORIGEN == snap ]]; then
				aviso "Docker $servidor instalado con snap: no se recomienda (rutas limitadas). Mejor Docker Engine del repositorio oficial."
			elif [[ ${servidor%%.*} =~ ^[0-9]+$ ]] && ((${servidor%%.*} < 28)); then
				aviso "Docker $servidor ($DOCKER_ORIGEN). Se recomienda Docker Engine 28 o superior si CidIA se publica en una red local."
			else
				ok "Docker $servidor ($DOCKER_ORIGEN)"
			fi
			if "${DOCKER[@]}" context show 2>/dev/null | grep -q desktop; then
				aviso "Se está usando Docker Desktop: CidIA necesita Docker Engine (el servicio del sistema)."
			fi
			COMPOSE_VERSION=$("${DOCKER[@]}" compose version --short 2>/dev/null) || true
			if [[ -n $COMPOSE_VERSION ]]; then ok "Docker Compose $COMPOSE_VERSION"; else info "Falta el complemento Docker Compose: se instalaría."; fi
			OTROS_CONTENEDORES=$("${DOCKER[@]}" ps -q | wc -l)
			OTROS_CONTENEDORES=$((OTROS_CONTENEDORES - $("${DOCKER[@]}" ps -q --filter "$ETIQUETA" | wc -l)))
			if ((OTROS_CONTENEDORES > 0)); then info "Contenedores de otros proyectos en marcha: $OTROS_CONTENEDORES (no se tocarán)."; fi
		else
			aviso "Docker está instalado, pero este usuario no puede usarlo (prueba con sudo)."
		fi
	else
		info "Docker no está instalado: se instalaría Docker Engine desde download.docker.com."
	fi

	# NVIDIA Container Toolkit
	# shellcheck disable=SC2016  # plantilla de formato de Docker, no una expansión de bash
	if ((GPU_DRIVER)); then
		if command -v nvidia-ctk >/dev/null && docker_ok &&
			"${DOCKER[@]}" info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' 2>/dev/null | grep -qw nvidia; then
			TOOLKIT_OK=1
			ok "NVIDIA Container Toolkit configurado en Docker"
		else
			info "Falta el NVIDIA Container Toolkit: se instalaría desde el repositorio oficial de NVIDIA."
		fi
	fi

	# Conexión a los sitios de los que se descargan paquetes, imágenes y modelos
	local sitios=(download.docker.com registry-1.docker.io registry.ollama.ai github.com pypi.org registry.npmjs.org huggingface.co)
	local caidos=()
	if ! command -v curl >/dev/null; then
		info "curl no está instalado (se instalaría): la conexión a Internet se comprobará al descargar."
		sitios=()
	fi
	for d in "${sitios[@]}"; do
		codigo=$(curl -sS -o /dev/null -m 6 -w '%{http_code}' "https://$d/" 2>/dev/null) || codigo=000
		if [[ $codigo == 000 ]]; then caidos+=("$d"); fi
	done
	if ((${#caidos[@]})); then
		aviso "Sin conexión con: ${caidos[*]}. Hace falta para instalar (¿proxy de empresa? ver manual)."
	elif ((${#sitios[@]})); then
		ok "Conexión a Internet: llegan Docker, Ollama, GitHub, PyPI, npm y Hugging Face"
	fi

	# Energía: un servidor no debe suspenderse
	if compgen -G '/sys/class/power_supply/BAT*' >/dev/null; then ES_PORTATIL=1; fi
	if command -v gnome-shell >/dev/null; then ES_ESCRITORIO=1; fi
	if [[ $(systemctl is-enabled sleep.target 2>/dev/null) == masked ]]; then
		SUSPENSION_OFF=1
		ok "Suspensión desactivada"
	elif ((ES_PORTATIL)); then
		aviso "Es un portátil y puede suspenderse (al cerrar la tapa o por inactividad)."
	elif ((ES_ESCRITORIO)); then
		info "Ubuntu de escritorio: puede suspenderse por inactividad (conviene desactivarlo en un servidor)."
	fi
}

# ----------------------------------------------------------------------------- estado de una instalación

comprobar_instalacion() {
	local d n faltan=() v cid salida
	info "Carpeta de la instalación: $DIR"
	if [[ ! -d $DIR ]]; then
		info "No existe todavía: se crearía con datos/, secretos/, registros/ y copias/."
		return 0
	fi
	for d in datos secretos registros copias; do
		if [[ -d $DIR/$d ]]; then ok "$d/ existe"; else info "$d/ no existe: se crearía"; fi
	done
	if [[ -d $DIR/datos ]]; then
		v=$(find "$DIR/datos" ! -uid "$UID_DATOS" -printf '%u\n' 2>/dev/null | sort -u | paste -sd ',') || true
		if [[ -z $v ]]; then
			ok "datos/ es del usuario $UID_DATOS (el de los contenedores)"
		else
			aviso "En datos/ hay ficheros de otro usuario ($v); el gateway (uid $UID_DATOS) no podría escribirlos. Se corregiría con chown -R $UID_DATOS:$UID_DATOS."
		fi
	fi
	if [[ -d $DIR/secretos ]]; then
		v=$(stat -c %a "$DIR/secretos")
		if [[ $v == 700 ]]; then ok "secretos/ con permisos 700"; else aviso "secretos/ tiene permisos $v (deberían ser 700)"; fi
	fi
	if [[ -r $ENV_FILE ]]; then
		n=$(grep -cE '^[A-Z_]+=' "$ENV_FILE") || true
		for v in CIDIA_PG_PASSWORD CIDIA_SECRETO_JWT CIDIA_ESPACIO_SECRETO WEKNORA_DB_PASSWORD CIDIA_REDIS_PASSWORD WEKNORA_JWT_SECRET WEKNORA_AES_KEY; do
			tiene_var "$ENV_FILE" "$v" || faltan+=("$v")
		done
		ok "secretos/cidia.env: $n variables (los valores no se muestran)"
		if ((${#faltan[@]})); then info "Faltan ${faltan[*]}: se generarían sin tocar los existentes."; else ok "Todos los secretos están generados: se conservarían."; fi
		v=$(stat -c %a "$ENV_FILE")
		if [[ $v == 600 ]]; then ok "cidia.env con permisos 600"; else aviso "cidia.env tiene permisos $v (deberían ser 600)"; fi
		if [[ -e $SOCKET_DOCKER ]]; then
			v=$(leer_var "$ENV_FILE" CIDIA_DOCKER_GID)
			if [[ ${v:-120} != "$(stat -c %g "$SOCKET_DOCKER")" ]]; then
				info "CIDIA_DOCKER_GID (${v:-sin definir, 120}) no es el grupo del socket de Docker ($(stat -c %g "$SOCKET_DOCKER")): se corregiría (lo usa el espacio de trabajo)."
			fi
		fi
	elif [[ -e $ENV_FILE || -d $DIR/secretos ]]; then
		info "No puedo leer secretos/cidia.env con este usuario (ejecuta con sudo para comprobarlo)."
	else
		info "No hay secretos/cidia.env: se generaría."
	fi
	if [[ -d $REPO/.git ]]; then
		v=$(git -c safe.directory="$REPO" -C "$REPO" log -1 --format='%h del %cd' --date=format:'%d/%m/%Y' 2>/dev/null) || true
		ok "Código en $REPO (git${v:+, commit $v})"
	elif [[ -f $DIR_DESP/docker-compose.yml ]]; then
		ok "Código en $REPO (copia sin git)"
	else
		info "No hay código en $REPO: se copiaría desde $REPO_ORIGEN"
	fi
	if ! docker_ok; then
		info "No puedo consultar Docker con este usuario: no se comprueban los contenedores."
		return 0
	fi
	salida=$("${DOCKER[@]}" ps -a --filter "$ETIQUETA" --format '{{.Label "com.docker.compose.service"}}\t{{.State}}\t{{.Status}}' | sort) || true
	if [[ -z $salida ]]; then
		info "No hay contenedores de CidIA."
	else
		while IFS=$'\t' read -r n v d; do
			if [[ $v == running ]]; then ok "Servicio $n: $d"; else aviso "Servicio $n: $d"; fi
		done <<<"$salida"
		v=$("${DOCKER[@]}" ps -a --filter "$ETIQUETA" --format '{{.Label "com.docker.compose.project.config_files"}}' | head -n1 | tr ',' '\n' | xargs -r -n1 basename | paste -sd ' ') || true
		info "Compose en uso: $v"
	fi
	if "${DOCKER[@]}" volume inspect "${PROYECTO}_pg-datos" >/dev/null 2>&1; then ok "Volumen de la base de datos (${PROYECTO}_pg-datos) presente"; fi
	cid=$(contenedor postgres)
	if [[ -n $cid ]]; then
		n=$("${DOCKER[@]}" exec "$cid" psql -U cidia -d cidia -tAc "SELECT count(*) FROM usuarios WHERE rol = 'admin' AND activo" 2>/dev/null | tr -d '[:space:]') || true
		if [[ $n =~ ^[1-9] ]]; then ok "Cuentas de administración activas: $n (no se tocarían)"; else info "No hay cuenta de administración: se crearía."; fi
	fi
	if [[ -L $ENLACE_CIDIA ]]; then ok "Orden 'cidia' instalada en $ENLACE_CIDIA"; else info "La orden 'cidia' no está en $ENLACE_CIDIA: se enlazaría."; fi
}

# ----------------------------------------------------------------------------- 2. opciones

ORIGEN_PERFIL="" IP_PUBLICACION="" PUERTO_OLLAMA="" PUERTO_ASR="" RED_BORDE="" RED_INTERNA=""
EXTRAS_COMPOSE="" PERFILES_COMPOSE="" AJUSTAR_ENERGIA=0 MODELOS_PERFIL=()

perfil_sugerido() {
	if ((GPU_USAR)); then
		echo msi
	elif [[ $ARQ == arm64 ]]; then
		echo oracle
	else
		echo generico
	fi
}

describir_perfiles() {
	tenue "msi       GPU NVIDIA de 12-16 GB: ministral-3:8b y qwen3-embedding:0.6b (configuración del MVP)"
	tenue "generico  cualquier PC o servidor sin GPU: modelos medianos en el procesador (más lento)"
	tenue "oracle    pruebas en ARM sin GPU: modelos pequeños y datos de demostración"
}

# Modelos (chat, visión, embeddings) del perfil genérico según la memoria del equipo.
modelos_generico() {
	if ((RAM_GIB >= 16)); then
		echo "ministral-3:3b ministral-3:3b qwen3-embedding:0.6b"
	else
		echo "qwen3:1.7b qwen3.5:0.8b qwen3-embedding:0.6b"
	fi
}

calcular_modelos_perfil() {
	local fich m
	MODELOS_PERFIL=()
	if [[ $PERFIL == generico && ! -f $DIR_DESP/perfiles/generico.env ]]; then
		read -r -a MODELOS_PERFIL <<<"$(modelos_generico)"
	else
		fich=$(fichero_perfil "$PERFIL")
		for m in CIDIA_LLM_MODELO_CHAT CIDIA_LLM_MODELO_VISION CIDIA_LLM_MODELO_EMBEDDINGS; do
			m=$(leer_var "$fich" "$m")
			if [[ -n $m ]]; then MODELOS_PERFIL+=("$m"); fi
		done
	fi
	mapfile -t MODELOS_PERFIL < <(printf '%s\n' "${MODELOS_PERFIL[@]}" | awk 'NF && !visto[$0]++')
}

decidir_opciones() {
	local v ips cfg servicios rc
	# GPU
	if ((SIN_GPU)); then
		GPU_USAR=0
		if ((GPU_DRIVER)); then info "GPU desactivada con --sin-gpu."; fi
	elif ((GPU_DRIVER)); then
		GPU_USAR=1
	elif ((GPU_HW)) && [[ $MODO == instalar ]]; then
		aviso "La GPU NVIDIA no tiene controlador. Para usarla (muy recomendable):"
		tenue "1) sudo ubuntu-drivers install        (instala el controlador recomendado)"
		tenue "2) Reinicia el equipo. Si pide «Enroll MOK» (arranque seguro), elige la opción y usa la clave que te pidió."
		tenue "3) Comprueba con: nvidia-smi    y vuelve a ejecutar este instalador."
		if ! confirmar "¿Continuar ahora sin GPU (los modelos irán en el procesador, mucho más lentos)?" n; then
			info "Instalación detenida: instala el controlador, reinicia y vuelve a ejecutar el instalador."
			exit 0
		fi
	fi

	# Perfil
	v=$(leer_var "$ENV_FILE" CIDIA_PERFIL)
	if [[ -n $PERFIL ]]; then
		ORIGEN_PERFIL="opción --perfil"
	elif [[ -n $v ]]; then
		PERFIL=$v
		ORIGEN_PERFIL="instalación existente"
	else
		PERFIL=$(perfil_sugerido)
		ORIGEN_PERFIL="propuesto según el equipo"
		if [[ $MODO == instalar ]]; then
			info "Perfiles disponibles:"
			describir_perfiles
			preguntar PERFIL "Perfil" "$PERFIL"
		fi
	fi
	PERFIL=${PERFIL,,}
	if [[ $PERFIL == genérico ]]; then PERFIL=generico; fi
	[[ $PERFIL =~ ^[a-z0-9_-]+$ && $PERFIL != weknora && $PERFIL != plantilla ]] || morir "Perfil no válido: $PERFIL"
	if [[ $PERFIL != generico && ! -f $(fichero_perfil "$PERFIL") ]]; then
		# Con --repo y el instalador suelto, los perfiles llegan con el clon: se comprueba después.
		if [[ -n $REPO_URL && $MODO == instalar ]]; then
			info "El perfil «$PERFIL» se comprobará al clonar el repositorio."
		else
			morir "No existe el perfil «$PERFIL» (falta perfiles/$PERFIL.env). Usa msi, generico u oracle."
		fi
	fi
	if [[ $PERFIL == msi ]] && ((!GPU_USAR)); then
		aviso "El perfil msi está pensado para una GPU NVIDIA; sin ella ministral-3:8b será muy lento. Valora --perfil generico."
	fi
	calcular_modelos_perfil

	# Puerto
	v=$(leer_var "$ENV_FILE" CIDIA_PUERTO)
	if [[ -z $PUERTO ]]; then
		PUERTO=${v:-$PUERTO_DEFECTO}
		if [[ -z $v && $MODO == instalar ]]; then preguntar PUERTO "Puerto del servidor CidIA" "$PUERTO"; fi
	fi
	if ! [[ $PUERTO =~ ^[0-9]+$ ]] || ((PUERTO < 1024 || PUERTO > 65535)); then morir "Puerto no válido: $PUERTO (entre 1024 y 65535)."; fi
	rc=0
	puerto_ocupado_ajeno "$PUERTO" || rc=$?
	if ((rc == 0)); then
		if [[ $MODO == instalar ]]; then morir "El puerto $PUERTO ya lo usa otro programa. Elige otro con --puerto."; fi
		fallo "El puerto $PUERTO ya lo usa otro programa (habría que elegir otro con --puerto)."
	elif ((rc == 2)); then
		info "El puerto $PUERTO está en uso; sin acceso a Docker no sé si es de CidIA (con sudo se comprueba)."
	fi

	# Dirección para los portátiles
	v=$(leer_var "$ENV_FILE" CIDIA_DIRECCION)
	if [[ -z $DIRECCION ]]; then
		DIRECCION=${v:-$(ip_principal)}
		if [[ -z $v && $MODO == instalar ]]; then
			ips=$(ip -4 -o addr show scope global 2>/dev/null | awk '{ sub(/\/.*/, "", $4); printf "%s%s (%s)", sep, $4, $2; sep = ", " }') || true
			if [[ -n $ips ]]; then info "Direcciones IPv4 de este equipo: $ips"; fi
			tenue "Mejor una IP fija (reserva DHCP en el router) o un nombre del DNS de la empresa."
			preguntar DIRECCION "IP o nombre con el que los portátiles llegarán a este servidor" "$DIRECCION"
		fi
	fi
	DIRECCION=${DIRECCION#http://}
	DIRECCION=${DIRECCION#https://}
	DIRECCION=${DIRECCION%%/*}
	DIRECCION=${DIRECCION%%:*}
	[[ $DIRECCION =~ ^[A-Za-z0-9.-]+$ ]] || morir "Dirección no válida: $DIRECCION (usa una IPv4 o un nombre, sin espacios)."

	# Publicación en la red local
	v=$(leer_var "$ENV_FILE" CIDIA_IP_PUBLICACION)
	case $PUBLICAR in
	lan) IP_PUBLICACION=0.0.0.0 ;;
	local) IP_PUBLICACION=127.0.0.1 ;;
	*)
		if [[ -n $v ]]; then
			IP_PUBLICACION=$v
		elif [[ -e $ENV_FILE ]]; then
			# Instalación existente sin la variable: el compose publica en 127.0.0.1 y se mantiene.
			IP_PUBLICACION=127.0.0.1
		elif es_local "$DIRECCION"; then
			IP_PUBLICACION=127.0.0.1
		elif [[ $MODO == instalar ]]; then
			aviso "Para que los portátiles lleguen, CidIA debe escuchar en la red local (puerto $PUERTO)."
			tenue "Cualquier equipo de esa red verá la pantalla de inicio de sesión. Limítalo con el cortafuegos a la"
			tenue "red de la empresa (ver manual) y no lo abras nunca a Internet. Ollama y la base de datos seguirán"
			tenue "escuchando solo en este equipo."
			if confirmar "¿Publicar CidIA en la red local?" s; then IP_PUBLICACION=0.0.0.0; else IP_PUBLICACION=127.0.0.1; fi
		else
			IP_PUBLICACION=0.0.0.0
		fi
		;;
	esac
	if [[ $IP_PUBLICACION != 0.0.0.0 && $IP_PUBLICACION != 127.0.0.1 ]] && ! ip -4 -o addr show | grep -q " inet $IP_PUBLICACION/"; then
		aviso "CIDIA_IP_PUBLICACION=$IP_PUBLICACION no es una IP de este equipo: se usará 0.0.0.0."
		IP_PUBLICACION=0.0.0.0
	fi
	if [[ $IP_PUBLICACION == 127.0.0.1 ]] && ! es_local "$DIRECCION"; then
		aviso "CidIA quedará solo en este equipo: los portátiles no llegarán hasta que ejecutes «sudo cidia abrir-puerto»."
	fi

	# Ficheros y perfiles de Compose: se respetan los de la instalación existente
	cfg=""
	if docker_ok; then cfg=$("${DOCKER[@]}" ps -a --filter "$ETIQUETA" --format '{{.Label "com.docker.compose.project.config_files"}}' 2>/dev/null | head -n1) || true; fi
	EXTRAS_COMPOSE=""
	if tiene_var "$ENV_FILE" CIDIA_COMPOSE_FICHEROS; then
		if [[ ,$(leer_var "$ENV_FILE" CIDIA_COMPOSE_FICHEROS), == *,debug,* ]]; then EXTRAS_COMPOSE="debug"; fi
	elif [[ $cfg == *compose.debug.yml* ]]; then
		EXTRAS_COMPOSE="debug"
	fi
	if ((GPU_USAR)); then EXTRAS_COMPOSE="gpu${EXTRAS_COMPOSE:+,$EXTRAS_COMPOSE}"; fi
	if tiene_var "$ENV_FILE" CIDIA_COMPOSE_PERFILES; then
		v=$(leer_var "$ENV_FILE" CIDIA_COMPOSE_PERFILES)
	else
		v=""
		if docker_ok; then
			servicios=$("${DOCKER[@]}" ps -a --filter "$ETIQUETA" --format '{{.Label "com.docker.compose.service"}}' 2>/dev/null) || true
			if grep -qx weknora <<<"$servicios"; then v+="weknora,"; fi
			if grep -qx espacio-trabajo <<<"$servicios"; then v+="espacio,"; fi
		fi
	fi
	if ((CON_WEKNORA)); then v+=",weknora"; fi
	if ((CON_ESPACIO)); then v+=",espacio"; fi
	PERFILES_COMPOSE=$(tr ',' '\n' <<<"$v" | awk 'NF && !visto[$0]++' | paste -sd ',')
	if [[ ,$PERFILES_COMPOSE, == *,espacio,* && ! -f $REPO_ORIGEN/servidor/espacio-trabajo/Dockerfile && ! -f $DIR_DESP/../espacio-trabajo/Dockerfile ]]; then
		aviso "El espacio de trabajo del agente todavía no está en esta versión de CidIA (falta servidor/espacio-trabajo/Dockerfile): se omite."
		PERFILES_COMPOSE=$(tr ',' '\n' <<<"$PERFILES_COMPOSE" | grep -vx espacio | paste -sd ',') || true
	fi

	# Puertos internos (solo en 127.0.0.1) y subredes de Docker
	PUERTO_OLLAMA=$(leer_var "$ENV_FILE" CIDIA_PUERTO_OLLAMA)
	PUERTO_ASR=$(leer_var "$ENV_FILE" CIDIA_PUERTO_ASR)
	if [[ -z $PUERTO_OLLAMA ]] && puerto_ocupado_ajeno 18720; then
		PUERTO_OLLAMA=$(puerto_libre_desde 18722)
		info "El puerto 18720 está ocupado: Ollama usará 127.0.0.1:$PUERTO_OLLAMA."
	fi
	if [[ -z $PUERTO_ASR ]] && puerto_ocupado_ajeno 18721; then
		PUERTO_ASR=$(puerto_libre_desde 18760)
		info "El puerto 18721 está ocupado: la voz usará 127.0.0.1:$PUERTO_ASR."
	fi
	elegir_subredes

	# Energía
	AJUSTAR_ENERGIA=0
	if [[ $MODO == instalar ]] && ((!SUSPENSION_OFF && !SIN_ENERGIA && (ES_PORTATIL || ES_ESCRITORIO))) && ((INTERACTIVO || SI)); then
		if confirmar "¿Desactivar la suspensión y la hibernación del equipo? (recomendado en un servidor)" s; then AJUSTAR_ENERGIA=1; fi
	fi
}

# Subredes de las redes cidia-borde y cidia-interna: si la red de la empresa o algún otro
# proyecto de Docker usa 172.29.10-11.x, se eligen otras libres.
elegir_subredes() {
	local ocupadas candidato par borde interna r libre
	RED_BORDE=$(leer_var "$ENV_FILE" CIDIA_RED_BORDE)
	RED_INTERNA=$(leer_var "$ENV_FILE" CIDIA_RED_INTERNA)
	if [[ -n $RED_BORDE || -n $RED_INTERNA ]]; then return 0; fi
	if docker_ok && "${DOCKER[@]}" network inspect cidia-borde >/dev/null 2>&1; then return 0; fi
	ocupadas=$(
		ip -4 route show 2>/dev/null | awk '$1 != "default" { print $1 }'
		if docker_ok; then
			"${DOCKER[@]}" network ls -q 2>/dev/null | while read -r r; do
				"${DOCKER[@]}" network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}' "$r" 2>/dev/null
			done | awk '$1 !~ /^cidia-/ { for (i = 2; i <= NF; i++) print $i }'
		fi
	)
	ocupadas=$(grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$' <<<"$ocupadas") || true
	for par in "172.29.10.0/24 172.29.11.0/24" "172.30.10.0/24 172.30.11.0/24" "10.229.10.0/24 10.229.11.0/24" "192.168.229.0/24 192.168.230.0/24"; do
		read -r borde interna <<<"$par"
		libre=1
		while read -r r; do
			if [[ -z $r ]]; then continue; fi
			if solapan "$r" "$borde" || solapan "$r" "$interna"; then
				libre=0
				break
			fi
		done <<<"$ocupadas"
		if ((libre)); then
			if [[ $borde != 172.29.10.0/24 ]]; then
				info "La subred 172.29.10-11.x ya se usa en este equipo: las redes de CidIA usarán $borde y $interna."
				RED_BORDE=$borde
				RED_INTERNA=$interna
			fi
			return 0
		fi
		candidato=$par
	done
	aviso "No encuentro subredes libres para Docker (última probada: $candidato). Fíjalas en cidia.env con CIDIA_RED_BORDE y CIDIA_RED_INTERNA."
}

mostrar_resumen_opciones() {
	local txt_pub
	if [[ $IP_PUBLICACION == 127.0.0.1 ]]; then txt_pub="solo este equipo (127.0.0.1)"; else txt_pub="red local ($IP_PUBLICACION:$PUERTO)"; fi
	info "Carpeta:          $DIR"
	info "Perfil:           $PERFIL ($ORIGEN_PERFIL) · modelos: ${MODELOS_PERFIL[*]}"
	info "GPU:              $( ((GPU_USAR)) && echo "sí, $GPU_NOMBRE" || echo "no")"
	info "Dirección:        http://$DIRECCION:$PUERTO  · publicación: $txt_pub"
	info "Servicios extra:  ${PERFILES_COMPOSE:-ninguno}${EXTRAS_COMPOSE:+ · compose: $EXTRAS_COMPOSE}"
	if ((SIN_MODELOS)); then info "Modelos:          no se descargan ahora (--sin-modelos)"; fi
	if ((AJUSTAR_ENERGIA)); then info "Energía:          se desactivarán la suspensión y la hibernación"; fi
}

# ----------------------------------------------------------------------------- 3. Docker y GPU

APT_ACTUALIZADO=0
apt_instalar() {
	if ((!APT_ACTUALIZADO)); then
		ejecutar "Actualizando la lista de paquetes" apt-get -o DPkg::Lock::Timeout=300 update || morir "apt-get update ha fallado."
		APT_ACTUALIZADO=1
	fi
	ejecutar "Instalando $*" env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y --no-install-recommends "$@" ||
		morir "No se han podido instalar: $*"
}

repositorio_docker() {
	local distro=ubuntu
	if [[ $SO_ID == debian ]]; then distro=debian; fi
	if grep -rqs 'download.docker.com' /etc/apt/sources.list /etc/apt/sources.list.d/; then
		ok "Repositorio oficial de Docker ya configurado"
		return 0
	fi
	[[ -n $SO_CODENAME ]] || morir "No sé qué versión de $SO_ID es esta: instala Docker Engine a mano (docs.docker.com/engine/install)."
	install -m 0755 -d /etc/apt/keyrings
	ejecutar "Descargando la clave del repositorio de Docker" curl -fsSL "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/docker.asc ||
		morir "No se ha podido descargar la clave de Docker."
	chmod a+r /etc/apt/keyrings/docker.asc
	cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/$distro
Suites: $SO_CODENAME
Components: stable
Architectures: $ARQ
Signed-By: /etc/apt/keyrings/docker.asc
EOF
	APT_ACTUALIZADO=0
	ok "Repositorio oficial de Docker añadido (download.docker.com)"
}

instalar_docker() {
	local basicos=() p conflictivos=()
	for p in curl openssl gpg tar; do
		if ! command -v "$p" >/dev/null; then
			case $p in
			gpg) basicos+=(gnupg) ;;
			*) basicos+=("$p") ;;
			esac
		fi
	done
	if [[ ! -d /etc/ssl/certs ]]; then basicos+=(ca-certificates); fi
	if [[ -n $REPO_URL ]] && ! command -v git >/dev/null; then basicos+=(git); fi
	if ((${#basicos[@]})); then apt_instalar "${basicos[@]}"; fi

	if ((DOCKER_CLI)); then
		ok "Docker ya está instalado (${DOCKER_VERSION:-sin versión}, $DOCKER_ORIGEN): no se cambia"
	else
		# Paquetes que chocan con Docker Engine (según la guía oficial). Solo se quitan si están.
		for p in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
			if dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed'; then conflictivos+=("$p"); fi
		done
		if ((${#conflictivos[@]})); then
			ejecutar "Quitando paquetes que chocan con Docker Engine (${conflictivos[*]})" \
				env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 remove -y "${conflictivos[@]}" || morir "No se han podido quitar ${conflictivos[*]}."
		fi
		repositorio_docker
		apt_instalar docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
		ejecutar "Activando el servicio de Docker" systemctl enable --now docker || morir "Docker no arranca: sudo systemctl status docker"
		DOCKER_CLI=1
		DOCKER_ORIGEN="repositorio oficial de Docker"
	fi
	docker_ok || morir "Docker no responde. Compruébalo con: sudo systemctl status docker"
	DOCKER_VERSION=$("${DOCKER[@]}" version --format '{{.Server.Version}}' 2>/dev/null) || true
	if ! "${DOCKER[@]}" compose version >/dev/null 2>&1 || ! "${DOCKER[@]}" buildx version >/dev/null 2>&1; then
		repositorio_docker
		apt_instalar docker-compose-plugin docker-buildx-plugin
	fi
	COMPOSE_VERSION=$("${DOCKER[@]}" compose version --short 2>/dev/null) || morir "Docker Compose no funciona."
	ok "Docker $DOCKER_VERSION con Compose $COMPOSE_VERSION"
}

instalar_toolkit_nvidia() {
	if ((!GPU_USAR)); then
		info "Sin GPU: no hace falta el NVIDIA Container Toolkit."
		return 0
	fi
	if ((TOOLKIT_OK)); then
		ok "NVIDIA Container Toolkit ya configurado"
		return 0
	fi
	if ! command -v nvidia-ctk >/dev/null; then
		if [[ ! -s /etc/apt/sources.list.d/nvidia-container-toolkit.list ]]; then
			ejecutar "Descargando la clave del repositorio de NVIDIA" \
				bash -c 'set -o pipefail; curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg' ||
				morir "No se ha podido descargar la clave de NVIDIA."
			# La lista se escribe en un temporal y solo se mueve si la descarga ha ido bien: una
			# lista vacía haría que los reintentos se saltaran este paso.
			# shellcheck disable=SC2016  # $f es una variable del guion de «bash -c»
			ejecutar "Añadiendo el repositorio oficial de NVIDIA" \
				bash -c 'set -o pipefail; f=/etc/apt/sources.list.d/nvidia-container-toolkit.list; curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" > "$f.tmp" && [ -s "$f.tmp" ] && mv "$f.tmp" "$f"' ||
				morir "No se ha podido añadir el repositorio de NVIDIA."
			APT_ACTUALIZADO=0
		fi
		apt_instalar nvidia-container-toolkit
	fi
	ejecutar "Configurando Docker para usar la GPU" nvidia-ctk runtime configure --runtime=docker || morir "nvidia-ctk ha fallado."
	if ((OTROS_CONTENEDORES > 0)); then
		aviso "Hay que reiniciar Docker: los contenedores de otros proyectos ($OTROS_CONTENEDORES) se pararán unos segundos y volverán a arrancar si tienen «restart»."
		if ! confirmar "¿Reiniciar Docker ahora?" s; then
			aviso "Sin reiniciar Docker no se puede usar la GPU: CidIA seguirá sin ella. Reinicia Docker y vuelve a ejecutar el instalador."
			GPU_USAR=0
			EXTRAS_COMPOSE=$(tr ',' '\n' <<<"$EXTRAS_COMPOSE" | grep -vx gpu | paste -sd ',') || true
			return 0
		fi
	fi
	ejecutar "Reiniciando Docker" systemctl restart docker || morir "Docker no ha vuelto a arrancar: sudo systemctl status docker"
	# shellcheck disable=SC2016  # plantilla de formato de Docker, no una expansión de bash
	if "${DOCKER[@]}" info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' 2>/dev/null | grep -qw nvidia; then
		ok "Docker ya puede usar la GPU"
	else
		aviso "Docker no muestra el runtime de NVIDIA. Revisa: sudo nvidia-ctk runtime configure --runtime=docker"
	fi
}

# ----------------------------------------------------------------------------- 4. carpetas y código

preparar_carpetas() {
	local nuevo_registro
	mkdir -p "$DIR"/{datos/ficheros,datos/generador-de-contenido,secretos,registros,copias}
	chmod 700 "$DIR/secretos" "$DIR/copias"
	chmod 755 "$DIR"
	# El gateway y la voz corren como el usuario $UID_DATOS sin privilegios: datos/ debe ser suyo.
	if [[ -n $(find "$DIR/datos" ! -uid "$UID_DATOS" -print -quit 2>/dev/null) ]]; then
		chown -R "$UID_DATOS:$UID_DATOS" "$DIR/datos"
	fi
	ok "Carpetas en $DIR (secretos/ y copias/ solo para root; datos/ del usuario $UID_DATOS)"
	nuevo_registro="$DIR/registros/instalacion-$FECHA_INICIO.log"
	if [[ $REGISTRO != "$nuevo_registro" ]]; then
		cat "$REGISTRO" >>"$nuevo_registro"
		rm -f "$REGISTRO"
		REGISTRO=$nuevo_registro
		chmod 640 "$REGISTRO"
	fi
}

EXCLUSIONES=(--exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude='*.egg-info'
	--exclude=servidor/web/dist --exclude=tsconfig.tsbuildinfo --exclude=_datos --exclude=_datos_pruebas
	--exclude=datos --exclude=.env --exclude=secretos --exclude='*.pem' --exclude='*.key'
	--exclude=app/instalador/salida --exclude='*.exe' --exclude=.herramientas --exclude=servidor/despliegue/perfiles/generico.env)

# Los perfiles que solo existen en la copia instalada (perfiles/generico.env, creado por el
# instalador, o uno a medida hecho desde la plantilla) pasan a la copia nueva del código.
conservar_perfiles_locales() {
	local destino=$1 f
	for f in "$DIR_DESP"/perfiles/*.env; do
		if [[ -f $f && ! -e $destino/$(basename "$f") ]]; then
			cp -p "$f" "$destino/"
			info "Se conserva el perfil local $(basename "$f")"
		fi
	done
}

origen_valido() { [[ -f $REPO_ORIGEN/servidor/despliegue/docker-compose.yml && -f $REPO_ORIGEN/servidor/gateway/Dockerfile ]]; }

preparar_codigo() {
	local fecha rama=()
	if [[ -n $REPO_URL ]]; then
		command -v git >/dev/null || apt_instalar git
		if [[ -d $REPO/.git ]]; then
			ejecutar "Actualizando el código (git pull)" git -c safe.directory="$REPO" -C "$REPO" pull --ff-only ||
				morir "git pull ha fallado en $REPO."
		elif [[ -e $REPO ]]; then
			morir "$REPO ya existe y no es un repositorio git: muévelo o bórralo antes de usar --repo."
		else
			info "Clonando $(url_sin_credenciales "$REPO_URL") (si el repositorio es privado, git pedirá usuario y token)…"
			if [[ -n $RAMA ]]; then rama=(--branch "$RAMA"); fi
			git clone "${rama[@]}" "$REPO_URL" "$REPO" 2>&1 | url_sin_credenciales | tee -a "$REGISTRO" || morir "git clone ha fallado."
			ok "Código clonado en $REPO"
		fi
	elif [[ $(readlink -f "$REPO_ORIGEN") == "$(readlink -f "$REPO" 2>/dev/null || echo "$REPO")" ]]; then
		ok "Se usa el código de $REPO"
	else
		origen_valido || morir "Ejecuta el instalador desde una copia completa del repositorio de CidIA o usa --repo URL."
		if [[ -d $REPO/.git ]]; then
			aviso "$REPO ya es un repositorio git: no se sobrescribe. Para actualizarlo usa «sudo cidia actualizar»."
		elif [[ -d $REPO ]]; then
			# shellcheck disable=SC2016  # el guion de «bash -c» recibe sus valores como argumentos
			if confirmar "Ya hay una copia del código en $REPO. ¿Sustituirla por la de $REPO_ORIGEN?" s; then
				fecha=$(date +%Y%m%d-%H%M%S)
				mkdir -p "$DIR/cidia.nuevo"
				ejecutar "Copiando el código nuevo" bash -c 'set -o pipefail; tar -C "$1" "${@:3}" -cf - . | tar -C "$2" --no-same-owner -xf -' _ "$REPO_ORIGEN" "$DIR/cidia.nuevo" "${EXCLUSIONES[@]}" ||
					morir "No se ha podido copiar el código."
				conservar_perfiles_locales "$DIR/cidia.nuevo/servidor/despliegue/perfiles"
				rm -rf "$DIR/cidia.anterior"
				mv "$REPO" "$DIR/cidia.anterior"
				mv "$DIR/cidia.nuevo" "$REPO"
				ok "Código actualizado (la versión anterior queda en $DIR/cidia.anterior, $fecha)"
			else
				info "Se mantiene el código que ya había en $REPO."
			fi
		else
			mkdir -p "$REPO"
			# shellcheck disable=SC2016  # el guion de «bash -c» recibe sus valores como argumentos
			ejecutar "Copiando el código de $REPO_ORIGEN" bash -c 'set -o pipefail; tar -C "$1" "${@:3}" -cf - . | tar -C "$2" --no-same-owner -xf -' _ "$REPO_ORIGEN" "$REPO" "${EXCLUSIONES[@]}" ||
				morir "No se ha podido copiar el código."
		fi
	fi
	[[ -f $DIR_DESP/docker-compose.yml ]] || morir "Falta $DIR_DESP/docker-compose.yml: el código no está completo."
	# El perfil ya se comprobó con el código de origen; con --repo, se comprueba ahora en el clon.
	if [[ $PERFIL != generico && ! -f $DIR_DESP/perfiles/$PERFIL.env ]]; then
		morir "No existe el perfil «$PERFIL» en $DIR_DESP/perfiles. Usa msi, generico u oracle."
	fi
	calcular_modelos_perfil
	# Git en Windows puede perder el bit de ejecución: el script de initdb lo necesita.
	chmod +x "$DIR_DESP/instalar-servidor.sh" "$DIR_DESP/cidia" "$DIR_DESP"/postgres/initdb/*.sh 2>/dev/null || true
	if [[ -L $ENLACE_CIDIA || ! -e $ENLACE_CIDIA ]]; then
		ln -sfn "$HERRAMIENTA" "$ENLACE_CIDIA"
		ok "Orden de administración disponible: sudo cidia"
	else
		aviso "$ENLACE_CIDIA ya existe y no es de CidIA: usa $HERRAMIENTA"
	fi
}

# ----------------------------------------------------------------------------- 5. configuración

ENV_NUEVO=0
CABECERA_ANADIDOS=0
linea_env() {
	if ((!ENV_NUEVO && !CABECERA_ANADIDOS)); then
		printf '\n# Añadido por instalar-servidor.sh el %s\n' "$(date '+%d/%m/%Y %H:%M')" >>"$ENV_FILE"
		CABECERA_ANADIDOS=1
	fi
	printf '%s\n' "$1" >>"$ENV_FILE"
}
seccion_env() { if ((ENV_NUEVO)); then printf '\n# --- %s\n' "$1" >>"$ENV_FILE"; fi; }
fijar() { if [[ $(leer_var "$ENV_FILE" "$1") != "$2" ]] || ! tiene_var "$ENV_FILE" "$1"; then if tiene_var "$ENV_FILE" "$1"; then poner_var "$ENV_FILE" "$1" "$2"; else linea_env "$1=$2"; fi; fi; }
si_falta() { tiene_var "$ENV_FILE" "$1" || linea_env "$1=$2"; }
# El valor del secreto va directamente al fichero: nunca se muestra ni se guarda en el registro.
# Si openssl falla no se escribe nada (un secreto vacío ya no se regeneraría nunca).
secreto_si_falta() {
	local valor=""
	if tiene_var "$ENV_FILE" "$1"; then return 0; fi
	valor=$(openssl rand -hex "$2" 2>/dev/null) || true
	[[ $valor =~ ^[0-9a-f]+$ && ${#valor} -eq $(($2 * 2)) ]] || morir "No se ha podido generar el secreto $1 (¿falta openssl?)."
	linea_env "$1=$valor"
}

escribir_configuracion() {
	local perfil_anterior cambia_perfil=0 mem_ollama cpu_ollama cpu_asr hilos_asr asr contexto cargados
	local fichero_generico modelos=()
	ENV_NUEVO=0
	CABECERA_ANADIDOS=0

	# Con datos de una instalación anterior y sin sus secretos, la base de datos no se podría abrir.
	if "${DOCKER[@]}" volume inspect "${PROYECTO}_pg-datos" >/dev/null 2>&1 && ! tiene_var "$ENV_FILE" CIDIA_PG_PASSWORD; then
		morir "Hay una base de datos de una instalación anterior (volumen ${PROYECTO}_pg-datos) pero no sus secretos. Recupera secretos/cidia.env de una copia o usa --desinstalar para empezar de cero."
	fi
	if [[ ! -f $ENV_FILE ]]; then
		ENV_NUEVO=1
		(
			umask 077
			cat >"$ENV_FILE" <<EOF
# CidIA: configuración de esta instalación y secretos. NO lo compartas ni lo subas a git.
# Creado por instalar-servidor.sh el $(date '+%d/%m/%Y a las %H:%M'). Permisos 600 (solo root).
# Lo usan «docker compose --env-file» y la orden «cidia». Tras cambiarlo: sudo cidia arrancar
EOF
		)
	fi
	chmod 600 "$ENV_FILE"
	perfil_anterior=$(leer_var "$ENV_FILE" CIDIA_PERFIL)
	if [[ -n $perfil_anterior && $perfil_anterior != "$PERFIL" ]]; then cambia_perfil=1; fi

	seccion_env "Instalación"
	fijar CIDIA_PERFIL "$PERFIL"
	fijar CIDIA_DATOS "$DIR/datos"
	fijar CIDIA_DIRECCION "$DIRECCION"
	fijar CIDIA_PUERTO "$PUERTO"
	fijar CIDIA_IP_PUBLICACION "$IP_PUBLICACION"
	fijar CIDIA_URL_PUBLICA "http://$DIRECCION:$PUERTO"
	fijar CIDIA_COMPOSE_FICHEROS "$EXTRAS_COMPOSE"
	fijar CIDIA_COMPOSE_PERFILES "$PERFILES_COMPOSE"
	if [[ -n $PUERTO_OLLAMA ]]; then fijar CIDIA_PUERTO_OLLAMA "$PUERTO_OLLAMA"; fi
	if [[ -n $PUERTO_ASR ]]; then fijar CIDIA_PUERTO_ASR "$PUERTO_ASR"; fi
	if [[ -n $RED_BORDE ]]; then fijar CIDIA_RED_BORDE "$RED_BORDE"; fi
	if [[ -n $RED_INTERNA ]]; then fijar CIDIA_RED_INTERNA "$RED_INTERNA"; fi
	# El ejecutor del espacio de trabajo usa el socket de Docker con el grupo dueño del socket,
	# que cambia de un equipo a otro (el compose propone 120, el del servidor Oracle).
	if [[ -e $SOCKET_DOCKER ]]; then fijar CIDIA_DOCKER_GID "$(stat -c %g "$SOCKET_DOCKER")"; fi

	# Recursos según el equipo. Solo se escriben si faltan (o si cambia el perfil): el
	# administrador puede ajustarlos a mano en este fichero. Con GPU, la memoria de la gráfica va
	# aparte, pero Ollama usa RAM al cargar y para las capas que no caben (MSI de 32 GB: 24g).
	if ((GPU_USAR)); then mem_ollama=$((RAM_GIB * 75 / 100)); else mem_ollama=$((RAM_GIB * 50 / 100)); fi
	mem_ollama=$((mem_ollama < 4 ? 4 : mem_ollama))
	mem_ollama=$((mem_ollama > 24 ? 24 : mem_ollama))
	cpu_ollama=$((NUCLEOS > 4 ? NUCLEOS - 2 : (NUCLEOS > 1 ? NUCLEOS - 1 : 1)))
	cpu_ollama=$((cpu_ollama > 16 ? 16 : cpu_ollama))
	hilos_asr=$((NUCLEOS >= 8 ? 4 : (NUCLEOS >= 2 ? 2 : 1)))
	cpu_asr=$hilos_asr
	case $PERFIL in
	msi) asr=small contexto=32768 cargados=2 ;;
	oracle) asr=base contexto=8192 cargados=3 ;;
	*)
		asr=$( ((RAM_GIB >= 16)) && echo small || echo base)
		contexto=$( ((RAM_GIB >= 16)) && echo 16384 || echo 8192)
		cargados=2
		;;
	esac
	seccion_env "Recursos (ajústalos si hace falta y aplica con: sudo cidia arrancar)"
	local -a recursos=(
		"OLLAMA_CONTEXT_LENGTH=$contexto" "OLLAMA_NUM_PARALLEL=1" "OLLAMA_MAX_LOADED_MODELS=$cargados" "OLLAMA_KEEP_ALIVE=30m"
		"CIDIA_MEM_OLLAMA=${mem_ollama}g" "CIDIA_CPU_OLLAMA=${cpu_ollama}.0"
		"CIDIA_MEM_GATEWAY=$( ((RAM_GIB >= 16)) && echo 2g || echo 1g)" "CIDIA_CPU_GATEWAY=$( ((NUCLEOS >= 8)) && echo 2.0 || echo 1.0)"
		"CIDIA_MEM_POSTGRES=$( ((RAM_GIB >= 16)) && echo 1g || echo 512m)"
		"ASR_MODELO=$asr" "ASR_HILOS=$hilos_asr" "CIDIA_CPU_ASR=${cpu_asr}.0" "CIDIA_MEM_ASR=$([[ $asr == small ]] && echo 2g || echo 1536m)"
	)
	local r
	for r in "${recursos[@]}"; do
		if ((cambia_perfil)); then fijar "${r%%=*}" "${r#*=}"; else si_falta "${r%%=*}" "${r#*=}"; fi
	done

	seccion_env "Secretos (generados con openssl rand; no se muestran nunca)"
	secreto_si_falta CIDIA_PG_PASSWORD 32
	secreto_si_falta CIDIA_SECRETO_JWT 32
	secreto_si_falta CIDIA_ESPACIO_SECRETO 32
	secreto_si_falta CIDIA_REDIS_PASSWORD 32
	secreto_si_falta WEKNORA_DB_PASSWORD 32
	secreto_si_falta WEKNORA_JWT_SECRET 32
	secreto_si_falta WEKNORA_AES_KEY 16 # WeKnora exige exactamente 32 caracteres
	chmod 600 "$ENV_FILE"
	if ((ENV_NUEVO)); then ok "Configuración y secretos nuevos en $ENV_FILE (permisos 600)"; else ok "Configuración actualizada en $ENV_FILE; los secretos existentes se conservan"; fi

	# Perfil genérico: copia local de la plantilla con los modelos adecuados a este equipo.
	if [[ $PERFIL == generico ]]; then
		fichero_generico=$DIR_DESP/perfiles/generico.env
		if [[ ! -f $fichero_generico ]]; then
			[[ -f $DIR_DESP/perfiles/plantilla.env ]] || morir "Falta perfiles/plantilla.env para crear el perfil genérico."
			cp "$DIR_DESP/perfiles/plantilla.env" "$fichero_generico"
			chmod 644 "$fichero_generico"
			read -r -a modelos <<<"$(modelos_generico)"
			poner_var "$fichero_generico" CIDIA_LLM_MODELO_CHAT "${modelos[0]}"
			poner_var "$fichero_generico" CIDIA_LLM_MODELO_VISION "${modelos[1]}"
			poner_var "$fichero_generico" CIDIA_LLM_MODELO_EMBEDDINGS "${modelos[2]}"
			poner_var "$fichero_generico" CIDIA_ASR_MODELO "$asr"
			ok "Perfil genérico creado en perfiles/generico.env (modelos: ${modelos[*]})"
		fi
		poner_var "$fichero_generico" CIDIA_URL_PUBLICA "http://$DIRECCION:$PUERTO"
		calcular_modelos_perfil
	fi
}

preparar_compose() {
	local f lista=()
	DC_ARGS=(compose --project-directory "$DIR_DESP" --env-file "$ENV_FILE" -f "$DIR_DESP/docker-compose.yml")
	IFS=, read -r -a lista <<<"$EXTRAS_COMPOSE"
	for f in "${lista[@]}"; do
		if [[ -n $f && -f $DIR_DESP/compose.$f.yml ]]; then DC_ARGS+=(-f "$DIR_DESP/compose.$f.yml"); fi
	done
	IFS=, read -r -a lista <<<"$PERFILES_COMPOSE"
	for f in "${lista[@]}"; do
		if [[ -n $f ]]; then DC_ARGS+=(--profile "$f"); fi
	done
}

# ----------------------------------------------------------------------------- 6-7. imágenes y arranque

construir_imagenes() {
	local sandbox="" ayuda_pull
	ejecutar "Comprobando la configuración de Docker Compose" dc config --quiet || morir "La configuración de Compose no es válida (detalles en el registro)."
	ayuda_pull=$(dc pull --help 2>/dev/null) || true
	if grep -q -- --ignore-buildable <<<"$ayuda_pull"; then
		ejecutar "Descargando imágenes (PostgreSQL, Ollama…; la primera vez son varios GB)" dc pull --ignore-buildable || morir "No se han podido descargar las imágenes."
	else
		ejecutar "Descargando imágenes (PostgreSQL, Ollama…; la primera vez son varios GB)" dc pull --ignore-pull-failures || morir "No se han podido descargar las imágenes."
	fi
	ejecutar "Construyendo CidIA: gateway, interfaz web y voz (la primera vez, 5-15 minutos)" dc build ||
		morir "La construcción ha fallado. Revisa el registro (a menudo es la conexión a Internet o un proxy)."
	if [[ ,$PERFILES_COMPOSE, == *,espacio,* ]]; then
		if [[ -f $REPO/servidor/espacio-trabajo/sandbox/Dockerfile ]]; then sandbox=$REPO/servidor/espacio-trabajo/sandbox; fi
		if [[ -n $sandbox ]]; then
			ejecutar "Construyendo la imagen aislada del espacio de trabajo" "${DOCKER[@]}" build -t cidia-sandbox:local "$sandbox" ||
				morir "No se ha podido construir cidia-sandbox:local."
		else
			aviso "No encuentro la imagen del espacio de trabajo (servidor/espacio-trabajo/sandbox/Dockerfile)."
		fi
	fi
}

arrancar_servicios() {
	local host=127.0.0.1 t0 url registros_ollama
	ejecutar "Arrancando los servicios" dc up -d || morir "Los servicios no han arrancado (detalles en el registro)."
	if [[ $IP_PUBLICACION != 0.0.0.0 && $IP_PUBLICACION != 127.0.0.1 ]]; then host=$IP_PUBLICACION; fi
	url="http://$host:$PUERTO/salud"
	t0=$SECONDS
	while ((SECONDS - t0 < 300)); do
		if curl -fsS -m 4 "$url" >/dev/null 2>&1; then
			if ((TTY_SALIDA)); then printf '\r\e[K'; fi
			ok "CidIA responde en $url ($((SECONDS - t0)) s)"
			break
		fi
		if ((TTY_SALIDA)); then printf '\r  … esperando a que el gateway prepare la base de datos y responda (%d s)' "$((SECONDS - t0))"; fi
		sleep 3
	done
	if ! curl -fsS -m 4 "$url" >/dev/null 2>&1; then
		if ((TTY_SALIDA)); then printf '\r\e[K'; fi
		dc ps >>"$REGISTRO" 2>&1 || true
		dc logs --tail 80 gateway >>"$REGISTRO" 2>&1 || true
		dc logs --tail 12 gateway 2>&1 | sed 's/^/      /' >&2 || true
		morir "El gateway no responde en $url tras 5 minutos."
	fi
	if ((GPU_USAR)); then
		registros_ollama=$(dc logs --tail 400 ollama 2>&1) || true
		if grep -qiE 'library=cuda' <<<"$registros_ollama"; then
			ok "Ollama usa la GPU (CUDA)"
		else
			aviso "Ollama no indica que use la GPU todavía. Compruébalo cuando cargue un modelo: sudo cidia estado"
		fi
	fi
}

ajustar_energia() {
	if ((!AJUSTAR_ENERGIA)); then return 0; fi
	ejecutar "Desactivando la suspensión y la hibernación" systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target ||
		{
			aviso "No se ha podido desactivar la suspensión."
			return 0
		}
	if ((ES_PORTATIL)); then
		mkdir -p /etc/systemd/logind.conf.d
		cat >/etc/systemd/logind.conf.d/50-cidia.conf <<'EOF'
# CidIA: el servidor sigue funcionando con la tapa cerrada (lo creó instalar-servidor.sh).
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
EOF
		ok "Cerrar la tapa no suspenderá el equipo (se aplica del todo tras reiniciar)"
	fi
}

# ----------------------------------------------------------------------------- 10. resumen

resumen_final() {
	local usuario="" clave="" url_portatiles fichero_admin=$DIR/secretos/admin-inicial.txt
	url_portatiles="http://$DIRECCION:$PUERTO"
	if [[ -f $fichero_admin ]]; then
		usuario=$(sed -n 's/^Usuario: //p' "$fichero_admin")
		clave=$(sed -n 's/^Contraseña: //p' "$fichero_admin")
	fi
	printf '\n%s%s%s\n' "$C_N$C_VERDE" "CidIA está instalado y en marcha." "$C_R"
	reg "== Instalación terminada"
	printf '\n'
	if [[ $IP_PUBLICACION == 127.0.0.1 ]]; then
		printf '  %sSolo local:%s los portátiles todavía no llegan. Para publicarlo en la red: %ssudo cidia abrir-puerto%s\n' "$C_AMAR" "$C_R" "$C_N" "$C_R"
		printf '  Desde este equipo:                    http://127.0.0.1:%s/app/\n' "$PUERTO"
	else
		printf '  Dirección para el instalador de los portátiles:  %s%s%s\n' "$C_N" "$url_portatiles" "$C_R"
		printf '  Desde un navegador:                              %s%s/app/%s\n' "$C_N" "$url_portatiles" "$C_R"
	fi
	if [[ -n $ADMIN_NUEVO && -n $clave ]]; then
		printf '\n  Cuenta de administración (se muestra solo esta vez):\n'
		printf '    Usuario:     %s%s%s\n' "$C_N" "$usuario" "$C_R"
		printf '    Contraseña:  %s%s%s\n' "$C_N" "$clave" "$C_R"
		printf '  %sTambién queda en %s (solo root): cámbiala al entrar y borra ese fichero.%s\n' "$C_T" "$fichero_admin" "$C_R"
	elif [[ -f $fichero_admin ]]; then
		printf '\n  La contraseña inicial de administración sigue en %s (sudo cat). Cámbiala y borra el fichero.\n' "$fichero_admin"
	else
		printf '\n  La cuenta de administración ya existía. Si no recuerdas la contraseña: %ssudo cidia admin-restablecer%s\n' "$C_N" "$C_R"
	fi
	if [[ -f $DIR/datos/usuarios-demo.txt ]]; then
		printf '  %sUsuarios de demostración: su contraseña está en %s/datos/usuarios-demo.txt (sudo cat).%s\n' "$C_T" "$DIR" "$C_R"
	fi
	printf '\n  %sSiguientes pasos%s\n' "$C_N" "$C_R"
	printf '   1. Comprueba el estado:  sudo cidia estado\n'
	if [[ $IP_PUBLICACION != 127.0.0.1 ]]; then
		printf '   2. Cortafuegos: deja entrar solo a la red de la empresa al puerto %s (manual, «Cortafuegos»).\n' "$PUERTO"
		printf '   3. Desde un portátil, abre %s/app/ y entra con la cuenta de administración.\n' "$url_portatiles"
	else
		printf '   2. Publica CidIA en la red cuando quieras:  sudo cidia abrir-puerto\n'
		printf '   3. Desde este equipo, abre http://127.0.0.1:%s/app/ y entra con la cuenta de administración.\n' "$PUERTO"
	fi
	printf '   4. Crea departamentos, niveles y personas en Administración.\n'
	printf '   5. Instala CidIA-Setup.exe en los portátiles y escribe la dirección de arriba.\n'
	printf '   6. Programa copias de seguridad:  sudo cidia copia  (manual, «Copias de seguridad»).\n'
	if ((${#AVISOS[@]})); then
		printf '\n  %sAvisos durante la instalación:%s\n' "$C_AMAR" "$C_R"
		printf '   · %s\n' "${AVISOS[@]}"
	fi
	printf '\n  Registro de la instalación: %s\n  Manual: %s/docs/manual-servidor.md\n\n' "$REGISTRO" "$REPO"
}

# ----------------------------------------------------------------------------- modos

ADMIN_NUEVO=""

modo_instalar() {
	local res faltan=() m cid
	PASOS_TOTAL=10
	# Se instala en una carpeta propia: en / o en /home/<usuario> el instalador cambiaría los
	# permisos de esa carpeta y la desinstalación se negaría a limpiarla.
	if carpeta_protegida "$DIR"; then morir "No se puede instalar directamente en $DIR: usa una carpeta propia, como /opt/cidia (--dir)."; fi
	paso "Comprobaciones del equipo"
	comprobar_equipo
	((ERRORES == 0)) || morir "El equipo no cumple los requisitos mínimos (ver arriba)."
	[[ $SO_ID == ubuntu || $SO_ID == debian || $DOCKER_CLI == 1 ]] || morir "Este sistema no es Ubuntu y no tiene Docker: instala Ubuntu 22.04 o 24.04."

	paso "Opciones de esta instalación"
	if [[ -e $ENV_FILE ]]; then info "Hay una instalación en $DIR: se conservan sus datos y secretos."; fi
	decidir_opciones
	printf '\n'
	mostrar_resumen_opciones
	if ((INTERACTIVO && !SI)); then
		confirmar "¿Empezar la instalación?" s || {
			info "No se ha cambiado nada."
			exit 0
		}
	fi

	paso "Docker Engine y soporte de GPU"
	instalar_docker
	instalar_toolkit_nvidia

	paso "Carpetas y código de CidIA"
	preparar_carpetas
	preparar_codigo

	paso "Configuración y secretos"
	escribir_configuracion
	preparar_compose

	paso "Imágenes de los servicios"
	construir_imagenes

	paso "Arranque de los servicios"
	arrancar_servicios

	paso "Modelos de IA"
	if ((SIN_MODELOS)); then
		info "Omitido (--sin-modelos). Descárgalos cuando quieras con: sudo cidia modelos descargar"
	else
		info "Modelos del perfil $PERFIL: ${MODELOS_PERFIL[*]}"
		if ! CIDIA_REGISTRO="$REGISTRO" bash "$HERRAMIENTA" --dir "$DIR" modelos descargar; then
			aviso "Faltan modelos por descargar. Reinténtalo con: sudo cidia modelos descargar"
		fi
	fi

	paso "Cuenta de administración"
	if res=$(CIDIA_REGISTRO="$REGISTRO" bash "$HERRAMIENTA" --dir "$DIR" _admin-inicial "$DIR/secretos/admin-inicial.txt"); then
		res=$(tail -n1 <<<"$res")
		case $res in
		CREADO*)
			ADMIN_NUEVO=${res#* }
			ok "Cuenta de administración «$ADMIN_NUEVO» creada (contraseña generada al azar)"
			;;
		EXISTE*) ok "Ya existe la cuenta de administración «${res#* }»: no se cambia" ;;
		*) aviso "Respuesta inesperada al crear la cuenta de administración: $res" ;;
		esac
	else
		aviso "No se ha podido crear la cuenta de administración. Prueba con: sudo cidia admin-restablecer"
	fi

	paso "Ajustes finales"
	ajustar_energia
	cid=$(contenedor ollama)
	if [[ -n $cid ]] && ((!SIN_MODELOS)); then
		for m in "${MODELOS_PERFIL[@]}"; do
			"${DOCKER[@]}" exec "$cid" ollama show "$m" >/dev/null 2>&1 || faltan+=("$m")
		done
		if ((${#faltan[@]})); then aviso "Faltan modelos: ${faltan[*]} (sudo cidia modelos descargar)"; else ok "Modelos del perfil disponibles"; fi
	fi
	resumen_final
}

modo_comprobar() {
	PASOS_TOTAL=3
	INTERACTIVO=0
	paso "Comprobaciones del equipo"
	comprobar_equipo
	paso "Instalación existente"
	comprobar_instalacion
	paso "Qué haría el instalador (no se cambia nada)"
	decidir_opciones
	mostrar_resumen_opciones
	if carpeta_protegida "$DIR"; then fallo "En $DIR no se puede instalar: usa una carpeta propia, como /opt/cidia (--dir)."; fi
	if ((DOCKER_CLI)); then info "Docker: ya instalado, no se tocaría."; else info "Docker: se instalaría Docker Engine desde download.docker.com."; fi
	if ((GPU_USAR && !TOOLKIT_OK)); then info "GPU: se instalaría el NVIDIA Container Toolkit."; fi
	mostrar_modelos_pendientes
	printf '\n'
	if ((ERRORES)); then
		printf '  %sResultado: %s y %s. No se ha cambiado nada.%s\n' "$C_ROJO" "$(plural "$ERRORES" problema)" "$(plural "${#AVISOS[@]}" aviso)" "$C_R"
	else
		printf '  %sResultado: sin problemas (%s). No se ha cambiado nada.%s\n' "$C_VERDE" "$(plural "${#AVISOS[@]}" aviso)" "$C_R"
	fi
	printf '  Registro: %s\n\n' "$REGISTRO"
	if ((ERRORES)); then exit 1; fi
	return 0
}

# plural N palabra -> «1 aviso», «3 avisos».
plural() { if (($1 == 1)); then printf '1 %s' "$2"; else printf '%d %ss' "$1" "$2"; fi; }

mostrar_modelos_pendientes() {
	local cid m lista faltan=()
	cid=$(contenedor ollama)
	if [[ -z $cid ]]; then
		info "Modelos: se descargarían ${MODELOS_PERFIL[*]}"
		return 0
	fi
	lista=$("${DOCKER[@]}" exec "$cid" ollama list 2>/dev/null | awk 'NR > 1 { print $1 }') || true
	for m in "${MODELOS_PERFIL[@]}"; do
		[[ $m == *:* ]] || m="$m:latest"
		grep -qxF "$m" <<<"$lista" || faltan+=("$m")
	done
	if ((${#faltan[@]})); then info "Modelos: se descargarían ${faltan[*]}"; else ok "Modelos del perfil ya descargados: ${MODELOS_PERFIL[*]}"; fi
}

# Carpetas en las que no se instala ni se borra aunque se pasen con --dir (raíz, sistema y
# carpetas personales).
carpeta_protegida() {
	case $1 in
	'' | / | /bin | /boot | /dev | /etc | /home | /lib | /lib64 | /media | /mnt | /opt | /proc | /root | /run | /sbin | /srv | /sys | /tmp | /usr | /var | /var/lib) return 0 ;;
	/home/* | /Users/*) [[ $1 != /home/*/* && $1 != /Users/*/* ]] && return 0 ;;
	esac
	return 1
}

# Lo que la instalación crea dentro de su carpeta: solo esto se borra.
PARTES_CIDIA=(cidia cidia.nuevo cidia.anterior datos secretos registros copias)

modo_desinstalar() {
	local resp conservar=0 ids vols imagenes=() terceros=() i n restos parte
	PASOS_TOTAL=3
	paso "Qué se va a borrar"
	if [[ -z $DIR ]] || carpeta_protegida "$DIR"; then morir "No se puede desinstalar desde $DIR: indica la carpeta de CidIA con --dir."; fi
	if [[ ! -f $DIR/secretos/cidia.env && ! -f $DIR_DESP/docker-compose.yml ]] && [[ -z $("${DOCKER[@]}" ps -aq --filter "$ETIQUETA" 2>/dev/null) ]]; then
		morir "No encuentro ninguna instalación de CidIA en $DIR (indica la carpeta con --dir)."
	fi
	n=$("${DOCKER[@]}" ps -aq --filter "$ETIQUETA" 2>/dev/null | wc -l) || n=0
	info "Contenedores del proyecto cidia: $n"
	vols=$("${DOCKER[@]}" volume ls -q --filter "$ETIQUETA" 2>/dev/null | paste -sd ' ') || true
	info "Volúmenes (base de datos, modelos, WeKnora): ${vols:-ninguno}"
	info "Redes cidia-borde y cidia-interna, e imágenes construidas cidia-*:local"
	if [[ -d $DIR ]]; then
		info "En $DIR ($(du -sh "$DIR" 2>/dev/null | cut -f1)): código, datos, secretos, registros y copias"
	fi
	if [[ -L $ENLACE_CIDIA ]]; then info "La orden $ENLACE_CIDIA"; fi
	tenue "No se tocan: Docker, el NVIDIA Container Toolkit, otros contenedores ni las imágenes de terceros."
	if [[ -f $DIR_DESP/docker-compose.yml ]]; then
		mapfile -t terceros < <(sed -n 's/^[[:space:]]*image:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "$DIR_DESP/docker-compose.yml" | { grep -v '^cidia-' || true; } | sort -u)
	fi
	if ((!SI)); then
		((INTERACTIVO)) || morir "Para desinstalar sin terminal añade --si (borra los datos de verdad)."
		printf '\n  %sSe borrarán de verdad la base de datos, los documentos, los modelos y los secretos de CidIA.%s\n' "$C_ROJO$C_N" "$C_R"
		read -r -p "  Escribe BORRAR para continuar: " resp || true
		if [[ $resp != BORRAR ]]; then
			info "No se ha borrado nada."
			exit 0
		fi
	fi
	if [[ -n $(find "$DIR/copias" -mindepth 1 -maxdepth 1 2>/dev/null | head -n1) ]] && confirmar "¿Conservar las copias de seguridad de $DIR/copias?" s; then
		conservar=1
	fi

	paso "Parando y borrando contenedores, volúmenes, redes e imágenes de CidIA"
	if [[ -f $DIR_DESP/docker-compose.yml ]]; then
		if [[ -r $ENV_FILE ]]; then
			DC_ARGS=(compose --project-directory "$DIR_DESP" --env-file "$ENV_FILE" -f "$DIR_DESP/docker-compose.yml" --profile weknora --profile espacio)
		else
			# Sin secretos, compose exige igualmente las variables obligatorias: valores de relleno.
			export CIDIA_PG_PASSWORD=x CIDIA_SECRETO_JWT=x CIDIA_ESPACIO_SECRETO=x
			DC_ARGS=(compose --project-directory "$DIR_DESP" -f "$DIR_DESP/docker-compose.yml" --profile weknora --profile espacio)
		fi
		ejecutar "docker compose down (contenedores, redes y volúmenes de cidia)" dc down -v --remove-orphans ||
			aviso "compose down no ha terminado bien: se sigue por etiquetas."
	fi
	# Lo que quede, siempre filtrado por la etiqueta del proyecto cidia.
	ids=$("${DOCKER[@]}" ps -aq --filter "$ETIQUETA" | paste -sd ' ') || true
	if [[ -n $ids ]]; then
		# shellcheck disable=SC2086  # lista de identificadores separados por espacios
		if "${DOCKER[@]}" rm -f $ids >>"$REGISTRO" 2>&1; then ok "Contenedores restantes borrados"; fi
	fi
	ids=$("${DOCKER[@]}" ps -aq --filter label=cidia.espacio=1 | paste -sd ' ') || true
	if [[ -n $ids ]]; then
		# shellcheck disable=SC2086
		if "${DOCKER[@]}" rm -f $ids >>"$REGISTRO" 2>&1; then ok "Contenedores del espacio de trabajo borrados"; fi
	fi
	vols=$("${DOCKER[@]}" volume ls -q --filter "$ETIQUETA" | paste -sd ' ') || true
	if [[ -n $vols ]]; then
		# shellcheck disable=SC2086
		if "${DOCKER[@]}" volume rm $vols >>"$REGISTRO" 2>&1; then ok "Volúmenes borrados: $vols"; else aviso "No se han podido borrar los volúmenes: $vols"; fi
	fi
	for i in cidia-borde cidia-interna; do
		if [[ $("${DOCKER[@]}" network inspect -f '{{index .Labels "com.docker.compose.project"}}' "$i" 2>/dev/null) == "$PROYECTO" ]]; then
			if "${DOCKER[@]}" network rm "$i" >>"$REGISTRO" 2>&1; then ok "Red $i borrada"; fi
		fi
	done
	for i in cidia-gateway:local cidia-asr:local cidia-espacio:local cidia-sandbox:local; do
		if "${DOCKER[@]}" image inspect "$i" >/dev/null 2>&1; then imagenes+=("$i"); fi
	done
	if ((${#imagenes[@]})); then
		if "${DOCKER[@]}" image rm "${imagenes[@]}" >>"$REGISTRO" 2>&1; then ok "Imágenes borradas: ${imagenes[*]}"; fi
	fi

	paso "Borrando los ficheros de CidIA"
	if [[ -L $ENLACE_CIDIA && $(readlink "$ENLACE_CIDIA") == "$DIR"/* ]]; then
		rm -f "$ENLACE_CIDIA"
		ok "Orden $ENLACE_CIDIA eliminada"
	fi
	if [[ -f /etc/systemd/logind.conf.d/50-cidia.conf ]]; then
		rm -f /etc/systemd/logind.conf.d/50-cidia.conf
		ok "Ajuste de la tapa del portátil eliminado"
	fi
	cd /
	if [[ -d $DIR ]]; then
		for parte in "${PARTES_CIDIA[@]}"; do
			if [[ $parte == copias ]] && ((conservar)); then continue; fi
			if [[ -e $DIR/$parte ]]; then rm -rf -- "${DIR:?}/$parte"; fi
		done
		find "$DIR" -mindepth 1 -maxdepth 1 -name 'datos.previo-*' -exec rm -rf -- {} +
		restos=$(find "$DIR" -mindepth 1 -maxdepth 1 2>/dev/null | head -n5) || true
		if [[ -z $restos ]]; then
			rmdir "$DIR"
			ok "Carpeta $DIR borrada"
		elif ((conservar)) && [[ $restos == "$DIR/copias" ]]; then
			ok "Carpeta $DIR borrada salvo $DIR/copias"
		else
			ok "Ficheros de CidIA borrados de $DIR"
			aviso "En $DIR quedan ficheros que no son de CidIA y no se han tocado."
		fi
	fi
	printf '\n  %sCidIA se ha desinstalado.%s\n' "$C_N$C_VERDE" "$C_R"
	if [[ $(systemctl is-enabled sleep.target 2>/dev/null) == masked ]]; then
		tenue "La suspensión sigue desactivada. Para volver a activarla:"
		tenue "sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target"
	fi
	if ((${#terceros[@]})); then
		tenue "Las imágenes de terceros se conservan por si las usa otro proyecto. Si no, puedes borrarlas con:"
		tenue "sudo docker image rm ${terceros[*]}"
	fi
	printf '  Registro: %s\n\n' "$REGISTRO"
}

# ----------------------------------------------------------------------------- arranque

main() {
	leer_opciones "$@"

	# Instalar y desinstalar necesitan root; comprobar no (solo lee).
	if [[ $MODO != comprobar ]] && ((EUID != 0)); then
		command -v sudo >/dev/null || {
			echo "Hacen falta permisos de administrador (root)." >&2
			exit 1
		}
		echo "Hacen falta permisos de administrador: se vuelve a ejecutar con sudo."
		if [[ -z $DIR && -n ${CIDIA_DIR:-} ]]; then
			exec sudo -- bash "$SCRIPT" --dir "$CIDIA_DIR" "${ARGS_ORIGINALES[@]}"
		fi
		exec sudo -- bash "$SCRIPT" "${ARGS_ORIGINALES[@]}"
	fi

	preparar_docker_cli
	detectar_dir
	REGISTRO=$(mktemp "${TMPDIR:-/tmp}/cidia-$MODO-$(date +%Y%m%d-%H%M%S)-XXXX.log")
	chmod 640 "$REGISTRO"
	reg "instalar-servidor.sh $MODO · argumentos: $(url_sin_credenciales "${ARGS_ORIGINALES[*]:-ninguno}") · usuario $(id -un) · carpeta $DIR"

	printf '\n%sCidIA · instalador del servidor%s  %s(%s)%s\n' "$C_N" "$C_R" "$C_T" \
		"$([[ $MODO == comprobar ]] && echo "solo comprobación" || echo "$MODO")" "$C_R"
	case $MODO in
	instalar) modo_instalar ;;
	comprobar) modo_comprobar ;;
	desinstalar) modo_desinstalar ;;
	esac
}

# La última línea llama a main y sale en la misma orden: así, si el propio fichero cambia
# mientras se ejecuta (copia o git pull del código), la ejecución en curso no se ve afectada.
main "$@"; exit $?
