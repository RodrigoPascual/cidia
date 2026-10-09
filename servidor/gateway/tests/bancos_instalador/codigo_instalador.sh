#!/usr/bin/env bash
# Instalador: copia del código al servidor (sin secretos ni datos) y perfiles locales.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

# Repositorio de origen con lo que nunca debe llegar al servidor.
ORIGEN=$BANCO/origen
mkdir -p "$ORIGEN/servidor/despliegue/perfiles" "$ORIGEN/servidor/gateway/datos" "$ORIGEN/servidor/web/node_modules/x" "$ORIGEN/secretos"
cp "$BANCO/repo/servidor/despliegue/perfiles/"*.env "$ORIGEN/servidor/despliegue/perfiles/"
rm -f "$ORIGEN/servidor/despliegue/perfiles/generico.env"
echo "services: {}" >"$ORIGEN/servidor/despliegue/docker-compose.yml"
printf '#!/usr/bin/env bash\n' >"$ORIGEN/servidor/despliegue/cidia"
echo "FROM scratch" >"$ORIGEN/servidor/gateway/Dockerfile"
echo "CIDIA_BASE_DATOS_URL=postgresql://usuario:clave@host/cidia" >"$ORIGEN/servidor/gateway/.env"
echo "documento" >"$ORIGEN/servidor/gateway/datos/doc.pdf"
echo "x" >"$ORIGEN/servidor/web/node_modules/x/index.js"
echo "x" >"$ORIGEN/secretos/cidia.env"
echo "clave" >"$ORIGEN/servidor/servidor.key"
REPO_ORIGEN=$ORIGEN

# Instalación existente con un perfil a medida que solo está en la copia instalada.
DIR=$BANCO/opt/cidia
fijar_rutas
mkdir -p "$DIR_DESP/perfiles"
echo "services: {}" >"$DIR_DESP/docker-compose.yml"
printf 'CIDIA_LLM_MODELO_CHAT=mi-modelo:8b\n' >"$DIR_DESP/perfiles/mi-planta.env"
printf 'CIDIA_LLM_MODELO_CHAT=qwen3:1.7b\n' >"$DIR_DESP/perfiles/generico.env"
echo "viejo" >"$DIR_DESP/perfiles/msi.env"
REGISTRO=$BANCO/registro.log
: >"$REGISTRO"
ENLACE_CIDIA=$BANCO/bin/cidia
mkdir -p "$BANCO/bin"
SI=1 TTY_SALIDA=0 PERFIL=mi-planta REPO_URL=""

preparar_codigo >/dev/null
comprobar "código nuevo en su sitio" '[[ -f $REPO/servidor/gateway/Dockerfile ]]'
comprobar "la versión anterior se guarda" '[[ -d $DIR/cidia.anterior ]]'
comprobar "no copia .env" '[[ ! -e $REPO/servidor/gateway/.env ]]'
comprobar "no copia datos/" '[[ ! -e $REPO/servidor/gateway/datos ]]'
comprobar "no copia node_modules" '[[ ! -e $REPO/servidor/web/node_modules ]]'
comprobar "no copia secretos/" '[[ ! -e $REPO/secretos ]]'
comprobar "no copia claves privadas" '[[ ! -e $REPO/servidor/servidor.key ]]'
comprobar "conserva el perfil a medida" '[[ $(leer_var "$DIR_DESP/perfiles/mi-planta.env" CIDIA_LLM_MODELO_CHAT) == mi-modelo:8b ]]'
comprobar "conserva el perfil genérico" '[[ -f $DIR_DESP/perfiles/generico.env ]]'
comprobar "los perfiles del repositorio se actualizan" '[[ $(cat "$DIR_DESP/perfiles/msi.env") != viejo ]]'
comprobar "modelos del perfil a medida" '[[ "${MODELOS_PERFIL[*]}" == mi-modelo:8b ]]'

# Un perfil que no existe en el código (por ejemplo, con --repo) se rechaza tras copiarlo.
PERFIL=inexistente
falla "perfil inexistente rechazado" preparar_codigo
terminar
