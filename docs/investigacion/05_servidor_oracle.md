# 05. Servidor de pruebas Oracle: inspección y propuesta de despliegue

Fecha de la inspección: 9 de octubre de 2026 (16:24 UTC).
Equipo: `ubuntu@143.47.56.7` (Oracle Cloud, nivel gratuito).
Método: **solo lectura**. No se ha instalado, parado, arrancado ni cambiado nada. Las únicas órdenes de Docker fueron de consulta (`info`, `ps`, `stats --no-stream`, `inspect`, `network ls/inspect`, `system df`, `compose ls`) y una validación de sintaxis de compose leída por la entrada estándar, sin escribir ficheros (`docker compose -f - config`). Para leer el `ulimit -n` efectivo de los contenedores se ejecutó una sola vez `docker exec postiz-redis sh -c "ulimit -n"`, que no cambia nada. Para la prueba de reenvío SSH se abrió un canal a `127.0.0.1:18700`, un puerto libre, y no se conectó a ningún servicio.

> Convención: **[verificado]** significa comprobado en el servidor, en el código fuente o en el registro de imágenes. **[inferencia]** es una deducción todavía sin probar.

---

## 0. Resumen

* Servidor **ARM64 (Neoverse-N1, 4 núcleos, sin SMT)**, 23,4 GiB de RAM, **sin swap**, Ubuntu 20.04.6 y kernel 5.15 de Oracle. Tiene **cgroups v1** (modo híbrido) y Docker 26.1.3 con compose v2.35.1. El usuario `ubuntu` usa Docker sin `sudo`.
* Ya funcionan **12 contenedores**: 9 de 3 proyectos compose (postiz, robot-ai-lab y waha) y 3 sueltos (n8n, jellyfin y ats-cv-forge-app). Hay además 4 parados de postiz y servicios nativos (pm2, uvicorn :8000, rclone, cupsd). Todo lo de CidIA debe ir en el proyecto compose `cidia`, en redes y volúmenes propios y con puertos **solo en 127.0.0.1**.
* **Todas las imágenes que necesitamos tienen variante arm64** [verificado en los registros]: WeKnora app, ui y docreader v0.8.2; Qdrant; Ollama 0.40.2; pgvector pg17; Redis; speaches 0.8.3-cpu; python:3.12-slim. El servidor puede hacer las pruebas de la fase 2 con modelos pequeños.
* Bloque de puertos propuesto: **18700-18750** (libres en el servidor y en el PC). El PC accede por túnel `ssh -L`; el reenvío TCP está permitido [verificado].
* Presupuesto de memoria de CidIA: **≤ 6,5 GiB con el perfil `weknora`, ≤ 8 GiB con `voz`**. Así se respeta el peor caso de LocalAI, que tiene límite de 9 GiB y hoy usa 88 MiB.
* Riesgos principales:
  1. Ollama 0.40.2 **no lee los límites de cgroup v1**, así que dentro del contenedor cree que tiene 23 GiB. Con contexto 8192, los dos modelos Qwen3 0.6B juntos probablemente **no caben** en 2,5 GiB (sección 6.5, corregido en la verificación).
  2. El espacio de trabajo del agente necesita la API de Docker, que en un servidor compartido equivale a control total sobre los demás contenedores.
  3. `docker system prune` **borraría datos de otros proyectos**.
  4. La imagen por defecto de WeKnora usa ParadeDB, que es **AGPL-3.0**. Con `RETRIEVE_DRIVER=qdrant` basta PostgreSQL normal [verificado en código].

---

## 1. Sistema

| Elemento | Valor | Fuente |
|---|---|---|
| SO | Ubuntu 20.04.6 LTS (focal) | `/etc/os-release` |
| Kernel | `5.15.0-1081-oracle` aarch64 | `uname -a` |
| CPU | 4 × ARM Neoverse-N1 r3p1, 1 hilo por núcleo. Extensiones: `asimd asimddp atomics lrcpc dcpop` (**sin SVE, sin i8mm, sin bf16**) | `lscpu` |
| RAM | 23,43 GiB en total; 3,9 GiB usados; **19 GiB disponibles** | `free -h`, `/proc/meminfo` |
| Swap | **ninguna** | `free -h` |
| Disco `/` | ext4, 194 GB; 82 GB usados; **112 GB libres**; inodos al 7 % | `df -hT`, `df -i` |
| `/var/lib/docker` | en `/` (no hay disco aparte) | `docker info` |
| Otros montajes | `/home/ubuntu/pcloud-drive` (FUSE rclone, 2 TB, 93 % lleno): **no usar para CidIA** | `df -hT` |
| cgroups | **v1** (híbrido: controladores v1 en `/sys/fs/cgroup/*`, `cgroup2` solo en `/sys/fs/cgroup/unified`) | `mount \| grep cgroup` |
| Docker cgroup driver | `cgroupfs`, `Cgroup Version: 1` | `docker info` |
| Límites por contenedor | **Funcionan**: `robot-ai-lab-*` ya usan `mem_limit`, `cpus` y `pids_limit` y `docker stats` muestra los topes (256 MiB, 128 MiB, 9 GiB…) | `docker stats`, `docker inspect` |
| `ulimit -n` | 1024 en la shell de `ubuntu`; **1 048 576 en los contenedores** (heredado de `dockerd`) | `/proc/<dockerd>/limits` |
| sysctl | `vm.overcommit_memory=0`, `vm.max_map_count=65530`, `vm.swappiness=60`, `fs.inotify.max_user_instances=128`, `kernel.unprivileged_userns_clone=1`, `net.ipv4.ip_local_port_range=32768-60999` | `sysctl` |
| Presión de memoria | PSI a 0. **Ningún OOM-kill** en los registros del kernel de los últimos 30 días | `/proc/pressure/memory`, `journalctl -k` |
| Hora | UTC, sincronizada | `timedatectl` |
| AppArmor / seccomp | activos (perfil seccomp `builtin`) | `docker info`, `aa-status` |
| Runtimes | solo `runc` (no hay `runsc`/gVisor ni `crun`) | `docker info`, `which` |
| Carga | 0,02 / 0,07 / 0,07 (prácticamente en reposo) | `uptime` |

**Qué implica cgroups v1:**

* `mem_limit`, `cpus`, `cpu_shares` y `pids_limit` de compose funcionan, como demuestran los contenedores de `robot-ai-lab`.
* **Ollama 0.40.2 solo consulta los ficheros de cgroup v2** [verificado: `discover/cpu_linux.go:15-20` y `:64-74` del tag `v0.40.2`, que leen `/sys/fs/cgroup/memory.max` y `memory.current`]. Con v1 esos ficheros no existen y Ollama cae a `/proc/meminfo`, donde ve unos 23 GiB. Ollama tiene un rechazo propio («model is too large for system memory», `server/sched.go:642`), pero no salta porque cree tener 23 GiB. Si un modelo o contexto no cabe en el `mem_limit`, actúa el OOM-killer del cgroup. Lo normal es que mate el proceso que más memoria usa, que es el subproceso `llama-server` (lo lanza `exec.Command` en `llm/llama_server.go:426`), y no el contenedor entero: la petición falla con un error genérico y `ollama serve` sigue vivo [inferencia, corregido en la verificación: antes decía que el kernel mataba el contenedor]. Mitigación: fijar `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_NUM_PARALLEL=1` y `OLLAMA_MAX_LOADED_MODELS`, y bajar solo modelos pequeños (sección 6.5). En el MSI con Ubuntu 22.04/24.04 (cgroups v2) el problema desaparece [inferencia: es lo normal en esas versiones].
* Sin swap, si un contenedor llega a su `mem_limit` el OOM-killer actúa **dentro de ese contenedor**. Por eso es imprescindible poner límites a todo lo nuestro.
* Docker rootless (una alternativa para el espacio de trabajo) no aplica límites de recursos con cgroups v1 [verificado: según la guía de problemas de Docker rootless, con cgroup v1 se ignoran `--cpus`, `--memory` y `--pids-limit`, y los límites solo funcionan con cgroup v2 y systemd]. En este servidor no es opción.

**ARM y lo que significa para CidIA:**

* Sin GPU: todo el LLM corre en CPU NEON con `dotprod`. Velocidad prevista [inferencia, hay que medirla]: decenas de tokens por segundo con 0,6B en Q4 y unos pocos con 3B. Basta para validar flujos, no para medir rendimiento.
* El `ffmpeg` del sistema (4.2.7) está compilado con `--enable-gpl --enable-libx264` [verificado: `ffmpeg -buildconf`]. **No sirve para CidIA.** Para el gateway hay builds estáticas LGPL para arm64 y amd64 (BtbN/FFmpeg-Builds: `ffmpeg-n8.1-latest-linuxarm64-lgpl-8.1.tar.xz`, 116 MB) [verificado en la API de releases de GitHub]. Hay que descargar la variante de la arquitectura en el `Dockerfile` con `TARGETARCH`.
* Las ruedas Python del gateway tienen versión `aarch64` o `py3-none-any` [verificado en PyPI]: `mcp 2.3.0` (requiere Python ≥ 3.10), `fastapi 0.143.0`, `psycopg-binary 3.3.6`, `qdrant-client 1.19.1`, `faster-whisper 1.2.1`, `ctranslate2 4.8.2`, `scenedetect 0.7.1` y `opencv-python-headless 5.0.0.93`.
* **Licencias de esas ruedas (añadido en la verificación)** [verificado en PyPI y en el README de opencv-python]:
  * `psycopg` y `psycopg-binary` 3.3.6 son **LGPL-3.0-only**, y `servidor/gateway/pyproject.toml` ya usa `psycopg[binary]`. Esto choca con la regla «LGPL solo como programa externo». Hay que elegir: aceptarlo como biblioteca que se importa y se puede sustituir (es lo habitual, pero cambia la regla), o cambiar a `pg8000` 1.31.5 (BSD-3-Clause, Python puro, compatible con SQLAlchemy síncrono) o a `asyncpg` 0.32.0 (Apache-2.0, con rueda `cp312 manylinux_2_28_aarch64`, solo asíncrono).
  * Todas las ruedas de `opencv-python` y `opencv-python-headless` **llevan FFmpeg LGPL-2.1 dentro** (README de la rama 5.x, línea 203). Es otra biblioteca LGPL enlazada.
  * `scenedetect 0.7.1` depende de **`opencv-python`**, no de la variante *headless*. En Linux, esa variante incluye Qt 5 (LGPL-3.0) y necesita `libGL.so.1`, que `python:3.12-slim` no trae. Instalar `scenedetect` añade `opencv-python` aunque se pida `opencv-python-headless`. Alternativas: instalar `scenedetect --no-deps` más sus dependencias con la variante *headless*, o detectar cambios de escena con el ffmpeg LGPL externo (filtros `select='gt(scene,0.3)'` o `scdet`) [inferencia: no está probado con nuestros vídeos].
  * `faster-whisper 1.2.1` depende de `av` (PyAV, cuyas ruedas también llevan FFmpeg) y de `onnxruntime`. Si la voz va en el contenedor `asr` (speaches), el gateway no necesita instalarlo.

---

## 2. Docker

### 2.1 Motor

| Elemento | Valor |
|---|---|
| Engine | 26.1.3 (paquete `docker.io` de Ubuntu, `26.1.3-0ubuntu1~20.04.1`), API 1.45, linux/arm64 |
| containerd / runc | 1.7.24 / 1.1.12 |
| Compose / Buildx | v2.35.1 / v0.23.0 (plugins en `/usr/libexec/docker/cli-plugins`) |
| Almacenamiento | `overlay2` sobre extfs, `d_type` sí |
| Logs | `json-file` **sin rotación global**: no existe `/etc/docker/daemon.json`. Cada servicio nuestro debe fijar `max-size` y `max-file` |
| Live restore | desactivado: cualquier actualización o reinicio de `docker.io` reinicia todos los contenedores. **Matiz de la verificación:** `unattended-upgrades` casi seguro **no** lo actualizará. El `docker.io` instalado viene de `focal-updates`, que no está en `Allowed-Origins` (solo `focal`, `focal-security` y ESM), y la máquina no tiene Ubuntu Pro, así que ESM no está activo [verificado: `apt-cache policy docker.io`, `50unattended-upgrades`, `pro status`]. El riesgo real es un `apt upgrade` manual |
| Origen de los paquetes | `docker.io`, `containerd` y `runc` de Ubuntu; `docker-compose-plugin` y `docker-buildx-plugin` del repositorio `download.docker.com` (`/etc/apt/sources.list.d/docker.list`) [verificado: `dpkg -l`] |
| Registros inseguros | `127.0.0.0/8` |
| Swarm | inactivo |
| Docker sin sudo | **sí**: `ubuntu` pertenece al grupo `docker` (gid 120) y el socket es `srw-rw---- root:docker` [verificado] |
| Sesión en registros | ninguna (no hay credenciales en `~/.docker/config.json`) |
| Límite de Docker Hub | **100 descargas por hora** para la IP 143.47.56.7, sin consumir ninguna en la consulta [verificado: cabecera `ratelimit-limit: 100;w=3600`] |

### 2.2 Proyectos y contenedores existentes (no tocar)

| Proyecto compose | Contenedores (estado) | Puertos publicados |
|---|---|---|
| `postiz` (`/home/ubuntu/postiz/docker-compose.yml`) | postiz, caddy, postiz-redis y postiz-postgres en marcha; temporal, temporal-ui, temporal-postgresql y temporal-elasticsearch **parados** | caddy `0.0.0.0:80`, `0.0.0.0:443` |
| `robot-ai-lab` (`/home/ubuntu/robot-ai-lab/compose.yaml`) | orchestrator, gateway, localai (`localai/localai:v4.8.0`, **límites de 9 GiB y 3 CPU**) y search | `127.0.0.1:8090`, `127.0.0.1:8091`, `172.17.0.1:8092` |
| `waha` (`/home/ubuntu/waha/docker-compose.yaml`) | waha | `127.0.0.1:3000` |
| (sin compose) | n8n, jellyfin, ats-cv-forge-app | `0.0.0.0:5678`, `0.0.0.0:8096`, `0.0.0.0:4010` |

Consumo actual (`docker stats --no-stream`): waha 1,50 GiB · postiz 1,34 GiB · n8n 550 MiB · jellyfin 288 MiB · localai 89 MiB · el resto < 60 MiB cada uno. Fuera de Docker: chromium (~1 GiB entre procesos), varios `node` (pm2) y `uvicorn`.

**Redes Docker en uso:** `bridge` 172.17/16, `postiz_temporal-network` 172.18/16, `postiz_postiz-network` 172.19/16, `robot-ai-lab-egress` 172.20/16, `robot-ai-lab-internal` 172.21/16, `robot-ai-lab-edge` 172.22/16 y `waha-n8n` 172.23/16. En la tabla NAT quedan además reglas `MASQUERADE` antiguas de 172.30/16, 192.168.144/20 y 192.168.160/20, de redes ya borradas. La VCN de Oracle es 10.0.0.0/24 (`enp0s6` 10.0.0.173).
→ Para CidIA proponemos **172.29.10.0/24** (borde) y **172.29.11.0/24** (interna), libres [verificado con `ip route` y `docker network inspect`].

**Disco de Docker:** imágenes 24,2 GB, de los que 11 GB son recuperables; volúmenes 4,7 GB; caché de compilación 0,43 GB. **Lo recuperable es de otros proyectos** (contenedores de temporal parados y sus volúmenes): no se puede usar `docker system prune`, `docker image prune -a` ni `docker volume prune`.

**Antes de desplegar:** no hay ningún contenedor, red ni volumen con «cidia» en el nombre. `/home/ubuntu/CidIA` existe, vacío y propiedad de `ubuntu`.

---

## 3. Puertos y cortafuegos

### 3.1 Puertos en escucha (`ss -tlnp`)

| Dirección | Puerto | Proceso |
|---|---|---|
| 0.0.0.0 / [::] | 22 | sshd |
| 0.0.0.0 / [::] | 80, 443 | docker-proxy → caddy (postiz) |
| 0.0.0.0 | 111 | rpcbind |
| 0.0.0.0 / [::] | 631 | cupsd |
| 0.0.0.0 | 4001, 4002, 4005 | node (pm2) |
| 0.0.0.0 / [::] | 4010 | docker-proxy → ats-cv-forge-app |
| 0.0.0.0 / [::] | 5678 | docker-proxy → n8n |
| 0.0.0.0 | 8000 | uvicorn (nativo) |
| 0.0.0.0 / [::] | 8096 | docker-proxy → jellyfin |
| 127.0.0.1 | 3000 | waha |
| 127.0.0.1 | 8090, 8091 | robot-ai-lab |
| 172.17.0.1 | 8092 | robot-ai-lab-orchestrator |
| 127.0.0.1 | 38791 | containerd |
| 127.0.0.53 | 53 | systemd-resolved |

UDP: solo 53 (resolved), 68 (DHCP) y 111 (rpcbind). **Nada escucha en 18700-18799**, ni en el servidor ni en el PC de desarrollo [verificado con `ss` y `netstat -ano`]. Todo el bloque queda por debajo del rango efímero (32768-60999).

### 3.2 Cortafuegos

* `ufw`: **inactive**.
* `iptables` `INPUT`: política **ACCEPT**, con solo cinco reglas `ACCEPT` explícitas (5678, 4008, 443, 80, 5000) y ningún `REJECT` final. El cortafuegos del host, en la práctica, deja pasar todo; el filtro real es la *security list* de la VCN de Oracle, que no se ve desde dentro.
* `DOCKER-USER`: vacía (`-j RETURN`). `FORWARD`: política DROP con las cadenas estándar de Docker.
* Los puertos publicados por Docker **no pasan por `INPUT`** (van por `nat/PREROUTING` → `DOCKER` → `FORWARD`). Un `ports: "18700:8000"` sin IP quedaría abierto en todas las interfaces aunque hubiera reglas en `INPUT`. **Regla obligatoria: todo `ports:` de CidIA lleva `127.0.0.1:` delante.**
* `sshd -T`: `allowtcpforwarding yes`, `gatewayports no`, `permitopen any`. Se probó el reenvío con `ssh -W 127.0.0.1:18700` y la respuesta fue `connect failed: Connection refused` (puerto libre) y no `administratively prohibited`, así que **el túnel `-L` funciona** [verificado].

---

## 4. Conectividad saliente

`curl -sI --max-time 10` desde el servidor. Todo llega; los 401, 403, 404 y 405 son respuestas normales de una API de registro a un `HEAD` sin credenciales.

| Destino | HTTP | Tiempo |
|---|---|---|
| registry-1.docker.io/v2/ | 401 | 0,34 s |
| auth.docker.io/token | 405 | 0,12 s |
| production.cloudflare.docker.com (capas) | 403 | 0,09 s |
| ghcr.io/v2/ | 405 | 0,20 s |
| ollama.com | 200 | 0,11 s |
| registry.ollama.ai/v2/ | 404 | 0,29 s |
| pypi.org/simple/ | 200 | 0,01 s |
| files.pythonhosted.org | 404 | 0,19 s |
| github.com | 200 | 0,11 s |
| objects.githubusercontent.com | 404 | 0,06 s |
| huggingface.co | 200 | 0,04 s |
| quay.io/v2/ | 401 | 0,53 s |
| download.pytorch.org/whl/ | 200 | 0,11 s |

---

## 5. Software del host

| Herramienta | Estado | Comentario |
|---|---|---|
| python3 | 3.8.10 (`/usr/bin`), con `venv` | EOL. **No cumple** `mcp` ni `fastapi` (≥ 3.10) |
| python3.10 | 3.10.13 (`/usr/local/bin`, compilado a mano; OpenSSL 1.1.1f) | Funciona, pero no lo usaremos |
| miniconda | Python 3.13.12 en `/home/ubuntu/miniconda` (entorno `moss-tts-nano` del usuario) | **No tocar** |
| git | 2.25.1 | Suficiente para clonar |
| ffmpeg / ffprobe | 4.2.7 **GPL** (`--enable-gpl --enable-libx264`) | Solo para inspección manual; CidIA lleva su ffmpeg LGPL en la imagen |
| node / npm / pm2 | v20.20.2 / 10.8.2 / pm2 | Del usuario (pm2 sirve 4001-4005) |
| gcc, make, jq, tmux, screen, rclone, cloudflared | presentes | |
| uv, pipx, conda (en PATH), psql, redis-cli, sqlite3, ollama, nvidia-smi | **no** | Todo lo de CidIA irá en contenedores |
| glibc / OpenSSL | 2.31 / 1.1.1f | |

**Conclusión:** en el host **no se instala nada**. El gateway se construye con `python:3.12-slim-bookworm` (tiene arm64 y amd64) y los clientes de bases de datos se usan con `docker compose exec`.

---

## 6. Propuesta de despliegue

### 6.1 Estructura de directorios

```
/home/ubuntu/CidIA/
├── cidia/                         git clone del repositorio (el mismo que en el PC)
│   └── servidor/despliegue/
│       ├── docker-compose.yml     servicios (sección 6.4)
│       ├── compose.debug.yml      puertos extra de depuración, siempre en 127.0.0.1
│       ├── perfiles/oracle.env    parámetros NO secretos de este equipo (en git)
│       └── postgres/initdb/       crea la BD y el rol de WeKnora en el primer arranque
├── secretos/                      chmod 700, fuera de git
│   ├── cidia.env                  chmod 600: CIDIA_PG_PASSWORD, CIDIA_REDIS_PASSWORD, JWT…
│   └── weknora.env                chmod 600: DB_USER/DB_PASSWORD, JWT_SECRET, SYSTEM_AES_KEY…
├── datos/                         montajes con ruta conocida (fáciles de inspeccionar y copiar)
│   ├── ficheros/                  documentos subidos, imágenes y clips de pasos
│   ├── generador-de-contenido/    <usuario>/ (espacio de trabajo del agente)
│   └── captura/                   vídeos en proceso (temporal)
├── copias/                        pg_dump y snapshots de Qdrant
├── terceros/                      clones de consulta (WeKnora v0.8.2…), solo lectura
└── registros/                     salida de los scripts de instalación y de las pruebas
```

* Los motores (PostgreSQL, Qdrant, Redis, modelos de Ollama, caché de Hugging Face) van en **volúmenes con nombre**, que quedan con el prefijo del proyecto (`cidia_pg-datos`…). Así no hay problemas de UID/GID con los montajes de carpeta y `docker compose down -v` borra solo lo nuestro.
* Nada en `/home/ubuntu/pcloud-drive`, que es FUSE remoto y está al 93 %.
* Los secretos se generan en el servidor (`openssl rand -hex 32`), nunca se imprimen y nunca entran en git. **Excepción, corregida en la verificación:** `SYSTEM_AES_KEY` de WeKnora tiene que medir **exactamente 32 bytes**. Hay que generarla con `openssl rand -hex 16`, que da 32 caracteres. Con `-hex 32` saldrían 64 caracteres: WeKnora solo avisa en el registro y **desactiva el cifrado** de las credenciales que guarda en la BD [verificado: `internal/utils/crypto.go:19-25` devuelve `nil` si la longitud no es 32; `internal/runtime/startup.go:137-141` solo escribe un aviso].
* `secretos/weknora.env` debe llevar `DB_USER`, `DB_PASSWORD`, `JWT_SECRET` y `SYSTEM_AES_KEY`. En el borrador, `REDIS_PASSWORD` le llega a WeKnora interpolada desde `CIDIA_REDIS_PASSWORD` (sección 6.4). Sin ella, WeKnora no puede autenticarse en un Redis con `--requirepass` [verificado: lee `REDIS_PASSWORD` en `internal/container/container.go:764` y `internal/router/task.go:83`].

### 6.2 Aislamiento del proyecto

* `name: cidia` en la cabecera del compose. Contenedores `cidia-<servicio>-1`, volúmenes `cidia_*`, redes con nombre explícito `cidia-borde` y `cidia-interna`. **Sin `container_name`**: el compose de WeKnora fija nombres globales como `WeKnora-app` o `WeKnora-postgres` (`docker-compose.yml:14, 44, 414, 533, 554, 658` de WeKnora v0.8.2), y en el nuestro hay que quitarlos.
* Dos redes:
  * `cidia-interna` (`internal: true`, 172.29.11.0/24, sin salida a Internet): **todos** los servicios. Los que no publican puertos (postgres, redis, qdrant, docreader, weknora) **solo** están aquí.
  * `cidia-borde` (bridge normal, 172.29.10.0/24): solo los servicios que publican en 127.0.0.1 o necesitan descargar algo (gateway, weknora-ui, ollama para `pull`, asr para bajar modelos de Hugging Face).
  * Motivo: en Docker 26.1.3 un contenedor conectado **solo** a redes `internal` no tiene endpoint de pasarela, y los puertos se programan sobre ese endpoint. [Verificado en moby v26.1.3: `libnetwork/drivers/bridge/bridge_linux.go:1262-1263` solo asigna pasarela si `!network.config.Internal`; `libnetwork/default_gateway.go:177-187` elige el endpoint con pasarela.] [Verificación: además, `libnetwork/endpoint.go:609-611` solo llama a `ProgramExternalConnectivity` (lo que programa los puertos) si la red no es interna, y `default_gateway.go:125` hace que una red interna tampoco pida la pasarela por defecto `docker_gwbridge`.] Por eso `compose.debug.yml` añade `borde` a cada servicio que publica.
* **Seguridad de los puertos en 127.0.0.1 (añadido en la verificación).** Docker 26.1.3 no trae una corrección de Docker 28.0.0: un equipo vecino de la misma red L2 podía llegar a puertos publicados en una dirección de *loopback* (notas de versión de Docker 28, moby/moby#49325). En el servidor, la tabla `raw` de iptables está vacía, así que no tiene la regla que añade Docker 28 [verificado: `iptables -t raw -S`]. En OCI, los vecinos de la subred 10.0.0.0/24 son solo instancias de la propia cuenta, así que el riesgo es bajo [inferencia]. **En el MSI, conectado a la LAN de una empresa, conviene Docker Engine ≥ 28.**
* Siempre `restart: unless-stopped`, así que tras un reinicio del host todo vuelve a arrancar.
* Rotación de logs en cada servicio (ancla `x-log`), porque el daemon no la tiene.
* Limpieza **solo** con `docker compose --profile '*' down` (con `-v` para borrar datos) desde el directorio del proyecto. Para listar lo nuestro: `docker ps -a --filter label=com.docker.compose.project=cidia`.

### 6.3 Puertos (todos en 127.0.0.1)

| Puerto host | Servicio | Puerto interno | Perfil | Publicado |
|---|---|---|---|---|
| **18700** | gateway (`/api`, `/v1`, `/mcp`, `/app`) | 8000 | base | siempre |
| 18701 | weknora-ui (consola de la base de conocimiento) | 80 | `weknora` | siempre |
| 18702 | weknora API | 8080 | `weknora` | solo con `compose.debug.yml` |
| 18710 | postgres | 5432 | base | solo con `compose.debug.yml` |
| 18711 | redis | 6379 | `weknora` | solo con `compose.debug.yml` |
| 18712 | qdrant REST + `/dashboard` | 6333 | `weknora` | solo con `compose.debug.yml` |
| 18713 | qdrant gRPC | 6334 | `weknora` | solo con `compose.debug.yml` |
| 18720 | ollama | 11434 | base | siempre |
| 18721 | asr (speaches) | 8000 | `voz` | siempre |
| 18750 | docreader gRPC | 50051 | `weknora` | solo con `compose.debug.yml` |

Los mismos números valen en el MSI. Allí solo cambia cómo se expone el gateway a la LAN (proxy inverso con TLS), que no se hace en Oracle.

### 6.4 Compose propuesto (borrador validado)

Validado en el servidor con `docker compose -f - --profile weknora --profile voz config` (Compose v2.35.1). El borrador base y la fusión con `compose.debug.yml` resuelven sin errores, con los puertos en `host_ip: 127.0.0.1` y las redes y límites esperados [verificado]. Solo se ha comprobado la sintaxis; no se ha levantado ningún servicio.

> **Precisión de la verificación.** La variante que se validó usaba `env_file: [{ path: ..., required: false }]`. Con la forma corta del borrador (`env_file: [perfiles/oracle.env]`), `docker compose config` falla con «env file … not found» mientras el fichero no exista [verificado en el servidor]. Además, como `${CIDIA_PG_PASSWORD:?…}` y `${CIDIA_REDIS_PASSWORD:?…}` son obligatorias, **todas** las órdenes de compose del proyecto (`ps`, `exec`, `logs`…) fallan si no reciben las variables [verificado: `docker compose -f - ps` da «required variable CIDIA_REDIS_PASSWORD is missing a value»]. Ver la secuencia corregida en 6.8. La versión de abajo, que incluye los cambios de la verificación (`REDIS_PASSWORD`, `STORAGE_TYPE`, `GIN_MODE`, *healthchecks*, `depends_on` de la UI y contexto 4096), se volvió a validar en el servidor con `config` y `required: false`.

```yaml
name: cidia

x-log: &log
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }

services:
  gateway:
    build: ../gateway
    image: cidia-gateway:local
    <<: *log
    restart: unless-stopped
    env_file: [perfiles/oracle.env]
    ports: ["127.0.0.1:18700:8000"]
    networks: [interna, borde]
    volumes:
      - ${CIDIA_DATOS:-/home/ubuntu/CidIA/datos}/ficheros:/datos/ficheros
      - ${CIDIA_DATOS:-/home/ubuntu/CidIA/datos}/generador-de-contenido:/datos/generador-de-contenido
    depends_on:
      postgres: { condition: service_healthy }
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    cpus: 1.0
    mem_limit: 512m
    pids_limit: 256

  postgres:
    image: pgvector/pgvector:pg17
    <<: *log
    restart: unless-stopped
    environment:
      POSTGRES_USER: cidia
      POSTGRES_PASSWORD: ${CIDIA_PG_PASSWORD:?falta CIDIA_PG_PASSWORD}
      POSTGRES_DB: cidia
    volumes:
      - pg-datos:/var/lib/postgresql/data
      - ./postgres/initdb:/docker-entrypoint-initdb.d:ro
    networks: [interna]
    shm_size: 128m
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cidia -d cidia"]
      interval: 10s
      timeout: 5s
      retries: 6
    cpus: 1.0
    mem_limit: 512m
    pids_limit: 256

  ollama:
    image: ollama/ollama:0.40.2
    <<: *log
    restart: unless-stopped
    environment:
      OLLAMA_HOST: "0.0.0.0:11434"
      OLLAMA_NO_CLOUD: "1"
      OLLAMA_CONTEXT_LENGTH: "4096"   # verificación: con 8192 los dos Qwen3 0.6B no caben en 2560m (6.5)
      OLLAMA_NUM_PARALLEL: "1"
      OLLAMA_MAX_LOADED_MODELS: "2"
      OLLAMA_KEEP_ALIVE: "10m"
    volumes: [ollama-modelos:/root/.ollama]
    ports: ["127.0.0.1:18720:11434"]
    networks: [interna, borde]
    cpus: 2.0
    cpu_shares: 512
    mem_limit: 2560m
    pids_limit: 256

  asr:
    image: ghcr.io/speaches-ai/speaches:0.8.3-cpu
    profiles: [voz]
    <<: *log
    restart: unless-stopped
    volumes: [hf-cache:/home/ubuntu/.cache/huggingface/hub]
    ports: ["127.0.0.1:18721:8000"]
    networks: [interna, borde]
    cpus: 1.5
    cpu_shares: 512
    mem_limit: 1536m
    pids_limit: 256

  qdrant:
    image: qdrant/qdrant:v1.16.2
    profiles: [weknora]
    <<: *log
    restart: unless-stopped
    volumes: [qdrant-datos:/qdrant/storage]
    networks: [interna]
    cpus: 1.0
    mem_limit: 512m
    pids_limit: 256

  redis:
    image: redis:7-alpine
    profiles: [weknora]
    <<: *log
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "128mb",
              "--maxmemory-policy", "noeviction",
              "--requirepass", "${CIDIA_REDIS_PASSWORD:?falta CIDIA_REDIS_PASSWORD}"]
    volumes: [redis-datos:/data]
    networks: [interna]
    cpus: 0.5
    mem_limit: 192m
    pids_limit: 64

  docreader:
    image: wechatopenai/weknora-docreader:v0.8.2
    profiles: [weknora]
    <<: *log
    restart: unless-stopped
    environment:
      TZ: Europe/Madrid
      DOCREADER_GRPC_MAX_WORKERS: "2"
    volumes: [docreader-tmp:/tmp/docreader]
    networks: [interna]
    healthcheck:   # el mismo que usa WeKnora (docker-compose.yml de v0.8.2)
      test: ["CMD", "grpc_health_probe", "-addr=localhost:50051"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    cpus: 1.0
    cpu_shares: 512
    mem_limit: 1g
    pids_limit: 512

  weknora:
    image: wechatopenai/weknora-app:v0.8.2
    profiles: [weknora]
    <<: *log
    restart: unless-stopped
    env_file: [perfiles/weknora.env]
    environment:
      DB_DRIVER: postgres
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_NAME: weknora
      RETRIEVE_DRIVER: qdrant
      QDRANT_HOST: qdrant
      QDRANT_PORT: "6334"
      REDIS_ADDR: "redis:6379"
      REDIS_PASSWORD: ${CIDIA_REDIS_PASSWORD:?falta CIDIA_REDIS_PASSWORD}
      DOCREADER_ADDR: "docreader:50051"
      OLLAMA_BASE_URL: "http://ollama:11434"
      WEKNORA_SANDBOX_DOCKER_ENABLED: "false"
      STORAGE_TYPE: local
      GIN_MODE: release
      TZ: Europe/Madrid
    volumes:
      - weknora-ficheros:/data/files
      - docreader-tmp:/tmp/docreader:ro
    networks: [interna]
    healthcheck:   # la imagen trae curl; ruta /health en internal/router/router.go:145
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_started }
      qdrant: { condition: service_started }
      docreader: { condition: service_healthy }
    cpus: 1.0
    mem_limit: 1g
    pids_limit: 512

  weknora-ui:
    image: wechatopenai/weknora-ui:v0.8.2
    profiles: [weknora]
    <<: *log
    restart: unless-stopped
    environment:
      APP_HOST: weknora
      APP_PORT: "8080"
      APP_SCHEME: http
    ports: ["127.0.0.1:18701:80"]
    networks: [interna, borde]
    depends_on:   # como en WeKnora: su nginx resuelve APP_HOST al arrancar
      weknora: { condition: service_healthy }
    cpus: 0.25
    mem_limit: 128m
    pids_limit: 64

networks:
  interna:
    name: cidia-interna
    internal: true
    ipam:
      config: [{ subnet: 172.29.11.0/24 }]
  borde:
    name: cidia-borde
    ipam:
      config: [{ subnet: 172.29.10.0/24 }]

volumes:
  pg-datos: {}
  ollama-modelos: {}
  hf-cache: {}
  qdrant-datos: {}
  redis-datos: {}
  docreader-tmp: {}
  weknora-ficheros: {}
```

`compose.debug.yml` (también validado fusionado con el anterior):

```yaml
services:
  postgres:  { ports: ["127.0.0.1:18710:5432"], networks: [interna, borde] }
  redis:     { ports: ["127.0.0.1:18711:6379"], networks: [interna, borde] }
  qdrant:    { ports: ["127.0.0.1:18712:6333", "127.0.0.1:18713:6334"], networks: [interna, borde] }
  weknora:   { ports: ["127.0.0.1:18702:8080"], networks: [interna, borde] }
  docreader: { ports: ["127.0.0.1:18750:50051"], networks: [interna, borde] }
```

Notas sobre el borrador, con su fuente:

* **PostgreSQL sin ParadeDB.** El compose de WeKnora usa `paradedb/paradedb:v0.22.6-pg17` (`docker-compose.yml:532`), y ParadeDB es **AGPL-3.0** [verificado en la API de GitHub]. Con `RETRIEVE_DRIVER=qdrant`, WeKnora conecta para migrar con `app.skip_embedding=true` (`internal/container/container.go:809-825`). Las migraciones que piden `vector`, `pg_search` o `bm25` están protegidas. Precisión de la verificación: `000002` (`:7-18`), `000008`, `000011` y `000099` miran directamente `app.skip_embedding`; `000059` comprueba si existe la tabla `embeddings` y `000095` si existe la extensión `vector`. El efecto es el mismo. Sin protección solo quedan `uuid-ossp` (`000000_init.up.sql:7`) y `pg_trgm` (`000041_task_queue_and_wiki_indexes.up.sql:32`), ambas de `contrib`. La imagen `pgvector/pgvector:pg17` se construye `FROM postgres:17-bookworm` (`Dockerfile` de pgvector), que incluye `contrib`. Las dos están marcadas como *trusted* [verificado: `trusted = true` en `contrib/pg_trgm/pg_trgm.control` y `contrib/uuid-ossp/uuid-ossp.control` de `REL_17_STABLE`]. Con esto, el rol `weknora`, dueño de su BD, puede crearlas sin ser superusuario. En las migraciones `*.up.sql` no hay órdenes que exijan superusuario (`ALTER SYSTEM`, `CREATE ROLE`, `EVENT TRIGGER`…) [verificado con grep]. Falta probarlo en ejecución. Una sola instancia de PostgreSQL con dos bases (`cidia` y `weknora`) ahorra unos 150-250 MiB frente a dos instancias [inferencia].
* `postgres/initdb/10-weknora.sh` (sin probar). Necesita `WEKNORA_DB_PASSWORD` en el `environment` de postgres y solo se ejecuta cuando el volumen está vacío. **Debe ser ejecutable (`chmod +x`).** Si no lo es, el *entrypoint* oficial lo carga con `source` en su propio shell (`docker-entrypoint.sh`, rama `*.sh)`, líneas 180-187 de `17/bookworm`) y el `set -u` del script se aplicaría al resto del *entrypoint* [verificado el comportamiento; el efecto del `set -u` es inferencia]:
  ```sh
  #!/bin/sh
  set -eu
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
  CREATE ROLE weknora LOGIN PASSWORD '${WEKNORA_DB_PASSWORD}';
  CREATE DATABASE weknora OWNER weknora;
  SQL
  ```
* La configuración de WeKnora ya viene dentro de la imagen (`docker/Dockerfile.app:137` copia `config/`), así que **no hace falta** montar `config.yaml` salvo que lo cambiemos. El nginx de la UI construye las rutas del proxy con `APP_HOST`, `APP_PORT` y `APP_SCHEME` (`frontend/nginx.conf:78-205`): por eso `APP_HOST: weknora`.
* Qdrant: el compose de WeKnora fija `v1.16.2` (`docker-compose.yml:657`), pero `go.mod:50` usa `github.com/qdrant/go-client v1.18.1`. Las dos versiones tienen arm64 [verificado]. Dejamos 1.16.2 por ser la que prueba WeKnora; si el cliente se queja, subimos a `v1.18.2`.
* No se endurecen con `cap_drop` las imágenes de terceros. El nginx de la UI escucha en el 80 y el entrypoint de WeKnora usa `gosu`; quitarles capacidades podría romperlos [inferencia]. El endurecimiento queda para nuestras imágenes (gateway y espacio de trabajo). [Verificación: el entrypoint de WeKnora hace `chown -R appuser` (`scripts/docker-entrypoint.sh:18`) y `exec gosu appuser` (`:68`), y las dos cosas necesitan CAP_CHOWN y CAP_SETUID/SETGID.] Para el gateway, con `cap_drop: [ALL]`, la imagen tiene que ejecutarse como UID 1000 (`USER 1000:1000`). Las carpetas de `datos/` son de `ubuntu` (1000) y un root sin `CAP_DAC_OVERRIDE` no podría escribir en ellas [inferencia].
* **SSRF de WeKnora (añadido en la verificación).** Los modelos de origen `local` (Ollama) usan `OLLAMA_BASE_URL` con un cliente HTTP normal, sin filtro SSRF (`internal/models/utils/ollama/ollama.go:29-55`, `internal/models/chat/chat.go:125`), así que `http://ollama:11434` funciona. Los modelos de origen `remote` (compatibles con OpenAI) sí pasan `ValidateURLForSSRF` (`internal/models/chat/chat.go:176-179`), que rechaza los nombres que resuelven a IP privadas (`internal/utils/security.go:342-420`). Si en WeKnora se registra el gateway como modelo remoto (`http://gateway:8000/v1`), hay que añadir `SSRF_WHITELIST=gateway`. El cliente de Qdrant configurado por variables solo exige lista blanca si `SSRF_DNS_WHITELIST_ONLY` está activo (`internal/container/container.go:1275-1279`, `internal/utils/security.go:1203-1209`); por defecto no lo está.
* `docs/arquitectura.md` (línea 24) dice que Ollama «solo escucha en la red interna de Docker», pero en una red `internal` no puede hacer `ollama pull`. En el borrador va en `borde` y publica en 127.0.0.1:18720 para facilitar las pruebas. Para cumplir la arquitectura al pie de la letra: dejar Ollama solo en `interna` y mover `borde` y el puerto 18720 a `compose.debug.yml`, que se usaría únicamente para descargar modelos y depurar.
* speaches 0.8.3: usuario UID 1000, puerto 8000 y caché en `/home/ubuntu/.cache/huggingface/hub` [verificado: `Dockerfile:16-17, 38-39, 51` y `compose.cpu.yaml` del tag `v0.8.3`]. `latest-cpu` apunta al mismo digest que `0.8.3-cpu`.
* **Programas GPL dentro de imágenes de terceros (añadido en la verificación).** La imagen de speaches instala el `ffmpeg` de Ubuntu (`Dockerfile:8-9`; la variante CPU parte de `ubuntu:24.04`). Debian lo compila con `--enable-gpl` y `--enable-libx265` (`debian/rules:30, 65` en salsa.debian.org), así que es un binario **GPL**, igual que el del host que se descartó. La imagen de docreader instala `antiword` (GPL), `libreoffice` (MPL-2.0) y `openjdk-17-jre-headless` (GPL con excepción de *classpath*) (`docker/Dockerfile.docreader`, etapa `runner`). CidIA no enlaza con ellos: son programas aparte en imágenes que se descargan de sus registros. **Mientras el instalador descargue las imágenes y no las redistribuya, no hay obligación nueva** [inferencia legal, no es asesoramiento]. Si el instalador del MSI empaqueta imágenes para instalar sin conexión (`docker save`), CidIA pasaría a redistribuir binarios GPL: habría que ofrecer el código fuente o dejar fuera esas imágenes. Hay que reflejarlo en `THIRD_PARTY_NOTICES.md`.

### 6.5 Ollama en ARM sin GPU

* Variables comprobadas en `envconfig/config.go` de `v0.40.2`: `OLLAMA_CONTEXT_LENGTH` (`:230`), `OLLAMA_NO_CLOUD` (`:238`, con `NoCloud()` en `:443-449`; garantiza «solo modelos locales»), `OLLAMA_NUM_PARALLEL` (`:277`, vale 1 por defecto) y `OLLAMA_MAX_LOADED_MODELS` (`:279`).
* **Hilos:** Ollama 0.40.2 solo pasa `-t` a `llama-server` si se fija `num_thread` (`llm/llama_server.go:415-418`). Si no, `llama-server` elige el número de hilos por su cuenta y probablemente usará los 4 núcleos aunque el contenedor tenga `cpus: 2.0`, con estrangulamiento de CFS [inferencia]. Hay que fijar `num_thread: 2` en las opciones de cada petición del gateway, o crear alias con `PARAMETER num_thread 2` en un Modelfile. [Verificación: `num_thread` es un campo de `api.Options` (`api/types.go:600`) y por defecto vale 0, «que decida el runtime» (`:1198`). La tabla de parámetros de `docs/modelfile.mdx` no lo lista, así que el alias con Modelfile es probable pero no está confirmado; la vía segura es mandarlo en `options` de `/api/chat` y `/api/embed`. WeKnora llama a Ollama con su propio cliente y no deja fijar opciones, así que para sus peticiones solo sirve el alias.]
* **Modelos para Oracle** (tamaños y licencias leídos de `registry.ollama.ai`) [verificado]:

  | Uso | Modelo | Tamaño | Licencia |
  |---|---|---|---|
  | Chat y agente (por defecto) | `qwen3:0.6b` | 523 MB | Apache-2.0 |
  | Alternativa mínima | `granite4:350m` | 708 MB | Apache-2.0 |
  | Embeddings (**el mismo que en el MSI**: misma dimensión y mismas colecciones) | `qwen3-embedding:0.6b` | 639 MB | Apache-2.0 (*corrección:* su manifiesto en `registry.ollama.ai` **no tiene capa de licencia**; la licencia se ha verificado en la ficha de `Qwen/Qwen3-Embedding-0.6B` en Hugging Face) |
  | Visión y misma familia que el MSI (opcional, pruebas puntuales) | `ministral-3:3b` (ollama.com indica *vision* y *tools*) | 2 954 MB | Apache-2.0 |
  | MSI (no se instala aquí) | `ministral-3:8b` | 6 022 MB | Apache-2.0 |
  | **Evitar** | `gemma3:*` | — | *Gemma Terms of Use* (no permisiva) |

  ~~Con `qwen3:0.6b` y `qwen3-embedding:0.6b` cargados a la vez y contexto de 8192 caben en 2,5 GiB.~~ **Corregido en la verificación: con 8192 probablemente no caben.** El cálculo:
  * Ollama pasa a `llama-server` `-c num_ctx × num_parallel` (`llm/llama_server.go:378`). `num_ctx` toma por defecto `OLLAMA_CONTEXT_LENGTH` para **cualquier** modelo, también el de embeddings (`api/types.go:1195`).
  * El propio Ollama estima la caché KV como `2 × capas × cabezas_kv × dim_cabeza × contexto × 2 bytes` (`llm/llama_server.go:2804`). Los dos Qwen3 0.6B tienen 28 capas, 8 cabezas KV y dimensión 128 (`config.json` de `Qwen/Qwen3-0.6B` y de `Qwen/Qwen3-Embedding-0.6B`). Salen 112 KiB por token: **896 MiB por modelo con 8192** y 448 MiB con 4096.
  * Con 8192: unos 523 MB + 896 MiB + búferes del chat, más 639 MB + 896 MiB + búferes del embedding, es decir, unos 3,2-3,5 GB, por encima de los 2,68 GB (2560 MiB) del `mem_limit`. Como Ollama no ve el límite (cgroups v1), cargaría los dos y el OOM-killer mataría un `llama-server` [inferencia basada en la fórmula de Ollama; hay que medirlo].
  * **Cambio aplicado en el borrador:** `OLLAMA_CONTEXT_LENGTH=4096`. Además, para los embeddings, un alias con contexto 2048 (los fragmentos de WeKnora son mucho más cortos [inferencia]). Con eso quedan unos 1,2 GB para el chat y 1,0 GB para los embeddings, por debajo de 2,5 GiB:
    ```
    # Modelfile de cidia-embed (crear con: docker compose ... exec ollama ollama create cidia-embed -f /ruta/Modelfile)
    FROM qwen3-embedding:0.6b
    PARAMETER num_ctx 2048
    ```
    Alternativas: `OLLAMA_MAX_LOADED_MODELS=1` (alterna los modelos con más latencia) u `OLLAMA_KV_CACHE_TYPE=q8_0` (`envconfig/config.go:222`; reduce la caché a la mitad, pero puede requerir *flash attention* [inferencia]).

  Para probar `ministral-3:3b`, subir temporalmente `mem_limit` de ollama a 4,5 GiB y no levantar el perfil `voz`. Su caché KV con 4096 tampoco es despreciable: hay que medirla antes [inferencia].

### 6.6 Presupuesto de recursos

**Peor caso de los demás servicios.** Hoy usan 3,9 GiB (host y contenedores). LocalAI puede crecer de 89 MiB hasta su límite de 9 GiB, lo que da unos **12,8 GiB** antes de CidIA. Con 23,4 GiB y sin swap, conviene dejar 2,5-3 GiB libres para la caché de páginas y el host.

| Conjunto de CidIA | Suma de `mem_limit` | Peor total del servidor |
|---|---|---|
| Base: gateway, postgres y ollama | 3,5 GiB | 16,3 GiB |
| Base + `weknora` (qdrant, redis, docreader, weknora y ui) | **6,3 GiB** | 19,1 GiB |
| Base + `weknora` + `voz` | **7,8 GiB** | 20,6 GiB |
| Lo anterior + 2 contenedores del espacio de trabajo (256 MiB cada uno) | 8,3 GiB | 21,1 GiB |

Reglas propuestas:

* **Tope de 8 GiB para CidIA en Oracle.** Perfil `voz` solo mientras se prueba la transcripción, y como máximo 2 contenedores del espacio de trabajo a la vez.
* CPU: `cpus` limita cada servicio. Los procesos pesados (ollama, docreader, asr) llevan `cpu_shares: 512` (la mitad del valor por defecto) para que, si hay competencia, ganen los servicios del usuario. LocalAI tiene `cpus: 3.0`: si los dos modelos infieren a la vez, ambos irán lentos. Conviene **no medir rendimiento en Oracle**.
* Disco previsto: unos **5,7 GB comprimidos** de imágenes arm64 (ollama 2,8 GB, docreader 1,5 GB, weknora-app 0,55 GB, speaches 0,54 GB, pgvector 0,16 GB y el resto menos de 0,1 GB cada una), que se quedan en unos 12-16 GB descomprimidos [inferencia]. Más unos 1,2 GB de modelos y los datos sintéticos: bien dentro de los 112 GB libres. En total son unas 9 descargas, muy por debajo del límite de 100 por hora.

### 6.7 Acceso desde el PC por túnel SSH

En PowerShell (no deja nada instalado en el PC):

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 `
  -i "C:\Users\pascu\Desktop\05_DOCUMENTOS_PERSONALES\05_Claves_SSH\ia_workspace" `
  -L 18700:127.0.0.1:18700 -L 18701:127.0.0.1:18701 `
  -L 18720:127.0.0.1:18720 -L 18721:127.0.0.1:18721 `
  ubuntu@143.47.56.7
```

* La app de escritorio (dsh/CidIA) del PC apunta a `http://127.0.0.1:18700/v1` (proveedor OpenAI-compatible) y a `http://127.0.0.1:18700/mcp` (MCP). Los paneles usan `http://127.0.0.1:18700/api`.
* Consola de WeKnora: `http://127.0.0.1:18701`. Ollama directo, para pruebas: `http://127.0.0.1:18720/api/tags`.
* Para depurar, añadir `-L 18702:127.0.0.1:18702 -L 18710:127.0.0.1:18710 -L 18712:127.0.0.1:18712` y levantar el servicio con `-f compose.debug.yml`.
* Opcional, si el usuario lo aprueba porque cambia la configuración del PC: un bloque `Host cidia-oracle` en `~/.ssh/config` con esos `LocalForward`.

### 6.8 Secuencia de despliegue (fase 2; **no ejecutada**)

```bash
# en el servidor, dentro de /home/ubuntu/CidIA
git clone <repo-privado> cidia
mkdir -p secretos datos/{ficheros,generador-de-contenido,captura} copias registros && chmod 700 secretos
# generar secretos/cidia.env y secretos/weknora.env con openssl rand (sin imprimirlos)
cd cidia/servidor/despliegue
# Verificación: TODAS las órdenes de compose necesitan las variables obligatorias
# (sin ellas, hasta 'ps' y 'exec' fallan con "required variable ... is missing a value").
DC="docker compose --env-file ../../../secretos/cidia.env"
$DC --profile weknora pull
$DC --profile weknora up -d
$DC exec ollama ollama pull qwen3:0.6b
$DC exec ollama ollama pull qwen3-embedding:0.6b
$DC --profile weknora ps        # todo healthy; comprobar puertos con: ss -tln | grep 187
# desmontar SOLO lo nuestro:
$DC --profile '*' down        # (-v borra datos)
```

`perfiles/weknora.env` de la sección 6.4 debe apuntar a `secretos/weknora.env`. Mientras no se cree un enlace simbólico o el instalador no lo copie, conviene usar `env_file: [../../../secretos/weknora.env]`. Lo decidirá quien escriba `instalar-servidor.sh`.

### 6.9 Espacio de trabajo del agente (contenedores sin red) en un servidor compartido

* Para crear un contenedor por petición hace falta la API de Docker. Montar `/var/run/docker.sock` en un contenedor de CidIA equivale a **root en el host** y daría control sobre postiz, n8n, waha y los demás.
* Propuesta para Oracle:
  * Solo el servicio `espacio-trabajo` (perfil `espacio`, en la red `interna`, sin puertos) monta el socket. El gateway **nunca** lo monta.
  * El ejecutor solo crea, inspecciona y borra contenedores con la etiqueta `cidia.espacio=1` y una imagen de una lista blanca, y rechaza cualquier otra operación.
  * Los contenedores se crean con `--network none --read-only --tmpfs /tmp:size=64m --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 256m --cpus 0.5 --user 1000:1000 --label cidia.espacio=1 -v <RUTA_HOST>/datos/generador-de-contenido/<usuario>:/trabajo`.
  * La ruta del `-v` es **la del host** (`/home/ubuntu/CidIA/datos/...`), no la del contenedor del ejecutor: hay que pasarla por variable (`CIDIA_DATOS_HOST`).
* gVisor (`runsc`) daría más aislamiento, pero no está instalado e instalarlo cambia la configuración del daemon (`daemon.json`). Queda para el MSI.

---

## 7. Compatibilidad ARM de las piezas

| Pieza | Imagen o etiqueta | arm64 | Tamaño arm64 (comprimido) |
|---|---|---|---|
| WeKnora app | `wechatopenai/weknora-app:v0.8.2` | sí | 546 MB |
| WeKnora docreader | `wechatopenai/weknora-docreader:v0.8.2` | sí | 1 520 MB |
| WeKnora UI | `wechatopenai/weknora-ui:v0.8.2` | sí | 32 MB |
| Qdrant | `qdrant/qdrant:v1.16.2` / `v1.18.2` | sí | 71 / 69 MB |
| Ollama | `ollama/ollama:0.40.2` | sí | 2 806 MB |
| PostgreSQL + pgvector | `pgvector/pgvector:pg17` | sí | 158 MB |
| Redis | `redis:7-alpine` | sí (`arm64v8`) | 17 MB |
| speaches (Whisper CPU) | `ghcr.io/speaches-ai/speaches:0.8.3-cpu` | sí | 542 MB |
| Base del gateway | `python:3.12-slim-bookworm` | sí (`arm64v8`) | — |
| ffmpeg LGPL | BtbN `linuxarm64-lgpl` (n8.1) | sí | 116 MB |
| (descartado) ParadeDB | `paradedb/paradedb:v0.22.6-pg17` | sí | 502 MB, pero **AGPL-3.0** |

Fuentes: API de Docker Hub (`/v2/repositories/<repo>/tags/<tag>`), manifiestos OCI de ghcr.io y API de releases de GitHub, consultadas el 9 de octubre de 2026. **Nada de lo previsto es incompatible con ARM.** Lo único que no se puede probar aquí es la GPU (CUDA y el modelo de 8B), que queda para el MSI.

Licencias consultadas en la API de GitHub: speaches MIT, Qdrant Apache-2.0, Ollama MIT y WeKnora MIT con componentes de terceros (cabecera del `LICENSE`). pgvector aparece como `NOASSERTION` en GitHub; es PostgreSQL License [verificado en la verificación: el fichero `LICENSE` de pgvector es el texto de la PostgreSQL License; pendiente de anotar en `THIRD_PARTY_NOTICES.md`]. ParadeDB: AGPL-3.0 [verificado en la API de GitHub]. WeKnora también lleva componentes MPL-2.0 (`go-sql-driver/mysql`, `go-m1cpu`; `THIRD_PARTY_NOTICES.md:17, 33`), con *copyleft* solo a nivel de fichero. Las imágenes de speaches y docreader contienen programas GPL: ver la nota de la sección 6.4.

ffmpeg de BtbN (añadido en la verificación): la versión `latest` va cambiando. Según el README de BtbN/FFmpeg-Builds, se guardan las 14 últimas compilaciones diarias y la última de cada mes durante dos años. Para que el `Dockerfile` sea reproducible hay que fijar una compilación mensual concreta y comprobar su SHA-256, o guardar una copia del tarball. Como la imagen del gateway redistribuye ese binario LGPL, hay que ofrecer su código fuente correspondiente.

---

## 8. Observaciones del servidor (no son de CidIA; no se han tocado)

* `/home/ubuntu/rclone-pcloud.log` ocupa unos 816 MB y crece; el journal, 4,0 GB. No es urgente con 112 GB libres, pero conviene saberlo.
* Escuchan en `0.0.0.0` servicios que quizá no deberían estar expuestos: uvicorn en 8000, node en 4001-4005, cupsd en 631 y rpcbind en 111. Que sean accesibles desde fuera depende de la *security list* de Oracle, que no se ve desde dentro. CidIA no añade nada expuesto.
* `unattended-upgrades` está activo y `live-restore` desactivado: una actualización de `docker.io` reinicia todos los contenedores. [Verificación: en la práctica no la hará `unattended-upgrades`, porque `docker.io` viene de `focal-updates`, que no está en `Allowed-Origins`, y no hay Ubuntu Pro. El riesgo es un `apt upgrade` manual.]
