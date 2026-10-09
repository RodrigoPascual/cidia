#!/usr/bin/env bash
# Instalador: carpetas protegidas, ruta canónica, subredes y URLs sin credenciales.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

for d in / /home /home/ubuntu /opt /var/lib /usr /etc; do comprobar "protegida $d" "carpeta_protegida $d"; done
for d in /opt/cidia /home/ubuntu/CidIA /srv/cidia; do comprobar "permitida $d" "! carpeta_protegida $d"; done

# La ruta se normaliza: «/opt/cidia/..» es /opt y no sirve para instalar ni para desinstalar.
DIR=/opt/cidia/.. CIDIA_DIR=""
detectar_dir
comprobar "--dir /opt/cidia/.. queda en /opt" '[[ $DIR == /opt ]]'
comprobar "y /opt está protegida" 'carpeta_protegida "$DIR"'
DIR=/srv/cidia/
detectar_dir
comprobar "sin barra final" '[[ $DIR == /srv/cidia && $ENV_FILE == /srv/cidia/secretos/cidia.env ]]'
# Instalar en una carpeta protegida se rechaza antes de tocar nada.
comprobar_equipo() { exit 99; } # no debe llegar a comprobar el equipo
for d in /home/ubuntu /; do
	DIR=$d MODO=instalar
	fijar_rutas
	rc=0
	salida=$( (modo_instalar) 2>&1) || rc=$?
	comprobar "no instala en $d" '[[ $rc == 1 && $salida == *"No se puede instalar directamente en"* ]]'
done

comprobar "172.29.10.0/24 solapa con 172.29.0.0/16" 'solapan 172.29.0.0/16 172.29.10.0/24'
comprobar "172.29.10.0/24 no solapa con 172.17.0.0/16" '! solapan 172.17.0.0/16 172.29.10.0/24'
comprobar "host suelto dentro de la red" 'solapan 172.29.11.7 172.29.11.0/24'
comprobar "10.0.0.0/8 solapa con 10.229.10.0/24" 'solapan 10.0.0.0/8 10.229.10.0/24'
comprobar "192.168.1.0/24 no solapa con 192.168.229.0/24" '! solapan 192.168.1.0/24 192.168.229.0/24'

comprobar "token fuera de la URL" '[[ $(url_sin_credenciales https://ana:ghp_secreto@github.com/empresa/cidia.git) == https://github.com/empresa/cidia.git ]]'
comprobar "token fuera de los argumentos" '[[ $(url_sin_credenciales "--repo https://x:tok@h/r.git --si") != *tok* ]]'
comprobar "también desde la entrada estándar" '[[ $(echo "fatal: https://u:p@h/r" | url_sin_credenciales) == "fatal: https://h/r" ]]'
comprobar "URL sin credenciales intacta" '[[ $(url_sin_credenciales https://github.com/a/b) == https://github.com/a/b ]]'
terminar
