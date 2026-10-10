#!/usr/bin/env bash
# Herramienta cidia: modo demo (preparar, restaurar y reiniciar-datos) con Docker simulado.
# Las variables las leen las funciones cargadas del script; las condiciones de «comprobar» van
# entre comillas simples a propósito (se evalúan al llamar) y los simulacros se llaman desde ellas.
# shellcheck disable=SC2034,SC2016,SC2329,SC2153
set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh" "$1"

DIR=$BANCO/inst
detectar_dir
mkdir -p "$DIR_DESP/perfiles" "$DIR/secretos" "$DIR/datos"
cp "$BANCO/repo/servidor/despliegue/perfiles/msi.env" "$DIR_DESP/perfiles/"
printf 'CIDIA_PERFIL=msi\nCIDIA_IP_PUBLICACION=0.0.0.0\nCIDIA_DIRECCION=192.168.1.50\nCIDIA_PUERTO=18700\nOLLAMA_KEEP_ALIVE=30m\nCIDIA_PG_PASSWORD=abc\n' >"$ENV_FILE"

# Docker simulado: los servicios de EN_MARCHA tienen contenedor «cid-<servicio>»; Ollama tiene los
# modelos de MODELOS y los muestra cargados en EN_GPU; el gateway dice CIDIA_CREAR_SEMILLA=$SEMILLA.
# dc, curl y docker exec se anotan en LLAMADAS.
LLAMADAS=$BANCO/llamadas
EN_MARCHA="gateway postgres ollama asr weknora weknora-ui docreader qdrant redis espacio-trabajo"
MODELOS="ministral-3:8b qwen3-embedding:0.6b"
EN_GPU="100% GPU"
SEMILLA=false
docker() {
	local a m
	case $1 in
	ps)
		for a in "$@"; do
			if [[ $a == label=com.docker.compose.service=* ]]; then
				a=${a#label=com.docker.compose.service=}
				if [[ " $EN_MARCHA " == *" $a "* ]]; then echo "cid-$a"; fi
				return 0
			fi
		done
		echo cid-x
		;;
	exec)
		shift
		if [[ $1 == -i || $1 == -it ]]; then shift; fi
		echo "exec $*" >>"$LLAMADAS"
		case "$2 $3" in
		"ollama list")
			echo "NAME ID SIZE MODIFIED"
			for m in $MODELOS; do echo "$m abc 6.0 GB 2 days ago"; done
			;;
		"ollama ps")
			echo "NAME ID SIZE PROCESSOR CONTEXT UNTIL"
			for m in $MODELOS; do echo "$m abc 9.1 GB $EN_GPU 32768 Forever"; done
			;;
		"printenv CIDIA_CREAR_SEMILLA") echo "$SEMILLA" ;;
		"psql -U") echo 6 ;;
		"python -m")
			echo "Datos de demostración cargados:"
			echo "  personas: 15"
			echo "  contrasena_en: /datos/usuarios-demo.txt"
			;;
		esac
		;;
	*) return 0 ;;
	esac
}
curl() {
	echo "curl $*" >>"$LLAMADAS"
	if [[ $* == */health* ]]; then echo '{"estado":"ok","modelo":"small","cargado":true}'; fi
	return 0
}
dc() { echo "dc $*" >>"$LLAMADAS"; }
esperar_salud() { return 0; }
hay_gpu() { return 0; }
nvidia-smi() { echo "NVIDIA GeForce RTX 4080 Laptop GPU, 9500, 12282, 2, 48"; }
SI=1
var() { leer_var "$ENV_FILE" "$1"; }

echo "== Silencio en WAV para cargar la voz"
comprobar "44 B de cabecera y 1 s de audio" '[[ $(wav_silencio | wc -c) == 32044 ]]'
comprobar "cabecera RIFF/WAVE" '[[ $(wav_silencio | head -c 4) == RIFF && $(wav_silencio | head -c 16 | tail -c 8) == "WAVEfmt " ]]'

echo "== demo preparar"
: >"$LLAMADAS"
rc=0
salida=$(demo_preparar 2>&1) || rc=$?
comprobar "termina bien" '[[ $rc == 0 ]]'
comprobar "listo para la demo" 'grep -q "Listo para la demo" <<<"$salida"'
comprobar "dirección para los portátiles" 'grep -q "http://192.168.1.50:18700" <<<"$salida"'
comprobar "modelos sin caducidad" '[[ $(var OLLAMA_KEEP_ALIVE) == -1 && $(var ASR_LIBERAR_TRAS_S) == 0 && $(var CIDIA_MODO_DEMO) == activo ]]'
comprobar "guarda los valores anteriores" '[[ $(var CIDIA_DEMO_PREVIO_OLLAMA_KEEP_ALIVE) == 30m && $(var CIDIA_DEMO_PREVIO_ASR_LIBERAR_TRAS_S) == ninguno ]]'
comprobar "para WeKnora y el espacio de trabajo" 'grep -qx "dc stop weknora weknora-ui docreader qdrant redis espacio-trabajo" "$LLAMADAS"'
comprobar "aplica solo a los servicios de la demo" 'grep -qx "dc up -d postgres gateway ollama asr" "$LLAMADAS"'
comprobar "chat mínimo con keep_alive -1" 'grep "/api/chat" "$LLAMADAS" | grep -q "\"model\":\"ministral-3:8b\".*\"keep_alive\":-1"'
comprobar "embeddings con keep_alive -1" 'grep "/api/embed" "$LLAMADAS" | grep -q "\"model\":\"qwen3-embedding:0.6b\".*\"keep_alive\":-1"'
comprobar "sin fijar el contexto" '! grep -q num_ctx "$LLAMADAS"'
comprobar "prueba la transcripción" 'grep -q "/v1/audio/transcriptions" "$LLAMADAS"'
comprobar "los dos modelos en la GPU" '[[ $(grep -c "en memoria: 100 % en la GPU" <<<"$salida") == 2 ]]'
comprobar "dice dónde está la contraseña sin mostrarla" 'grep -q "datos/usuarios-demo.txt" <<<"$salida"'

echo "== demo preparar otra vez, con WeKnora y espacio"
: >"$LLAMADAS"
demo_preparar --con-weknora --con-espacio >/dev/null 2>&1
comprobar "no para nada" '! grep -q "dc stop" "$LLAMADAS"'
comprobar "conserva el valor original guardado" '[[ $(var CIDIA_DEMO_PREVIO_OLLAMA_KEEP_ALIVE) == 30m ]]'
comprobar "sin claves duplicadas" '[[ -z $(grep -oE "^[A-Z_]+=" "$ENV_FILE" | sort | uniq -d) ]]'
falla "opción desconocida rechazada" demo_preparar --inventada

echo "== Problemas que se detectan"
EN_GPU="45%/55% CPU/GPU"
salida=$(demo_preparar 2>&1) || true
comprobar "aviso si el modelo no cabe en la GPU" 'grep -q "No cabe entero en la GPU" <<<"$salida"'
EN_GPU="100% GPU"
MODELOS="ministral-3:8b"
rc=0
salida=$(demo_preparar 2>&1) || rc=$?
comprobar "falta un modelo: no está listo" '[[ $rc == 1 ]] && grep -q "Falta qwen3-embedding:0.6b" <<<"$salida" && ! grep -q "Listo para la demo" <<<"$salida"'
MODELOS="ministral-3:8b qwen3-embedding:0.6b"

echo "== demo restaurar"
: >"$LLAMADAS"
demo_restaurar >/dev/null 2>&1
comprobar "vuelve la caducidad anterior" '[[ $(var OLLAMA_KEEP_ALIVE) == 30m ]]'
comprobar "quita lo que no estaba" '! tiene_var "$ENV_FILE" ASR_LIBERAR_TRAS_S'
comprobar "sin marcas de la demo" '! grep -q "^CIDIA_DEMO_PREVIO_\|^CIDIA_MODO_DEMO" "$ENV_FILE"'
comprobar "arranca todo de nuevo" 'grep -qx "dc up -d" "$LLAMADAS"'
cp "$ENV_FILE" "$BANCO/antes"
demo_restaurar >/dev/null 2>&1
comprobar "restaurar dos veces no cambia nada" 'cmp -s "$ENV_FILE" "$BANCO/antes"'
quitar_var "$ENV_FILE" OLLAMA_KEEP_ALIVE
demo_preparar >/dev/null 2>&1
demo_restaurar >/dev/null 2>&1
comprobar "sin OLLAMA_KEEP_ALIVE antes, tampoco después" '! tiene_var "$ENV_FILE" OLLAMA_KEEP_ALIVE'
comprobar "el resto del fichero se conserva" '[[ $(var CIDIA_PG_PASSWORD) == abc && $(var CIDIA_DIRECCION) == 192.168.1.50 ]]'

echo "== demo reiniciar-datos"
: >"$LLAMADAS"
falla "se niega en un servidor que no es de demostración" demo_reiniciar_datos
SEMILLA=true
SI=0
INTERACTIVO=0
falla "sin terminal ni --si pide confirmación" demo_reiniciar_datos
comprobar "y no ha tocado la base" '! grep -q "cidia.semilla" "$LLAMADAS"'
SI=1
SEMILLA=True
salida=$(demo_reiniciar_datos 2>&1)
comprobar "siembra con --forzar en el gateway" 'grep -qx "exec cid-gateway python -m cidia.semilla --forzar" "$LLAMADAS"'
comprobar "ruta de la contraseña en el equipo" 'grep -q "contrasena_en: $DIR/datos/usuarios-demo.txt" <<<"$salida"'
comprobar "termina con éxito" 'grep -q "sembrados de nuevo" <<<"$salida"'

echo "== Órdenes"
comprobar "la ayuda incluye el modo demo" 'bash "$SCRIPT_PROBADO" --dir "$DIR" ayuda | grep -q "demo reiniciar-datos"'
falla "suborden desconocida rechazada" orden_demo inventada
terminar
