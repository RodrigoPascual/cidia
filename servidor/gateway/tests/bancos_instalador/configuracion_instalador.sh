#!/usr/bin/env bash
# Instalador: secretos/cidia.env (secretos, recursos, idempotencia) y perfil genérico.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

DIR=$BANCO/opt/cidia
fijar_rutas
mkdir -p "$DIR/secretos" "$DIR_DESP/perfiles"
cp "$BANCO/repo/servidor/despliegue/perfiles/plantilla.env" "$DIR_DESP/perfiles/"
REGISTRO=$BANCO/registro.log
SOCKET_DOCKER=$BANCO/docker.sock
: >"$SOCKET_DOCKER"
RAM_GIB=32 NUCLEOS=16 GPU_USAR=1 PERFIL=msi DIRECCION=192.168.1.50 PUERTO=18700 IP_PUBLICACION=0.0.0.0
EXTRAS_COMPOSE=gpu PERFILES_COMPOSE=espacio PUERTO_OLLAMA="" PUERTO_ASR="" RED_BORDE="" RED_INTERNA=""
SECRETOS='^(CIDIA_PG_PASSWORD|CIDIA_SECRETO_JWT|CIDIA_ESPACIO_SECRETO|CIDIA_REDIS_PASSWORD|WEKNORA_DB_PASSWORD|WEKNORA_JWT_SECRET|WEKNORA_AES_KEY)='

echo "== Instalación nueva con el perfil msi"
escribir_configuracion >/dev/null
comprobar "existe cidia.env" '[[ -f $ENV_FILE ]]'
comprobar "sin claves duplicadas" '[[ -z $(grep -oE "^[A-Z_]+=" "$ENV_FILE" | sort | uniq -d) ]]'
comprobar "7 secretos" '[[ $(grep -cE "$SECRETOS" "$ENV_FILE") == 7 ]]'
comprobar "CIDIA_PG_PASSWORD de 64 hex" '[[ $(leer_var "$ENV_FILE" CIDIA_PG_PASSWORD) =~ ^[0-9a-f]{64}$ ]]'
comprobar "WEKNORA_AES_KEY de 32 caracteres" '[[ $(leer_var "$ENV_FILE" WEKNORA_AES_KEY) =~ ^[0-9a-f]{32}$ ]]'
comprobar "secretos distintos" '[[ $(leer_var "$ENV_FILE" CIDIA_PG_PASSWORD) != $(leer_var "$ENV_FILE" CIDIA_SECRETO_JWT) ]]'
comprobar "contexto 32768 en msi" '[[ $(leer_var "$ENV_FILE" OLLAMA_CONTEXT_LENGTH) == 32768 ]]'
comprobar "memoria de Ollama 24g con GPU y 32 GB" '[[ $(leer_var "$ENV_FILE" CIDIA_MEM_OLLAMA) == 24g ]]'
comprobar "CPU de Ollama 14.0 con 16 núcleos" '[[ $(leer_var "$ENV_FILE" CIDIA_CPU_OLLAMA) == 14.0 ]]'
comprobar "voz small en msi" '[[ $(leer_var "$ENV_FILE" ASR_MODELO) == small ]]'
comprobar "compose con GPU" '[[ $(leer_var "$ENV_FILE" CIDIA_COMPOSE_FICHEROS) == gpu ]]'
comprobar "grupo del socket de Docker" '[[ $(leer_var "$ENV_FILE" CIDIA_DOCKER_GID) == $(stat -c %g "$SOCKET_DOCKER") ]]'
comprobar "URL pública" '[[ $(leer_var "$ENV_FILE" CIDIA_URL_PUBLICA) == http://192.168.1.50:18700 ]]'
comprobar "el registro no contiene secretos" '! grep -qF "$(leer_var "$ENV_FILE" CIDIA_PG_PASSWORD)" "$REGISTRO" 2>/dev/null'
copia=$(cat "$ENV_FILE")

echo "== Segunda ejecución con lo mismo"
escribir_configuracion >/dev/null
comprobar "el fichero no cambia" '[[ $(cat "$ENV_FILE") == "$copia" ]]'

echo "== Cambio de puerto"
PUERTO=18800
escribir_configuracion >/dev/null
comprobar "puerto 18800" '[[ $(leer_var "$ENV_FILE" CIDIA_PUERTO) == 18800 ]]'
comprobar "URL pública con el puerto nuevo" '[[ $(leer_var "$ENV_FILE" CIDIA_URL_PUBLICA) == http://192.168.1.50:18800 ]]'
comprobar "los secretos no cambian" '[[ $(grep -E "$SECRETOS" "$ENV_FILE") == $(grep -E "$SECRETOS" <<<"$copia") ]]'

echo "== Instalación manual previa (como la de Oracle)"
printf 'CIDIA_PG_PASSWORD=previo1\nCIDIA_SECRETO_JWT=previo2\nCIDIA_DATOS=/x/datos\nCIDIA_PERFIL=oracle\n' >"$ENV_FILE"
PERFIL=oracle GPU_USAR=0 EXTRAS_COMPOSE=debug PUERTO=18700 IP_PUBLICACION=127.0.0.1 RAM_GIB=23 NUCLEOS=4
escribir_configuracion >/dev/null
comprobar "conserva los secretos existentes" '[[ $(leer_var "$ENV_FILE" CIDIA_PG_PASSWORD) == previo1 && $(leer_var "$ENV_FILE" CIDIA_SECRETO_JWT) == previo2 ]]'
comprobar "añade los que faltan" '[[ $(grep -cE "$SECRETOS" "$ENV_FILE") == 7 ]]'
comprobar "una sola cabecera de añadidos" '[[ $(grep -c "Añadido por instalar-servidor.sh" "$ENV_FILE") == 1 ]]'
comprobar "CIDIA_DATOS corregido en su línea" '[[ $(sed -n 3p "$ENV_FILE") == "CIDIA_DATOS=$DIR/datos" ]]'
comprobar "contexto 8192 en oracle" '[[ $(leer_var "$ENV_FILE" OLLAMA_CONTEXT_LENGTH) == 8192 ]]'

echo "== Sin openssl no se escribe un secreto vacío (luego ya no se regeneraría)"
rm -f "$ENV_FILE"
openssl() { return 1; }
falla "la configuración se detiene" escribir_configuracion
unset -f openssl
comprobar "sin secretos vacíos" '! grep -qE "^(CIDIA_PG_PASSWORD|CIDIA_SECRETO_JWT)=" "$ENV_FILE"'
escribir_configuracion >/dev/null
comprobar "al repetir con openssl se generan" '[[ $(leer_var "$ENV_FILE" CIDIA_PG_PASSWORD) =~ ^[0-9a-f]{64}$ ]]'

echo "== Base de datos de una instalación anterior sin sus secretos"
rm -f "$ENV_FILE"
docker() { [[ $1 == volume ]]; }
falla "se detiene" escribir_configuracion
docker() { return 1; }
comprobar "y no crea un cidia.env nuevo" '[[ ! -e $ENV_FILE ]]'

echo "== Perfil genérico con 12 GB"
PERFIL=generico RAM_GIB=12 NUCLEOS=8 GPU_USAR=0 EXTRAS_COMPOSE="" IP_PUBLICACION=0.0.0.0
escribir_configuracion >/dev/null
G=$DIR_DESP/perfiles/generico.env
comprobar "generico.env creado" '[[ -f $G ]]'
comprobar "chat qwen3:1.7b" '[[ $(leer_var "$G" CIDIA_LLM_MODELO_CHAT) == qwen3:1.7b ]]'
comprobar "visión qwen3.5:0.8b" '[[ $(leer_var "$G" CIDIA_LLM_MODELO_VISION) == qwen3.5:0.8b ]]'
comprobar "embeddings como en el MSI" '[[ $(leer_var "$G" CIDIA_LLM_MODELO_EMBEDDINGS) == qwen3-embedding:0.6b ]]'
comprobar "URL pública en el perfil local" '[[ $(leer_var "$G" CIDIA_URL_PUBLICA) == http://192.168.1.50:18700 ]]'
comprobar "voz base con 12 GB" '[[ $(leer_var "$ENV_FILE" ASR_MODELO) == base ]]'
comprobar "modelos del perfil" '[[ "${MODELOS_PERFIL[*]}" == "qwen3:1.7b qwen3.5:0.8b qwen3-embedding:0.6b" ]]'
terminar
