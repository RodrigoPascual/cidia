# Despliegue del servidor CidIA

Todo lo que hace falta para convertir un equipo con Ubuntu en el servidor de CidIA: el portátil MSI con GPU de la demo, el servidor de pruebas ARM de Oracle o cualquier PC o servidor de una empresa. El manual paso a paso, pensado para quien prepara el equipo, está en [`docs/manual-servidor.md`](../../docs/manual-servidor.md). Este fichero es la referencia técnica.

## Qué hay en esta carpeta

| Fichero | Para qué sirve |
|---|---|
| `instalar-servidor.sh` | Instalador idempotente: comprueba el equipo, instala Docker Engine (y el soporte de GPU), prepara carpetas y secretos, construye, arranca, descarga modelos y crea la cuenta de administración. |
| `cidia` | Herramienta de administración diaria (`sudo cidia estado`, `copia`, `actualizar`…). El instalador la enlaza en `/usr/local/bin/cidia`. |
| `docker-compose.yml` | Servicios: gateway, postgres (pgvector), ollama y asr; perfiles opcionales `weknora` y `espacio`. |
| `compose.gpu.yml` | Añade la GPU NVIDIA a Ollama. El instalador lo usa si hay GPU con controlador. |
| `compose.debug.yml` | Puertos extra para depurar desde el PC por túnel SSH (siempre en 127.0.0.1). |
| `perfiles/msi.env`, `perfiles/oracle.env` | Ajustes no secretos de cada equipo (modelos, motor de conocimiento, semilla…). |
| `perfiles/plantilla.env` | Plantilla del perfil genérico. El instalador la copia como `perfiles/generico.env` (local, fuera de git). |
| `perfiles/weknora.env` | Ajustes no secretos de WeKnora. No es un perfil de equipo. |
| `modelos/*.Modelfile` | Modelos derivados que no se descargan, sino que crea `cidia modelos descargar` con `ollama create` (ver «Modelo de búsqueda con contexto propio»). |
| `postgres/initdb/` | Crea la base y el rol de WeKnora en el primer arranque. |

## Instalación rápida

```bash
# con el repositorio ya copiado o clonado en el equipo
cd cidia/servidor/despliegue
bash instalar-servidor.sh --comprobar          # no cambia nada: dice qué haría
sudo bash instalar-servidor.sh                 # instalación guiada
```

Ejemplos sin preguntas:

```bash
# MSI con GPU, publicado en la red local con IP fija
sudo bash instalar-servidor.sh --perfil msi --ip 192.168.1.50 --lan --si

# PC de una pyme sin GPU, en otra carpeta y otro puerto
sudo bash instalar-servidor.sh --perfil generico --dir /srv/cidia --puerto 18800 --ip cidia.empresa.local --lan --si

# Clonar desde el repositorio privado en lugar de copiar esta carpeta
sudo bash instalar-servidor.sh --repo https://github.com/ORGANIZACION/cidia.git --rama main
```

### Opciones

| Opción | Efecto |
|---|---|
| `--perfil msi\|generico\|oracle\|<nombre>` | Perfil de modelos. Sin la opción: el de la instalación existente o, si es nueva, `msi` con GPU NVIDIA, `oracle` en ARM y `generico` en el resto (se pregunta). |
| `--dir CARPETA` | Carpeta de la instalación. Por defecto `/opt/cidia` (o la de la instalación que ya esté en marcha). Se rechazan `/`, las carpetas del sistema y `/home/<usuario>` a secas: hace falta una carpeta propia. |
| `--ip DIRECCION` | IP o nombre con el que los portátiles llegan al servidor. Se pregunta proponiendo la IP principal. |
| `--puerto N` | Puerto del gateway (por defecto 18700). |
| `--lan` / `--solo-local` | Publicar en la red local (`CIDIA_IP_PUBLICACION=0.0.0.0`) o solo en 127.0.0.1. Sin opción se pregunta con un aviso de seguridad. |
| `--con-weknora` / `--con-espacio` | Activa los perfiles de compose `weknora` (motor de conocimiento opcional) y `espacio` (consola aislada del agente; también construye `cidia-sandbox:local`). |
| `--sin-modelos` | No descarga los modelos ahora (`sudo cidia modelos descargar` más tarde). |
| `--sin-gpu` | Ignora la GPU aunque exista. |
| `--sin-ajustes-energia` | No ofrece desactivar la suspensión (solo se ofrece en portátiles y Ubuntu de escritorio). |
| `--repo URL [--rama R]` | Clona el código con git en `<dir>/cidia` (o hace `git pull` si ya es un clon). Los perfiles se comprueban en el clon. Si la URL lleva usuario y token, no salen en pantalla ni en el registro, pero git los guarda en `<dir>/cidia/.git/config`: mejor un token de solo lectura o un *credential helper*. |
| `--si` | Acepta lo propuesto sin preguntar. |
| `--comprobar` | Solo comprobaciones. No necesita root ni escribe nada en la instalación (el registro va a `/tmp`). Sale con código 1 si hay problemas que impiden instalar. |
| `--desinstalar` | Para y borra de verdad todo lo de CidIA (pide escribir `BORRAR`; con `--si` no pregunta). Ofrece conservar `copias/`. |

### Qué hace, paso a paso

1. **Comprobaciones**: Ubuntu 22.04/24.04 (avisa en otras versiones), amd64/arm64, núcleos, RAM (mínimo 8 GB), disco libre en la carpeta y en `/var/lib/docker` (mínimo 25 GB, recomendados 50), GPU NVIDIA por PCI y `nvidia-smi`, cgroups v2, origen y versión de Docker (recomienda 28 o superior si se publica en la LAN), conexión con los registros y la suspensión del equipo.
2. **Opciones**: perfil, dirección, puerto, publicación en la LAN y ajustes de energía. Si hay GPU sin controlador explica cómo instalarlo (`sudo ubuntu-drivers install` y reiniciar) y pregunta si seguir sin GPU. Busca puertos internos libres (18720/18721) y subredes de Docker que no choquen con la red de la empresa.
3. **Docker Engine** desde `download.docker.com` (nunca `docker.io` ni Docker Desktop) si falta; si ya hay un Docker funcionando no lo toca. Con GPU, **NVIDIA Container Toolkit** desde `nvidia.github.io`, `nvidia-ctk runtime configure` y reinicio de Docker (pregunta antes si hay contenedores de otros proyectos).
4. **Carpetas y código**: `<dir>/{cidia,datos,secretos,registros,copias}`; `secretos/` y `copias/` con permisos 700; `datos/` del uid 1000 (el de los contenedores). Copia el repositorio sin `node_modules`, `.venv`, `.env`, `datos` ni `secretos` (o lo clona con `--repo`) y enlaza `/usr/local/bin/cidia`.
5. **Configuración y secretos** en `secretos/cidia.env` (600): los secretos se generan con `openssl rand` sin mostrarse y nunca se regeneran; si hay una base de datos anterior sin sus secretos, se detiene. Con el perfil genérico crea `perfiles/generico.env` desde la plantilla.
6. **Imágenes**: `docker compose config`, `pull --ignore-buildable` y `build` (gateway con la interfaz web y ffmpeg LGPL, voz y, con `--con-espacio`, la caja de arena).
7. **Arranque**: `docker compose up -d` y espera a que `/salud` responda (hasta 5 minutos). Con GPU comprueba que Ollama detecta CUDA.
8. **Modelos** del perfil con barra de progreso (`cidia modelos descargar`): `ministral-3:8b` y `qwen3-embedding:0.6b` en el MSI; `qwen3:0.6b`, `qwen3.5:0.8b` y `qwen3-embedding:0.6b` en ARM. Después crea `qwen3-embedding-cidia:0.6b`, el modelo de búsqueda con contexto propio, sin volver a descargar nada.
9. **Cuenta de administración**: si no hay ninguna, crea `admin` con una contraseña aleatoria (se pasa al gateway por la entrada estándar, nunca como argumento) y la guarda en `secretos/admin-inicial.txt` (600).
10. **Resumen**: dirección para el instalador de los portátiles, URL del navegador (`http://<ip>:<puerto>/app/`), usuario y contraseña (solo esta vez) y siguientes pasos.

Volver a ejecutarlo es seguro: conserva secretos, datos, modelos y la cuenta de administración, y solo añade lo que falte.

## En el servidor

```
/opt/cidia/
├── cidia/                      código (copia o clon del repositorio)
│   └── servidor/despliegue/    compose, perfiles, instalar-servidor.sh y cidia
├── datos/                      documentos, imágenes, clips y espacio de trabajo (uid 1000)
├── secretos/                   700 · cidia.env (600) y admin-inicial.txt (600)
├── registros/                  instalacion-*.log del instalador
└── copias/                     700 · copias de seguridad cidia-AAAAMMDD-HHMMSS/
```

PostgreSQL, los modelos de Ollama y los de voz viven en volúmenes de Docker con el prefijo del proyecto (`cidia_pg-datos`, `cidia_ollama-modelos`, `cidia_asr-modelos`).

### `secretos/cidia.env`

Lo usan `docker compose --env-file` y la orden `cidia`. Tiene tres bloques:

| Bloque | Variables |
|---|---|
| Instalación | `CIDIA_PERFIL`, `CIDIA_DATOS`, `CIDIA_DIRECCION`, `CIDIA_PUERTO`, `CIDIA_IP_PUBLICACION`, `CIDIA_URL_PUBLICA`, `CIDIA_COMPOSE_FICHEROS` (`gpu`, `debug`), `CIDIA_COMPOSE_PERFILES` (`weknora`, `espacio`), `CIDIA_DOCKER_GID` (grupo del socket de Docker, para el espacio de trabajo) y, si hizo falta, `CIDIA_PUERTO_OLLAMA`, `CIDIA_PUERTO_ASR`, `CIDIA_RED_BORDE`, `CIDIA_RED_INTERNA`. |
| Recursos | `OLLAMA_CONTEXT_LENGTH` (32768 en el MSI), `OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_KEEP_ALIVE`, `CIDIA_MEM_*` y `CIDIA_CPU_*` calculados según la RAM y los núcleos, `ASR_MODELO` (`small` o `base`) y `ASR_HILOS`. Se pueden ajustar a mano; se aplican con `sudo cidia arrancar`. `ASR_LIBERAR_TRAS_S` (segundos sin uso tras los que la voz libera su modelo; 600 por defecto, 0 nunca) solo lo pone el modo demo. |
| Modo demo | Solo mientras está activo: `CIDIA_MODO_DEMO=activo` y `CIDIA_DEMO_PREVIO_*` (valores anteriores que devuelve `cidia demo restaurar`). |
| Secretos | `CIDIA_PG_PASSWORD`, `CIDIA_SECRETO_JWT`, `CIDIA_ESPACIO_SECRETO`, `CIDIA_REDIS_PASSWORD`, `WEKNORA_DB_PASSWORD`, `WEKNORA_JWT_SECRET` y `WEKNORA_AES_KEY` (32 caracteres exactos, `openssl rand -hex 16`). |

Para trabajar con compose a mano:

```bash
cd /opt/cidia/cidia/servidor/despliegue
DC="docker compose --env-file /opt/cidia/secretos/cidia.env -f docker-compose.yml -f compose.gpu.yml"
sudo $DC ps
```

## Herramienta `cidia`

| Orden | Qué hace |
|---|---|
| `estado` | Configuración, servicios, salud de gateway, Ollama, voz y base de datos, uso de CPU y memoria, disco, GPU, modelos (los que faltan) y última copia. |
| `registros [servicio] [-f] [-n N]` | Registros de un servicio o de todos. |
| `reiniciar [servicio]` · `parar` · `arrancar` | Ciclo de vida (los datos se conservan). `arrancar` crea o pone al día los modelos derivados cuyo modelo base ya está descargado. |
| `actualizar [--sin-copia]` | `git pull --ff-only`, copia previa, `pull`, `build --pull`, `up -d`, comprobación de salud y modelos derivados al día. Sin git, reconstruye con el código actual. |
| `modelos [listar]` · `modelos descargar [modelo…]` · `modelos borrar <modelo> [--forzar]` | Modelos del perfil, los locales permitidos en la app y los modelos base de los derivados; `descargar` baja los del registro y crea los derivados; no deja borrar uno en uso sin `--forzar`. |
| `copia [--conservar N]` · `copias` | `pg_dump` (formato propio) de `cidia` y, si existe, `weknora`; `tar` de `datos/`; secretos y perfil local; `info.txt` y `SHA256SUMS`. |
| `restaurar <copia> [--sin-copia]` | Verifica las sumas, pide escribir `RESTAURAR`, hace una copia del estado actual, restaura en una base temporal y solo si sale bien sustituye la actual; `datos/` anterior queda en `datos.previo-FECHA`. |
| `admin-restablecer [usuario]` | Nueva contraseña aleatoria para la cuenta de administración (la crea si no hay ninguna), cierra sus sesiones y lo anota en la auditoría. |
| `abrir-puerto [IP]` · `cerrar-puerto` | Publica el gateway en la LAN (0.0.0.0 o una IP del equipo) o lo deja solo en 127.0.0.1. Al publicar, actualiza también `CIDIA_DIRECCION` y `CIDIA_URL_PUBLICA`. |
| `demo preparar [--con-weknora] [--con-espacio]` | Modo demo (ver abajo): modelos cargados sin caducidad, voz lista, servicios opcionales parados, memoria y GPU, y la dirección para los portátiles. Sale con código 1 si algo no está listo. |
| `demo restaurar` | Devuelve los valores guardados, `up -d` de todo (vuelven los servicios opcionales) y comprobación de salud. |
| `demo reiniciar-datos` | `python -m cidia.semilla --forzar` en el gateway. Solo si el gateway tiene `CIDIA_CREAR_SEMILLA=true`; pide escribir `REINICIAR` (con `--si` no pregunta). |

Busca la instalación en `--dir`, `CIDIA_DIR`, la carpeta en la que vive el propio script o el proyecto `cidia` en marcha. Si no puede leer los secretos o hablar con Docker, se vuelve a ejecutar con `sudo`.

### Modo demo

Pensado para el MSI con 12 GB de VRAM; la demostración completa está en [`docs/guia-demo.md`](../../docs/guia-demo.md). `cidia demo preparar`:

1. Para los servicios opcionales en marcha que la demo no usa: WeKnora (`weknora`, `weknora-ui`, `docreader`, `qdrant`, `redis`; se queda si es el motor de conocimiento del perfil o con `--con-weknora`) y `espacio-trabajo` (salvo `--con-espacio`).
2. Pone en `cidia.env` `OLLAMA_KEEP_ALIVE=-1` (los modelos no caducan) y `ASR_LIBERAR_TRAS_S=0` (la voz no libera su modelo), guardando antes los valores anteriores como `CIDIA_DEMO_PREVIO_<variable>` (`ninguno` si no estaban), y marca `CIDIA_MODO_DEMO=activo`. Aplica con `up -d postgres gateway ollama asr`, que recrea Ollama y la voz.
3. Crea el modelo de búsqueda derivado si falta y ya está su base. Precarga los modelos de chat y embeddings del perfil con una petición mínima a Ollama (`/api/chat` con `num_predict: 1` y `/api/embed`, ambos con `keep_alive: -1` y sin `num_ctx`, para que la primera pregunta no los vuelva a cargar con otro contexto) y comprueba con `ollama ps` que siguen en memoria y si van «100% GPU». Si no caben enteros en la GPU, avisa y propone bajar `OLLAMA_CONTEXT_LENGTH`.
4. Envía a la voz un segundo de silencio en WAV: carga el modelo (y, la primera vez, lo descarga).
5. Comprueba que existen las cuentas del guion (`ana`, `luis`, `carmen`, `marta`, `javier`, `lucia`) y dice dónde está su contraseña, sin mostrarla.
6. Muestra la corriente (en portátiles), si la suspensión está desactivada, el uso de memoria de los contenedores y del equipo, la GPU y la dirección para los portátiles.

`cidia estado` avisa mientras el modo demo está activo. `cidia demo restaurar` devuelve los valores guardados (o quita las variables que no estaban), quita las marcas y hace `up -d`: Ollama y la voz se recrean con la caducidad normal y vuelven los servicios opcionales. Para marcar un servidor como de demostración, `CIDIA_CREAR_SEMILLA=true` en su perfil (el de `oracle` ya lo trae; en el MSI hay que cambiarlo en `perfiles/msi.env` de la instalación).

## Perfiles

| Perfil | Equipo | Modelos |
|---|---|---|
| `msi` | GPU NVIDIA de 12-16 GB, 32 GB de RAM | `ministral-3:8b` (chat y visión) y `qwen3-embedding-cidia:0.6b`; voz `small`; contexto 32K |
| `generico` | Cualquier PC o servidor sin GPU | Con 16 GB o más: `ministral-3:3b` y `qwen3-embedding-cidia:0.6b`. Con menos: `qwen3:1.7b`, `qwen3.5:0.8b` y `qwen3-embedding-cidia:0.6b` |
| `oracle` | Pruebas en ARM sin GPU | `qwen3:0.6b`, `qwen3.5:0.8b` y `qwen3-embedding-cidia:0.6b`; carga datos de demostración |

Para un perfil a medida (por ejemplo, un servidor con una GPU de 48 GB): `cp perfiles/plantilla.env perfiles/mi-planta.env`, cambiar los modelos y `sudo bash instalar-servidor.sh --perfil mi-planta`. Los embeddings son los mismos en todos los perfiles, así que no hay que reindexar al cambiar de equipo.

### Modelo de búsqueda con contexto propio

Ollama carga cada modelo con el contexto de `OLLAMA_CONTEXT_LENGTH`, también el de embeddings, y le reserva memoria para todo ese contexto: en Oracle, con 8192 y caché KV en f16, `qwen3-embedding:0.6b` ocupaba 2,9 GB en `ollama ps` y el derivado ocupa 2,4 GB (la caché KV baja de 896 a 448 MiB; los búferes de cálculo, unos 1,2 GiB, dependen del lote y no del contexto). Con los 32768 del MSI la diferencia es de alrededor de 1,5 GiB. Los trozos que indexa CidIA rondan los 300 tokens y el gateway corta cada texto a 6.000 caracteres, así que los perfiles usan `qwen3-embedding-cidia:0.6b`: el mismo modelo con `PARAMETER num_ctx 4096` ([`modelos/qwen3-embedding-cidia_0.6b.Modelfile`](modelos/qwen3-embedding-cidia_0.6b.Modelfile)). Cifras medidas y motivo en [`docs/manual-servidor.md`](../../docs/manual-servidor.md) §8.2.

* **Sin reindexar.** Los pesos son los mismos, así que los vectores son iguales; el gateway no guarda con ellos el nombre del modelo, y al arrancar la fila de búsqueda del panel de Modelos pasa al nombre nuevo (`sincronizar_modelo_busqueda` en `cidia/arranque.py`).
* **Cómo se crea.** `modelos/<nombre>_<etiqueta>.Modelfile` define un derivado. `cidia modelos descargar` (y con ella el instalador) descarga la base de la línea `FROM` y crea el derivado con `docker exec -i <ollama> ollama create <modelo> -f /dev/stdin`. `cidia arrancar`, `actualizar` y `demo preparar` lo crean o lo rehacen si falta o si sus `PARAMETER` no coinciden, siempre que la base ya esté descargada (sin red). Es idempotente.
* **El nombre tiene que contener `qwen3-embedding`**: `ia/llm.py` lo usa para poner la instrucción de consulta delante de las preguntas.
* **La base se queda.** `cidia modelos` la marca como «base de un modelo derivado» y `modelos borrar` no la borra sin `--forzar`.
* **Con WeKnora** (motor opcional), la base de conocimiento conserva el modelo con el que se dio de alta; funciona igual, pero WeKnora seguiría pidiendo el modelo base con el contexto global.

## Acceso desde fuera de la red de la empresa

CidIA se publica solo en la red local (`--lan`). Para una demostración a distancia, sin abrir puertos en el router, se puede publicar el puerto 18700 con un túnel saliente de dirección fija (por ejemplo, un túnel con nombre de Cloudflare sobre un dominio propio). Antes de abrirlo: solo datos de demostración, contraseña de administración cambiada, cuentas de demo para los visitantes y el túnel apagado al terminar. En producción, lo recomendable es la VPN de la empresa.

## Garantías

* Solo toca el proyecto de compose `cidia`: contenedores, volúmenes y redes se filtran por la etiqueta `com.docker.compose.project=cidia`. Nunca usa `docker system prune` ni borra imágenes de terceros.
* Los secretos no se imprimen ni se escriben en los registros. La contraseña de administración solo aparece en pantalla al final y en `secretos/admin-inicial.txt`.
* Ollama, la voz y PostgreSQL solo escuchan en 127.0.0.1; a la LAN solo se publica el gateway.
* `--desinstalar` borra únicamente lo que crea la instalación (`cidia/`, `datos/`, `secretos/`, `registros/`, `copias/`, volúmenes, redes e imágenes `cidia-*:local`) y se niega a actuar sobre carpetas del sistema.

## Pruebas

* `shellcheck -x -S style` (0.11.0, imagen `koalaman/shellcheck:stable`) sobre los dos scripts: sin avisos. Tras añadir el modo demo se repitió en Oracle sobre `cidia` y los bancos `comun.sh` y `demo_herramienta.sh`: sin avisos.
* `servidor/gateway/tests/test_instalador_servidor.py`: extrae del script `cidia` el programa que crea o restablece la cuenta de administración y lo ejecuta contra la base de pruebas (alta, no tocar una cuenta existente, restablecer y cerrar sesiones, auditoría, entrar con la clave nueva, rechazar cuentas que no son de administración, inexistentes o claves cortas).

  El mismo fichero ejecuta con bash (en Windows, el de Git) los bancos de `servidor/gateway/tests/bancos_instalador/`, que cargan las funciones de los dos scripts con Docker simulado: carpetas protegidas y rutas canónicas, subredes, URLs sin credenciales, `cidia.env` (secretos de la longitud correcta, nunca vacíos ni regenerados, idempotencia, recursos por perfil, `CIDIA_DOCKER_GID`), la copia del código sin `.env`, `datos/`, `node_modules` ni claves y conservando los perfiles locales, `abrir-puerto`/`cerrar-puerto`, la copia de seguridad con rotación y la restauración (incluida una copia dañada), y el modo demo (`demo_herramienta.sh`: servicios que se paran, peticiones de precarga con `keep_alive: -1` y sin `num_ctx`, aviso si un modelo no cabe en la GPU o falta, valores guardados y devueltos sin tocar el resto de `cidia.env`, y `reiniciar-datos` que se niega sin `CIDIA_CREAR_SEMILLA=true` o sin confirmación).

  ```bash
  cd servidor/gateway && CIDIA_TEST_BD=instalador_servidor .venv/Scripts/python -m pytest tests/test_instalador_servidor.py -q
  ```
* En el servidor Oracle, contra la instalación que ya funcionaba en `/home/ubuntu/CidIA`: `instalar-servidor.sh --comprobar` (con `--dir` y con detección automática) y `cidia estado` (con `--dir`, con `CIDIA_DIR` y sin nada). La instantánea del servidor antes y después es idéntica. Detalle en el manual, sección «Cómo se probó».
