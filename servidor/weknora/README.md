# WeKnora como motor de conocimiento de CidIA (opcional)

CidIA trae dos motores de conocimiento intercambiables (`cidia/conocimiento/`):

| Motor | Cuándo | Qué usa |
|---|---|---|
| `pgvector` (**por defecto**) | Siempre disponible | PostgreSQL de CidIA: pgvector, búsqueda de texto en castellano y fusión RRF. Licencia PostgreSQL. |
| `weknora` | Si se levanta el perfil `weknora` del despliegue | WeKnora v0.8.2 (MIT) con Qdrant, siempre detrás del gateway. |

Se elige con `CIDIA_MOTOR_CONOCIMIENTO=pgvector|weknora`. Ningún otro módulo cambia: la consola
de documentos, el copiloto y las herramientas MCP llaman a la misma interfaz `MotorConocimiento`.

## Aviso de licencias (leer antes de activarlo)

Resumen del informe `docs/investigacion/03_weknora_integracion.md` (§1.7, §6 y §7). No es
asesoramiento legal; la decisión es del equipo.

* **`docreader`** (imagen `wechatopenai/weknora-docreader`) incluye **EbookLib, con licencia
  AGPL-3.0+, importada en el propio proceso** (lector de EPUB y dependencia de `textract`), y
  ejecuta `antiword` (GPL-2.0) como programa externo. Choca con la regla del proyecto de usar solo
  dependencias permisivas. **Por eso el motor por defecto de CidIA es el propio.** Alternativas:
  prescindir de `docreader` y usar `anydoc` (MIT, ya enlazado en la app de WeKnora), usar la imagen
  sin modificar como servicio separado y documentarlo, o construir una imagen sin EbookLib.
* **Redis**: solo `redis:7.2-alpine` (BSD-3) o `valkey/valkey:8-alpine`. Las etiquetas `7-alpine`
  y `7.4+` son RSALv2/SSPLv1.
* **PostgreSQL de WeKnora**: `pgvector/pgvector`, nunca `paradedb/paradedb` (AGPL). Con
  `RETRIEVE_DRIVER=qdrant` las migraciones de `pg_search` se saltan.
* **Langfuse**: `LANGFUSE_ENABLED=false` obligatorio. El `.env.example` original trae claves de
  ejemplo que lo activan y enviaría *prompts* y respuestas fuera.
* Cada dependencia nueva se anota en `THIRD_PARTY_NOTICES.md`.

## Cómo organiza CidIA el conocimiento en WeKnora

* **Una base por departamento** (su id queda en `departamentos.weknora_kb_id`) y una base
  **«Público»** (id en `empresa.config['weknora_kb_publico']`).
* Cada documento lleva la etiqueta de su **nivel mínimo** (`n1`…`n4`) y, si es material de
  formación, la etiqueta **`formacion`**. Los públicos van a «Público» con la etiqueta `publico`.
  Un documento sin departamento y no público va a «Público» sin esa etiqueta: solo lo encuentra la
  administración.
* En cada búsqueda el gateway calcula el alcance de la persona (departamento, nivel y formaciones
  activas), lanza **una búsqueda por cada base y etiquetas permitidas**, fusiona las listas con RRF
  y **vuelve a comprobar cada resultado contra la base de datos** (defensa en profundidad).
* La similitud que decide si una respuesta tiene respaldo la calcula el gateway con el mismo
  modelo de embeddings que el motor propio: la puntuación de WeKnora depende de si hay reranker.
* Los fragmentos que genera WeKnora se copian (sin vector) en la tabla `fragmentos` para la consola
  de documentos y para conservar los metadatos de cada parte (página, paso de una instrucción).
* Los usuarios de CidIA **no** se crean en WeKnora. Solo existe el administrador técnico, para la
  consola de WeKnora, y la API key `cidia-gateway`, que solo tiene el gateway.

## Puesta en marcha

### 1. Variables del perfil `weknora`

Además de lo que ya pone `despliegue/docker-compose.yml` y `despliegue/perfiles/weknora.env`,
conviene tener (informe 03, §1.4):

```dotenv
WEKNORA_LANGUAGE=es-ES          # resúmenes y preguntas generadas en castellano
TZ=Europe/Madrid
LANGFUSE_ENABLED=false
DISABLE_REGISTRATION=false      # solo hasta crear el administrador (paso 4)
OLLAMA_OPTIONAL=true
SSRF_WHITELIST=gateway,asr,ollama
```

Los secretos (`WEKNORA_DB_PASSWORD`, `WEKNORA_JWT_SECRET`, `WEKNORA_AES_KEY` de 32 bytes,
`CIDIA_REDIS_PASSWORD`) se generan en el servidor y no se imprimen.

### 2. Levantar WeKnora

```sh
cd servidor/despliegue
docker compose --env-file <secretos>/cidia.env --profile weknora up -d
```

La base `weknora` y sus extensiones las crea `postgres/initdb/10-weknora.sh` en el primer arranque
de PostgreSQL. Si el volumen ya existía, hay que crearlas a mano como superusuario.

### 3. Ejecutar `inicializar.py`

El script registra el administrador técnico, inicia sesión, crea la API key del gateway (con el JWT
del propietario, que es la única forma), da de alta los modelos de Ollama, ajusta el número de
resultados por búsqueda y crea las bases y etiquetas con los departamentos de CidIA.

**La API key nunca se imprime**: se escribe en el fichero que indiques, con permisos 600. Con
`--formato env` (por defecto) se escribe o se sustituye la línea `CIDIA_WEKNORA_API_KEY=…`, así que
puede apuntar directamente al fichero de secretos que usa `docker compose --env-file`. Si el
fichero ya tiene una clave válida, se reutiliza.

Desde el PC, con el túnel SSH y `compose.debug.yml` (WeKnora en `127.0.0.1:18702` y PostgreSQL de
CidIA en `127.0.0.1:18710`), en `servidor/gateway` para que se lea su `.env`:

```sh
.venv/bin/python ../weknora/inicializar.py \
    --url http://127.0.0.1:18702/api/v1 \
    --contrasena-fichero /ruta/segura/weknora_admin.txt \
    --salida-clave /ruta/segura/cidia.env
```

O dentro del contenedor del gateway (ya trae el paquete `cidia` y la conexión a la BD):

```sh
docker compose cp ../weknora/inicializar.py gateway:/tmp/inicializar.py
docker compose exec gateway python /tmp/inicializar.py --url http://weknora:8080/api/v1 \
    --contrasena-fichero /datos/secretos/weknora_admin.txt --salida-clave /datos/secretos/weknora.env
```

Opciones útiles:

| Opción | Para qué |
|---|---|
| `--modelo-chat`, `--modelo-embeddings`, `--dimension` | Modelos de Ollama (por defecto `qwen3:0.6b`, `qwen3-embedding:0.6b`, 1024). Deben estar ya en Ollama (`ollama pull`): el script lo comprueba antes de darlos de alta. |
| `--permitir-descarga` | Da de alta también los modelos que aún no están en Ollama, para que WeKnora los descargue (solo si Ollama tiene salida a Internet). Ojo: con `OLLAMA_OPTIONAL=true`, si Ollama no responde, el modelo queda «activo» sin existir. |
| `--top-k 20` | Fragmentos que devuelve cada búsqueda (`rerank_top_k` del espacio; WeKnora no lo admite por petición). |
| `--sin-bd` | No tocar la BD de CidIA. El gateway crea cada base al subir el primer documento del departamento. |
| `--reindexar` | Vuelve a indexar en WeKnora los documentos que ya había (al pasar del motor propio a WeKnora). Los de audio se vuelven a transcribir. |

### 4. Cerrar el registro

Pon `DISABLE_REGISTRATION=true` en `perfiles/weknora.env` y reinicia `weknora`. Mientras está
abierto, cualquiera con acceso a la red interna podría registrarse.

### 5. Activar el motor en el gateway

```dotenv
CIDIA_MOTOR_CONOCIMIENTO=weknora
CIDIA_WEKNORA_URL=http://weknora:8080/api/v1     # ya lo pone el compose
CIDIA_WEKNORA_API_KEY=…                          # la escribe inicializar.py
```

y reinicia el gateway. Si no usaste `--reindexar`, reindexa los documentos desde **Documentos**
(botón «Reindexar» de cada uno).

### 6. Comprobar

* **Administración → Sistema**: el motor de conocimiento debe salir en verde. Sin WeKnora, el
  gateway da mensajes claros («No se puede conectar con WeKnora en …», «Falta la API key…»).
* **Documentos → Probar búsqueda**: escribe una pregunta como la haría un operario y mira qué
  fragmentos salen, con su puntuación RRF, su similitud y las bases y etiquetas consultadas. La
  administración puede probar «como» cualquier persona o como invitado.

## Limitaciones conocidas

* **Palabras clave con Qdrant**: no hay BM25 y en castellano «de», «la» o «que» casan con casi
  todo. Conviene un reranker (formato Cohere) o desactivar `keyword_enabled` en las bases y medir
  con el conjunto de preguntas sintético (informe 03, §7.1).
* **El borrado en WeKnora es asíncrono**: el gateway ya no devuelve el documento (lo filtra con la
  BD), pero WeKnora puede tardar unos segundos en eliminarlo.
* **Mover un documento de departamento** o hacerlo público obliga a reindexarlo en la otra base;
  la consola lo hace sola. Cambiar nivel o formación solo reetiqueta.
* **Nunca publiques `weknora:8080`** fuera de la red interna: tiene CORS abierto y su única
  credencial útil es la del gateway.
