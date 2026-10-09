#!/usr/bin/env bash
# Herramienta cidia: contraseñas, tamaños, modelos, direcciones, abrir/cerrar puerto y órdenes.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

for _ in 1 2 3 4 5; do
	c=$(generar_contrasena)
	comprobar "formato de contraseña" '[[ $c =~ ^[A-HJ-NP-Za-km-z2-9]{4}(-[A-HJ-NP-Za-km-z2-9]{4}){3}$ ]]'
done
comprobar "contraseñas distintas" '[[ $(generar_contrasena) != $(generar_contrasena) ]]'
comprobar "512 B" '[[ $(legible 512) == "512 B" ]]'
comprobar "1,5 GB" '[[ $(legible 1500000000) == "1,5 GB" ]]'
comprobar "modelo sin etiqueta" '[[ $(normalizar_modelo <<<nomic-embed-text) == nomic-embed-text:latest ]]'

DIR=$BANCO/inst/../inst
detectar_dir
comprobar "ruta canónica" '[[ $DIR == "$BANCO/inst" ]]'
mkdir -p "$DIR_DESP/perfiles" "$DIR/secretos" "$COPIAS"
cp "$BANCO/repo/servidor/despliegue/perfiles/msi.env" "$DIR_DESP/perfiles/"
printf 'CIDIA_PERFIL=msi\nCIDIA_IP_PUBLICACION=0.0.0.0\nCIDIA_DIRECCION=192.168.1.50\nCIDIA_PUERTO=18700\n' >"$ENV_FILE"
comprobar "modelos del perfil msi" '[[ $(modelos_del_perfil | paste -sd " ") == "ministral-3:8b qwen3-embedding:0.6b" ]]'
calcular_urls
comprobar "URL de los portátiles" '[[ $URL_PORTATILES == http://192.168.1.50:18700 ]]'
comprobar "URL local" '[[ $URL_LOCAL == http://127.0.0.1:18700 ]]'

# abrir-puerto con una dirección local: toma la IP del equipo y actualiza la URL pública.
printf 'CIDIA_PERFIL=generico\nCIDIA_IP_PUBLICACION=127.0.0.1\nCIDIA_DIRECCION=127.0.0.1\nCIDIA_PUERTO=18800\nCIDIA_URL_PUBLICA=http://127.0.0.1:18800\n' >"$ENV_FILE"
printf 'CIDIA_URL_PUBLICA=http://127.0.0.1:18800\n' >"$DIR_DESP/perfiles/generico.env"
dc() { :; }
esperar_salud() { return 0; }
ip_principal() { printf 192.168.1.60; }
SI=1
orden_abrir_puerto >/dev/null
comprobar "publicado en 0.0.0.0" '[[ $(leer_var "$ENV_FILE" CIDIA_IP_PUBLICACION) == 0.0.0.0 ]]'
comprobar "dirección del equipo" '[[ $(leer_var "$ENV_FILE" CIDIA_DIRECCION) == 192.168.1.60 ]]'
comprobar "URL pública en cidia.env" '[[ $(leer_var "$ENV_FILE" CIDIA_URL_PUBLICA) == http://192.168.1.60:18800 ]]'
comprobar "URL pública en el perfil local" '[[ $(leer_var "$DIR_DESP/perfiles/generico.env" CIDIA_URL_PUBLICA) == http://192.168.1.60:18800 ]]'
comprobar "sin claves duplicadas" '[[ -z $(grep -oE "^[A-Z_]+=" "$ENV_FILE" | sort | uniq -d) ]]'
falla "IP de escucha no válida rechazada" orden_abrir_puerto 'no-es-una-ip'
orden_cerrar_puerto >/dev/null
comprobar "cerrar-puerto vuelve a 127.0.0.1" '[[ $(leer_var "$ENV_FILE" CIDIA_IP_PUBLICACION) == 127.0.0.1 ]]'

mkdir -p "$COPIAS/cidia-20261009-120000" "$COPIAS/cidia-20261010-020000" "$COPIAS/.cidia-20261010-030000.parcial" "$COPIAS/otra"
comprobar "solo copias completas y ordenadas" '[[ $(listar_copias | paste -sd " ") == "cidia-20261009-120000 cidia-20261010-020000" ]]'

CID=x
falla "modelo con caracteres raros rechazado" modelos_borrar 'a;rm -rf /'

comprobar "ayuda sin Docker" 'bash "$SCRIPT_PROBADO" --dir "$DIR" ayuda | grep -q admin-restablecer'
rc=0
bash "$SCRIPT_PROBADO" --dir "$DIR" inventada >/dev/null 2>&1 || rc=$?
comprobar "orden desconocida: código 2" '[[ $rc == 2 ]]'
terminar
