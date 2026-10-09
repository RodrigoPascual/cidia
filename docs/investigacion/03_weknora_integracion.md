# 03 · Integración de WeKnora v0.8.2 detrás del gateway CidIA

Fecha: 9 de octubre de 2026. Fuente principal: clon de WeKnora en la etiqueta `v0.8.2` (commit `3e8b0bf`, `VERSION` = `0.8.2`). Todas las rutas de fichero de este documento son relativas a la raíz de ese clon salvo que se indique otra cosa.

Marcas usadas:

* **[verificado]**: leído en el código fuente, en un registro público (Docker Hub, PyPI, GitHub) o en el servidor Oracle con órdenes de solo lectura.
* **[inferencia]**: deducido del código pero no probado en ejecución. Hay que comprobarlo en la fase 2.

Este documento complementa a `05_servidor_oracle.md` (estructura de despliegue, redes, puertos 18700-18750). Uso los mismos nombres de servicio: `weknora`, `weknora-ui`, `docreader`, `qdrant`, `redis`, `postgres`, `ollama`, `asr` y `gateway`.

---

## 0. Resumen

1. **Servicios mínimos**: `weknora` (app Go), `docreader` (gRPC Python), `postgres` (imagen `pgvector/pgvector`), `redis` y `qdrant`. `weknora-ui` es opcional: solo sirve como consola de administración. Con `RETRIEVE_DRIVER=qdrant` WeKnora no necesita ParadeDB (AGPL), porque sus migraciones de `pg_search`/BM25 se saltan [verificado].
2. **Corrección al borrador de `05_servidor_oracle.md`**: `redis:7-alpine` apunta hoy a Redis 7.4, que tiene licencia RSALv2/SSPLv1 (no permisiva). Hay que usar `redis:7.2-alpine` (BSD-3) o `valkey/valkey:8-alpine` (BSD-3) [verificado].
3. **Arranque**: no hay usuario por defecto. Se registra el primer usuario por API, se hace login y, **con el JWT** (no se puede con API key), se crea una API key `full_access` para el gateway. Los modelos se crean con `POST /api/v1/models` y se asignan a cada base de conocimiento al crearla [verificado].
4. **Autenticación**: `X-API-Key` o `Authorization: Bearer <JWT>`. Toda ruta no declarada para API keys se deniega (*fail-closed*). La key de espacio queda fijada a su espacio (tenant). La memoria personal solo funciona por usuario si se activa el modo `direct_header` y el gateway envía `X-External-User-ID` [verificado].
5. **Búsqueda**: `POST /api/v1/knowledge-search` no admite «número de resultados» en la petición. Ese número sale de `rerank_top_k` en la configuración del espacio (por defecto 10). Para fijarlo por petición existe `POST /api/v1/knowledge-bases/{id}/hybrid-search` con `match_count`, pero sin rerank [verificado].
6. **Calidad con Qdrant**: la búsqueda por palabras clave con Qdrant es un filtro de texto con puntuación fija 1,0 y sin BM25. En castellano, palabras como «de» o «la» casan con casi todo. **Hace falta un reranker** o desactivar `keyword_enabled` y hacer el BM25 en castellano en nuestro PostgreSQL [verificado el código; el efecto en castellano es inferencia].
7. **arm64**: `weknora-app`, `weknora-ui` y `weknora-docreader` v0.8.2 publican imagen arm64 en Docker Hub. También `pgvector`, `qdrant`, `redis:7.2-alpine` y `valkey`. No hay que compilar nada en ARM [verificado].
8. **Salidas a Internet**: no hay telemetría ni analítica en el backend ni en la UI. El riesgo es **Langfuse**: `.env.example` trae claves de ejemplo que lo activan solas. Hay que poner `LANGFUSE_ENABLED=false`. El resto de salidas solo ocurren si se configuran (proveedores de modelos, búsqueda web, importar URL, skills, canales de mensajería). Con la red `cidia-interna` (`internal: true`) no hay salida posible [verificado].
9. **Licencias del `docreader`**: la imagen incluye EbookLib (AGPL-3.0+, importada en el proceso) y `antiword` (GPL-2.0, programa externo). La app incluye `anydoc` (MIT), que ya convierte en su propio proceso doc, docx, pptx, xlsx, epub y pdf. Hay que decidir si prescindimos de `docreader` o lo usamos sin modificar [verificado; la viabilidad sin docreader es inferencia].

---

## 1. Despliegue: compose y variables

### 1.1 Qué servicios del compose original necesitamos

`docker-compose.yml` de WeKnora define 25 servicios. Para CidIA:

| Servicio original | Líneas | Decisión | Motivo |
|---|---|---|---|
| `app` | 36-391 | **Sí** (como `weknora`) | API REST y procesado |
| `docreader` | 407-510 | **Sí** (revisar §7.3) | Analizador gRPC; `app` espera a que esté *healthy* (`docker-compose.yml:385-386`) |
| `postgres` | 531-550 | **Sí, cambiando la imagen** | El original es `paradedb/paradedb:v0.22.6-pg17` (AGPL). Va `pgvector/pgvector:pg17` |
| `redis` | 552-558 | **Sí, cambiando la imagen** | Cola asíncrona (asynq) y flujo de eventos; `redis:7.2-alpine` o `valkey` |
| `qdrant` | 656-669 | **Sí, quitando `profiles`** | `RETRIEVE_DRIVER=qdrant` |
| `frontend` | 2-34 | Opcional (como `weknora-ui`) | Solo consola de administración; no tiene castellano (§8) |
| `sandbox`, `odl-hybrid`, `searxng*`, `minio`, `neo4j`, `milvus`, `weaviate`, `doris-*`, `dex`, `langfuse-*`, `mcp` | — | **No** | Están en `profiles` o no aportan: el espacio de trabajo aislado, MCP y la identidad los pone el gateway |

**Redis es técnicamente opcional** [verificado]: sin `REDIS_ADDR`, WeKnora usa un ejecutor de tareas en el propio proceso (modo Lite): `internal/container/container.go:438-469` y `750-755`. Se pierden la cola persistente, los reintentos y el panel de colas. Que funcione con PostgreSQL y sin Redis es [inferencia]. Recomendación: mantener Redis o Valkey en el MSI y probar el modo sin Redis en Oracle si falta memoria.

### 1.2 Por qué basta PostgreSQL con pgvector

* Con `RETRIEVE_DRIVER` sin `postgres`, la conexión de migración lleva `app.skip_embedding=true` (`internal/container/container.go:809-825`).
* Las migraciones que crean `vector`, `pg_search` o índices `bm25` comprueban esa variable y no hacen nada: `migrations/versioned/000002_embeddings.up.sql:7-10`, `000011_pg_search_update.up.sql:6-9`, `000099_pg_search_0226.up.sql:7-9` [verificado].
* Sin esa protección solo quedan `uuid-ossp` (`000000_init.up.sql:7`) y `pg_trgm` (`000041_task_queue_and_wiki_indexes.up.sql:32`), que vienen en `contrib` [verificado].
* La memoria a largo plazo usa una columna `halfvec` solo si la extensión `vector` ya existe; si no, puntúa en el proceso (`000095_memory_vector_search.up.sql:27-36`) [verificado]. Para que la ordenación de la memoria se haga en la base de datos, hay que crear `vector` en la BD `weknora` **antes del primer arranque** de WeKnora (§1.6).

### 1.3 Compose mínimo autónomo (pruebas aisladas)

Para probar WeKnora solo, en su propio proyecto. En el despliegue real se usa el compose de `05_servidor_oracle.md` §6.4 con las correcciones de §1.7. Sin probar: solo se ha contrastado con el compose original.

```yaml
# compose.weknora-prueba.yml   →   docker compose -f compose.weknora-prueba.yml up -d
name: cidia-weknora-prueba

x-log: &log
  logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }

services:
  postgres:
    image: pgvector/pgvector:0.8.7-pg17
    <<: *log
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER:?falta DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?falta DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME:?falta DB_NAME}
    volumes:
      - wk-pg:/var/lib/postgresql/data
      - ./initdb:/docker-entrypoint-initdb.d:ro      # 01-extensiones.sql (§1.6)
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 6
    networks: [interna]

  redis:
    image: redis:7.2-alpine                          # BSD-3; NO usar 7-alpine (=7.4, RSAL/SSPL)
    <<: *log
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD:?falta REDIS_PASSWORD}"]
    volumes: [wk-redis:/data]
    networks: [interna]

  qdrant:
    image: qdrant/qdrant:v1.16.2
    <<: *log
    restart: unless-stopped
    volumes: [wk-qdrant:/qdrant/storage]
    networks: [interna]

  docreader:
    image: wechatopenai/weknora-docreader:v0.8.2
    <<: *log
    restart: unless-stopped
    environment:
      TZ: Europe/Madrid
      DOCREADER_GRPC_MAX_WORKERS: "2"
      MAX_FILE_SIZE_MB: "50"
    volumes: [wk-docreader-tmp:/tmp/docreader]
    healthcheck:
      test: ["CMD", "grpc_health_probe", "-addr=localhost:50051"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks: [interna]

  weknora:
    image: wechatopenai/weknora-app:v0.8.2
    <<: *log
    restart: unless-stopped
    env_file: [.env]                                  # mismo .env que interpola el compose (§1.4)
    volumes:
      - wk-ficheros:/data/files
      - wk-docreader-tmp:/tmp/docreader:ro
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_started }
      qdrant: { condition: service_started }
      docreader: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks: [interna]

  weknora-ui:                                         # opcional
    image: wechatopenai/weknora-ui:v0.8.2
    <<: *log
    restart: unless-stopped
    environment:
      APP_HOST: weknora
      APP_PORT: "8080"
      APP_SCHEME: http
      MAX_FILE_SIZE_MB: "50"
      DEFAULT_LOCALE: en-US
    ports: ["127.0.0.1:18701:80"]
    depends_on:
      weknora: { condition: service_healthy }
    networks: [interna, borde]

networks:
  interna: { internal: true }
  borde: {}

volumes:
  wk-pg: {}
  wk-redis: {}
  wk-qdrant: {}
  wk-docreader-tmp: {}
  wk-ficheros: {}
```

Notas sobre el compose, con su fuente:

* La imagen de la app ya trae `config/` (`docker/Dockerfile.app:137`), así que no hace falta montar `config.yaml` [verificado].
* La salud de la app está en `GET /health`, sin autenticación (`internal/router/router.go:145-147`). La del docreader usa `grpc_health_probe`, que ya va en la imagen (`docker-compose.yml:500-505`) [verificado].
* Sin `container_name`: el original fija `WeKnora-*` (`docker-compose.yml:14, 44, 414, 533, 554, 658`).
* `weknora` no publica puertos. Para depurar desde el PC se usa `compose.debug.yml` con `127.0.0.1:18702:8080`, añadiendo la red `borde` (ver `05_servidor_oracle.md` §6.2). En el servidor Oracle el puerto 80 ya está ocupado por Caddy [verificado con `ss -ltn`].
* La UI de WeKnora proxifica `/api` hacia `APP_HOST:APP_PORT` (`docker-compose.yml:21-26`).

### 1.4 Variables imprescindibles (`.env` de WeKnora)

Este `.env` lo leen tanto el compose (interpolación) como la app (`env_file`). Las claves se generan en el servidor y no se imprimen.

```dotenv
# --- Versión y ejecución ---
WEKNORA_VERSION=v0.8.2
GIN_MODE=release            # debug → sirve /swagger/index.html (router.go:151-158). Solo en Oracle.
LOG_LEVEL=info              # por defecto debug (docker-compose.yml:83)
TZ=Europe/Madrid            # por defecto Asia/Shanghai (docker-compose.yml:95)
WEKNORA_LANGUAGE=es-ES      # idioma de resúmenes y preguntas generadas; "es-ES" → "Spanish" (internal/types/context_helpers.go:421-422)
AUTO_MIGRATE=true
AUTO_RECOVER_DIRTY=true

# --- Base de datos (imprescindible) ---
DB_DRIVER=postgres
DB_HOST=postgres
DB_PORT=5432
DB_USER=weknora
DB_PASSWORD=<generar: openssl rand -hex 24>
DB_NAME=weknora

# --- Redis (imprescindible si hay servicio redis) ---
REDIS_ADDR=redis:6379
REDIS_PASSWORD=<generar>    # obligatorio: el compose pasa --requirepass
REDIS_DB=0
REDIS_PREFIX=stream:
STREAM_MANAGER_TYPE=redis   # vacío = flujo en memoria (internal/stream/factory.go:19-38)

# --- Recuperación: Qdrant (imprescindible) ---
RETRIEVE_DRIVER=qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6334            # gRPC
QDRANT_COLLECTION=weknora_embeddings
QDRANT_USE_TLS=false

# --- Analizador y ficheros ---
DOCREADER_ADDR=docreader:50051
DOCREADER_TRANSPORT=grpc
STORAGE_TYPE=local
LOCAL_STORAGE_BASE_DIR=/data/files
MAX_FILE_SIZE_MB=50

# --- Modelos ---
OLLAMA_BASE_URL=http://ollama:11434   # modelos con source=local
OLLAMA_OPTIONAL=true

# --- Claves (imprescindible en producción) ---
JWT_SECRET=<openssl rand -hex 32>     # vacío = aleatoria en cada arranque: los JWT caducan al reiniciar
SYSTEM_AES_KEY=<openssl rand -hex 16> # exactamente 32 bytes; cifra API keys y credenciales en BD
SYSTEM_SIGNING_KEY=<openssl rand -hex 32>

# --- Registro y espacios ---
DISABLE_REGISTRATION=false            # true después de crear el administrador (§2.1)
WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL=admin@cidia.example
WEKNORA_TENANT_SELF_SERVICE_CREATION_ENABLED=false
WEKNORA_TENANT_ENABLE_RBAC=true
WEKNORA_SANDBOX_DOCKER_ENABLED=false

# --- Sin salidas no deseadas ---
LANGFUSE_ENABLED=false                # OBLIGATORIO: ver §6
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# --- SSRF: nombres internos que la app puede llamar como modelos "remote" ---
SSRF_WHITELIST=gateway,asr,ollama
SSRF_WHITELIST_EXTRA=qdrant
CONCURRENCY_POOL_SIZE=2
```

* `SYSTEM_AES_KEY` de 32 bytes: `.env.example:549-555` [verificado].
* `JWT_SECRET` vacío genera uno aleatorio en cada arranque: `.env.example:546-548` [verificado].
* `WEKNORA_LANGUAGE` tiene prioridad sobre la cabecera `Accept-Language` (`internal/middleware/language.go:14-38`). El comentario de `.env.example:64-66` dice lo contrario y es erróneo [verificado].
* `SSRF_WHITELIST`: §1.5.

### 1.5 Cómo apuntar los modelos a Ollama o a un endpoint compatible con OpenAI

Hay dos vías [verificado]:

| Vía | `source` | URL | Restricción SSRF |
|---|---|---|---|
| Ollama de la red interna | `local` | Toma `OLLAMA_BASE_URL` (`internal/models/utils/ollama/ollama.go:32-35`). No se pasa `base_url`. | Ninguna: el cliente de Ollama usa un `http.Transport` normal (`ollama.go:47-55`) |
| Endpoint compatible con OpenAI (gateway, speaches, reranker) | `remote` + `provider: "generic"` | `parameters.base_url`, p. ej. `http://gateway:8000/v1` | **Sí**: `POST /models` valida `base_url` (`internal/handler/model.go:89-96`) y los clientes de embedding, ASR y rerank llaman con transporte anti-SSRF (`internal/models/embedding/transport.go:15-39`, `internal/models/asr/transport.go:11-25`) |

La protección SSRF bloquea cualquier nombre que resuelva a una IP privada, más `host.docker.internal`, `localhost`, los sufijos `.local`/`.internal`/`.lan`, las IP literales y los puertos 5432, 6379, 9200, etc. (`internal/utils/security.go:227-278`, `342-422`). **Un nombre de servicio Docker (`gateway`, `asr`) se rechaza si no está en `SSRF_WHITELIST`**. La lista blanca se aplica tanto al validar la URL como al conectar (`security.go:1331-1334` y `840-850`) [verificado].

Rutas que añade WeKnora a `base_url` [verificado]:

* Chat: protocolo OpenAI Chat Completions (`internal/models/providers/generic.go`, `API: api.APIOpenAICompletions`).
* Embeddings: `{base_url}/embeddings` (`internal/models/api/openaiembeddings/client.go:44-52`).
* Rerank: `{base_url}/rerank`, formato Cohere `{model, query, documents, top_n}` → `{results:[{index, relevance_score}]}` (`internal/models/api/cohererank/client.go:35-75`).
* ASR: `{base_url}/audio/transcriptions`, formato OpenAI (`internal/models/api/openaitranscriptions/client.go:38-47`).

Ollama no sirve rerank. Opciones: que el gateway exponga `POST /v1/rerank` en formato Cohere con un modelo cruzado de licencia Apache-2.0 (p. ej. Qwen3-Reranker-0.6B o bge-reranker-v2-m3), o un servidor aparte. La escala de puntuación se indica con `extra_config.score_scale` = `"logit"` (tipo Qwen3-Reranker) o `"probability"` (tipo BGE) (`generic.go`, `internal/models/legacy_keys.go:27`) [verificado; la elección del modelo es recomendación].

### 1.6 Extensiones en la base `weknora` (initdb)

Si WeKnora comparte el PostgreSQL de CidIA (opción de `05_servidor_oracle.md`), el script de `initdb` que crea el rol y la BD debe crear también las extensiones como superusuario. Así no dependemos de que `uuid-ossp` y `pg_trgm` sean *trusted*, y la memoria ordena en la BD. Sin probar:

```sh
#!/bin/sh
# postgres/initdb/10-weknora.sh — solo se ejecuta con el volumen vacío
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE ROLE weknora LOGIN PASSWORD '${WEKNORA_DB_PASSWORD}';
CREATE DATABASE weknora OWNER weknora;
SQL
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d weknora <<'SQL'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
```

### 1.7 Correcciones al borrador de `05_servidor_oracle.md` §6.4

| Punto | Borrador | Corrección | Fuente |
|---|---|---|---|
| Imagen de Redis | `redis:7-alpine` | `redis:7.2-alpine` o `valkey/valkey:8-alpine` | Docker Hub: `7-alpine` y `7.4-alpine` tienen el mismo *digest* `sha256:858f009f…`; `redis/redis@7.4/LICENSE.txt` dice RSALv2/SSPLv1; `@7.2/COPYING` es BSD; `valkey-io/valkey@8.1/COPYING` es BSD-3 [verificado] |
| `weknora.env` | solo secretos | añadir `REDIS_PASSWORD`, `STREAM_MANAGER_TYPE`, `JWT_SECRET`, `SYSTEM_AES_KEY`, `LANGFUSE_ENABLED=false`, `SSRF_WHITELIST`, `WEKNORA_LANGUAGE`, `DISABLE_REGISTRATION` | §1.4 |
| `depends_on` de docreader | `service_started` | `service_healthy` y su `healthcheck`, como el original | `docker-compose.yml:385-386, 500-505` |
| initdb | rol y BD | más las extensiones | §1.6 |
| `weknora-ui` | sin idioma | `DEFAULT_LOCALE: en-US` (no hay castellano) | `frontend/src/i18n/locales/` solo trae zh-CN, en-US, ru-RU, ko-KR y ja-JP |

---

## 2. Primer arranque

Base de la API: `http://weknora:8080/api/v1` desde el gateway, o `http://127.0.0.1:18702/api/v1` por túnel con `compose.debug.yml`. La especificación Swagger tiene `basePath: /api/v1` (`docs/swagger.yaml:1`).

### 2.1 Administrador, espacio y cierre del registro

No hay usuario ni espacio sembrados por las migraciones (solo agentes integrados: `000006_custom_agents.up.sql:79, 127`) [verificado]. Flujo:

```sh
WK=http://127.0.0.1:18702/api/v1

# 1) Registro (público mientras registration_mode = self_serve). Respuesta 201.
curl -s -X POST "$WK/auth/register" -H 'Content-Type: application/json' \
  -d '{"username":"admin","email":"admin@cidia.example","password":"<contraseña>"}'
# → {"success":true,"message":"Registration successful","user":{"id":"…","tenant_id":<N>,…}}

# 2) Login. Respuesta 200.
curl -s -X POST "$WK/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"admin@cidia.example","password":"<contraseña>"}'
# → {"success":true,"user":{…},"active_tenant":{"id":<N>,…},"memberships":[{"tenant_id":<N>,"role":"owner",…}],
#    "token":"<JWT>","refresh_token":"<…>"}
```

* El registro crea un espacio personal («`<usuario>`'s Workspace») y hace al usuario su Owner: `internal/application/service/user.go:167-177, 214-219` [verificado].
* Los cuerpos de petición son `RegisterRequest {username, email, password}` y `LoginRequest {email, password}` (`internal/types/user.go:144-147, 191-201`). La respuesta del login es `AuthLoginResponse` (`internal/handler/dto/auth.go:6-14`) [verificado].
* **Administrador de sistema**: con `WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL` se promociona ese usuario **en el siguiente arranque**, y solo si aún no hay ningún administrador de sistema (`cmd/server/bootstrap.go:33, 79-115`). Por tanto: registrar y luego `docker compose restart weknora`. Para el gateway no hace falta ser administrador de sistema: basta con ser Owner del espacio [verificado].
* **Cerrar el registro**: `DISABLE_REGISTRATION=true` y reiniciar. Al arrancar equivale a `auth.registration_mode=invite_only` (`internal/handler/auth.go:184-195`) [verificado].

### 2.2 API key del gateway (solo con JWT)

`POST /tenants/:id/api-keys` se registra **sin** política de API key (`internal/router/routes_auth_tenant.go:97-100`), así que solo funciona con JWT de Owner. El *gate* deniega toda ruta no declarada (`internal/middleware/api_key_gate.go:128-153`) [verificado].

```sh
curl -s -X POST "$WK/tenants/<N>/api-keys" \
  -H "Authorization: Bearer <JWT>" -H 'Content-Type: application/json' \
  -d '{"name":"cidia-gateway","full_access":true}'
# 201 → {"success":true,"data":{"id":1,"scope_type":"…","name":"cidia-gateway","api_key":"sk-…",
#        "full_access":true,"knowledge_base_ids":[],"capabilities":[],"created_at":"…","token":"sk-…"}}
```

* Cuerpo: `{name, full_access, knowledge_base_ids[], capabilities[], expires_at_unix}` (`internal/handler/tenant.go:138-171`).
* El token tiene la forma `sk-` + 32 bytes aleatorios en base64url. En la BD se guarda su SHA-256 (`internal/application/service/tenant_api_key.go:208-219`).
* Una key sin `full_access` necesita al menos una capacidad (`tenant.go:802-827`).
* Hay que guardar el token en el fichero de secretos del gateway en el momento de crearlo [verificado].

Configuración de identidad para la memoria por usuario (§3.3), también solo con JWT de Owner:

```sh
curl -s -X PUT "$WK/tenants/<N>/api-principal-config" \
  -H "Authorization: Bearer <JWT>" -H 'Content-Type: application/json' \
  -d '{"mode":"direct_header","require_direct_header":false}'
```

Modos posibles: `tenant` (por defecto), `direct_header` y `signed_token` (`internal/types/tenant.go:197-217`, `internal/handler/tenant.go:933-990`). El nombre de cabecera está fijo en `X-External-User-ID` (`internal/middleware/auth.go:22-27`, `internal/handler/tenant.go:173-176`) [verificado].

### 2.3 Modelos por API

`POST /models` admite `manage_models` o `full_access` (`internal/router/routes_infra.go:21-43`). Cuerpo `CreateModelRequest` (`internal/handler/model.go:47-54`):

```json
{ "name": "…", "display_name": "…", "type": "KnowledgeQA|Embedding|Rerank|VLLM|ASR",
  "source": "local|remote", "description": "…", "parameters": { … } }
```

Los tipos están en `internal/types/model.go:18-22` y los parámetros en `model.go:118-160` (`base_url`, `api_key`, `provider`, `embedding_parameters{dimension, truncate_prompt_tokens, supports_dimension_override}`, `extra_config`, `custom_headers`, `context_window`, `max_output_tokens`, `max_concurrency`, `supports_vision`) [verificado]. Respuesta 201 `{"success":true,"data":ModelResponse}` con `id` y `status` (`internal/handler/dto/model.go:179-199`).

Ejemplos (los nombres de etiqueta de Ollama son [inferencia]: comprobar con `ollama list`):

```json
// LLM en Ollama (MSI: Ministral 3 8B; en Oracle, uno muy pequeño)
{"name":"ministral-3:8b","display_name":"Ministral 3 8B","type":"KnowledgeQA","source":"local",
 "parameters":{"context_window":8192}}

// Embedding en Ollama (Qwen3-Embedding 0.6B → 1024 dimensiones → colección weknora_embeddings_1024)
{"name":"qwen3-embedding:0.6b","type":"Embedding","source":"local",
 "parameters":{"embedding_parameters":{"dimension":1024,"truncate_prompt_tokens":2048}}}

// Rerank servido por el gateway (formato Cohere)
{"name":"qwen3-reranker-0.6b","type":"Rerank","source":"remote",
 "parameters":{"base_url":"http://gateway:8000/v1","api_key":"<token interno>","provider":"generic",
               "extra_config":{"score_scale":"logit"}}}

// ASR con speaches
{"name":"Systran/faster-whisper-small","type":"ASR","source":"remote",
 "parameters":{"base_url":"http://asr:8000/v1","provider":"generic"}}
```

Los comentarios `//` son solo para leer: el JSON real no los admite.

* **`source: local` lanza una descarga** en Ollama si el modelo no existe. El registro queda en `status: "downloading"` hasta que termina (`internal/application/service/model.go:121-150`). Si ya está descargado no sale a Internet (`internal/models/utils/ollama/ollama.go:150-158`) [verificado]. Mientras no esté en `active`, `GetModelByID` falla, así que hay que consultar `GET /models/{id}` hasta ver `"status":"active"`.
* Si `truncate_prompt_tokens` es 0, el embedder de Ollama usa `num_ctx=511` (`internal/models/embedding/ollama.go:49-50`). Por eso propongo 2048 [verificado; el valor es recomendación].

Endpoints de comprobación (`internal/router/routes_infra.go:112-124`). Todos aceptan `ModelTestRequest` (`internal/handler/initialization.go:1765-1788`: `source`, `modelName`, `baseUrl`, `apiKey`, `provider`, `dimension`, `customHeaders`, `extraConfig`, `modelId`) y responden `{"success":true,"data":{"available":bool,"message":"…"}}`:

| Endpoint | Uso |
|---|---|
| `GET /initialization/ollama/status` | ¿Responde `OLLAMA_BASE_URL`? |
| `GET /initialization/ollama/models` | Modelos presentes en Ollama |
| `POST /initialization/remote/check` | Chat remoto (exige `modelName` y `baseUrl`) |
| `POST /initialization/embedding/test` | Embedding; además devuelve `data.dimension` (`initialization.go:1974-2048`) |
| `POST /initialization/rerank/check` | Rerank |
| `POST /initialization/asr/check` | ASR: envía un WAV de silencio a `/audio/transcriptions` (`initialization.go:2206-2289`) |

Asignación a una base de conocimiento: directamente al crearla (`embedding_model_id`, `summary_model_id`, `asr_config`, `vlm_config`; §4.1). La alternativa `PUT /initialization/config/{kbId}` exige `llmModelId` y no deja cambiar el modelo de embedding si la base ya tiene documentos (`initialization.go:98-149, 263-276`) [verificado].

### 2.4 Configuración del espacio: recuperación y memoria

`GET|PUT /tenants/kv/{key}` (`routes_auth_tenant.go:80-81`; PUT exige Admin o una key `full_access`/`manage_tenant_settings`).

```sh
# Recuperación: número de resultados, umbrales, reranker y pesos de RRF
curl -s -X PUT "$WK/tenants/kv/retrieval-config" -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"embedding_top_k":50,"vector_threshold":0.15,"keyword_threshold":0.3,
       "rerank_top_k":20,"rerank_threshold":0.2,"rerank_model_id":"<id rerank>",
       "rrf_k":60,"rrf_vector_weight":0.7,"rrf_keyword_weight":0.3}'

# Memoria (interruptor del espacio; por defecto está apagada)
curl -s -X PUT "$WK/tenants/kv/memory-config" -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"enabled":true,"write_mode":"explicit_only","embedding_model_id":"<id embedding>","max_items":200}'
```

* `RetrievalConfig`: `internal/types/retrieval_config.go:14-38`. Valores por defecto: 50, 0,15, 0,3, 10, 0,2, RRF 60 y 0,7/0,3 (`retrieval_config.go:44-108`). Límites: `top_k` entre 0 y 200 y `rerank_threshold` entre −10 y 10 (`internal/handler/tenant.go:1752-1791`) [verificado].
* `MemoryConfig`: `internal/types/memory.go:333-380`. Validaciones en `tenant.go:1832-1878` [verificado].

---

## 3. Autenticación y alcance

### 3.1 Canales

El middleware `Auth` (`internal/middleware/auth.go:126-181`) prueba en este orden [verificado]:

1. **Rutas públicas** (`auth.go:36-63`): `/health`, `/api/v1/auth/{register,login,refresh,config,oidc/*,…}` y `/api/v1/files/presigned`.
2. **`Authorization: Bearer <JWT>`**: el espacio sale de `X-Tenant-ID`, de la reclamación del JWT o de la primera membresía (`auth.go:284-338`). El rol se toma de la membresía activa.
3. **`X-API-Key: sk-…`**: si el JWT es inválido y hay key, se usa la key (`auth.go:160-171`).

Ojo: los errores de autenticación tienen la forma `{"error":"…"}` (`auth.go:173-179`). Los de los *handlers* tienen otra: `{"success":false,"error":{"code","message","details"}}` (`internal/middleware/error_handler.go:25-43`).

### 3.2 Alcance de una API key

* **Key de espacio**: queda fija a su espacio. Si se envía `X-Tenant-ID` con otro valor → 403 (`auth.go:409-431`). Con `full_access` actúa como Owner; sin él, como Viewer más sus capacidades (`auth.go:535-560`).
* **Key de plataforma** (`/system/admin/api-keys`, solo administrador de sistema): exige `X-Tenant-ID` (`auth.go:388-408`).
* **Gate por ruta** (`api_key_gate.go:111-153`): ruta sin política → 403 `"Forbidden: API key scope does not allow this operation"`. Las capacidades son de tipo «cualquiera de» y están en `internal/types/tenant_api_key.go:78-164` (`retrieve`, `chat`, `ingest`, `manage_kbs`, `manage_models`, `manage_tenant_settings`…).
* **Lista de bases permitidas** (`knowledge_base_ids`): se aplica después del gate, en `KBAccess*` y en los *handlers* (p. ej. `types.AuthorizeTenantAPIKeyKnowledgeTargets` en `internal/handler/session/qa.go:886-889`) [verificado].

Política de las rutas que usará el gateway [verificado en `internal/router/`]:

| Operación | Ruta | La key necesita |
|---|---|---|
| Crear, editar o borrar una base | `POST/PUT/DELETE /knowledge-bases[/:id]` | `manage_kbs` o `full_access` (`routes_knowledge.go:199-221`) |
| Etiquetas (escribir / leer) | `/knowledge-bases/:id/tags` | `ingest` / `retrieve` (`routes_knowledge.go:276-287`) |
| Subir fichero, URL o texto manual | `/knowledge-bases/:id/knowledge/{file,url,manual}` | `ingest` (`routes_knowledge.go:70-75`) |
| Listar y consultar el estado | `GET /knowledge-bases/:id/knowledge`, `GET /knowledge/:id`, `GET /knowledge/batch` | `retrieve` (`routes_knowledge.go:71-79, 89-107`) |
| Borrar conocimiento | `DELETE /knowledge/:id`, `POST /knowledge/batch-delete` | `ingest` (`routes_knowledge.go:108, 132`) |
| Buscar | `POST /knowledge-search`, `POST /knowledge-bases/:id/hybrid-search` | `retrieve` (`routes_chat.go:148-151`, `routes_knowledge.go:232`) |
| FAQ (escribir / buscar) | `/knowledge-bases/:id/faq/*` | `ingest` / `retrieve` (`routes_knowledge.go:151-181`) |
| Memoria | `/memory/*` | **solo `full_access`** (`routes_memory.go:21`) |
| Modelos | `/models/*`, `/initialization/*` | `manage_models` (`routes_infra.go:21, 112-128`) |
| Crear API keys y fijar el modo de identidad | `/tenants/:id/api-keys`, `/api-principal-config` | **solo JWT de Owner** (`routes_auth_tenant.go:97-103`) |

### 3.3 Identidad del usuario final (memoria)

* La memoria se guarda por `(tenant_id, Principal.StorageID())`. No hay ningún parámetro de usuario en las rutas (`internal/application/service/memory/scope.go:28-42`, `internal/router/routes_memory.go:9-16`) [verificado].
* Con una API key en modo `tenant`, el *principal* es el propio espacio, así que **todos los usuarios compartirían una sola memoria** (`auth.go:563-578`) [verificado].
* Con `direct_header`, cada petición del gateway debe llevar `X-External-User-ID: <id de usuario CidIA>` (como máximo 128 caracteres y sin caracteres de control: `auth.go:580-594, 661-675`).
* Es de **baja garantía**: quien tenga la key puede hacerse pasar por cualquier usuario (`internal/types/tenant.go:205-207`). Es aceptable porque la key solo la tiene el gateway. `signed_token` (JWT HS256 con `aud=weknora`, `tenant_id`, `sub` y una validez máxima de 24 h; `auth.go:613-659`) es la opción robusta.

### 3.4 Modelo de alcance propuesto para CidIA

Coincide con `docs/arquitectura.md` §3:

* **Un único espacio** «CidIA <empresa>» y **una key `full_access`** solo en el gateway. El gateway calcula los permisos (departamento, nivel, formación) y decide `knowledge_base_ids` y las etiquetas de cada búsqueda.
* **Defensa en profundidad** (opcional): una key por departamento con `capabilities:["retrieve"]` y `knowledge_base_ids:[<base del dpto>, <Público>]`. Así, un error del gateway no puede leer otro departamento [verificado que la lista se aplica en la búsqueda: `qa.go:886`].
* Los usuarios de CidIA **no** se crean en WeKnora. Solo el administrador técnico tiene cuenta, para la consola.

---

## 4. Endpoints con esquema exacto

Todas las respuestas correctas llevan `"success":true`. Para el gateway, la cabecera común es `X-API-Key: sk-…` más, cuando aplique, `X-External-User-ID`.

### 4.1 Crear una base de conocimiento

`POST /knowledge-bases` (`internal/handler/knowledgebase.go:395-449`). El cuerpo es `types.KnowledgeBase` (`internal/types/knowledgebase.go:59-156`); los campos útiles coinciden con los que envía la UI (`frontend/src/api/knowledge-base/index.ts:86-132`):

```json
{
  "name": "Mantenimiento",
  "description": "Base del departamento de mantenimiento (datos sintéticos)",
  "type": "document",
  "embedding_model_id": "<id embedding>",
  "summary_model_id": "<id LLM, opcional>",
  "chunking_config": { "chunk_size": 512, "chunk_overlap": 50, "separators": ["\n\n", "\n", ". "] },
  "indexing_strategy": { "vector_enabled": true, "keyword_enabled": true, "wiki_enabled": false, "graph_enabled": false },
  "vlm_config": { "enabled": false },
  "asr_config": { "enabled": false }
}
```

Respuesta 201: `{"success":true,"data":{"id":"<uuid>","name":…,"type":"document","tenant_id":<N>,"embedding_model_id":…,…}}` (`knowledgebase.go:445-448`).

* `type`: `document` (por defecto), `faq` o `wiki` (`knowledgebase.go:31-36`). Para FAQ se añade `"faq_config":{"index_mode":"question_answer","question_index_mode":"combined"}`; esos son los valores por defecto (`knowledgebase.go:755-769`).
* `chunking_config` admite además `enable_parent_child`, `parent_chunk_size`, `child_chunk_size`, `strategy` (`auto|heading|heuristic|recursive`), `token_limit` y `languages` (`knowledgebase.go:253-292`).
* `indexing_strategy` por defecto: vector y palabra clave activados (`internal/types/indexing_strategy.go:22-27`).
* `asr_config = {enabled, model_id, language}` (`knowledgebase.go:656-660`) sirve para transcribir audio y vídeo subidos a esa base.
* Una key `full_access` crea la base sin `creator_id`: la base pertenece al espacio (`internal/application/service/knowledgebase.go:131-141`).
* Si se omite `summary_model_id`, el resumen del documento se salta y queda `summary_status=failed`, pero el documento se indexa igual (`internal/application/service/knowledge_process.go:1290-1294`) [verificado].

### 4.2 Etiquetas

`POST /knowledge-bases/{kb}/tags` (`internal/handler/tag.go:113-157`):

```json
{ "name": "n1", "color": "#1f6feb", "sort_order": 1 }
```

Respuesta 200: `{"success":true,"data":{"id":"<uuid>","seq_id":<int64>,"tenant_id":…,"knowledge_base_id":…,"name":"n1","color":…,"sort_order":1,"created_at":…,"updated_at":…}}` (`internal/types/tag.go:12-31`).

* Listado: `GET /knowledge-bases/{kb}/tags?page=1&page_size=100&keyword=` → `data` es un `PageResult {total, page, page_size, data:[KnowledgeTag]}` (`tag.go:87-111`, `internal/types/search.go:272-314`).
* **Hay dos identificadores**: los documentos y `/knowledge-search` usan el `id` UUID; las FAQ usan el `seq_id` entero (§4.7).

### 4.3 Subir conocimiento desde fichero

`POST /knowledge-bases/{kb}/knowledge/file`, `multipart/form-data` (`internal/handler/knowledge.go:276-428`):

| Campo | Tipo | Notas |
|---|---|---|
| `file` | fichero | Obligatorio; como máximo `MAX_FILE_SIZE_MB` (`knowledge.go:317-341`) |
| `fileName` | texto | Nombre que se muestra (opcional) |
| `tag_ids` | texto | UUID separados por comas; se ignora `__untagged__` (`knowledge.go:2761-2775`) |
| `metadata` | texto JSON | `map[string]string` |
| `enable_multimodel` | `true`/`false` | Opcional |
| `process_config` | texto JSON | `KnowledgeProcessOverrides` (opcional) |
| `channel` | texto | Por defecto `web`; el gateway debería enviar `api` (`internal/application/service/knowledge.go:513-518`) |

```sh
curl -s -X POST "$WK/knowledge-bases/<kb>/knowledge/file" -H "X-API-Key: $KEY" \
  -F "file=@procedimiento_sintetico.pdf" -F "tag_ids=<uuid n1>,<uuid formacion>" \
  -F 'metadata={"origen":"sintetico"}' -F "channel=api"
```

* Respuesta 200: `{"success":true,"data":Knowledge}` (`knowledge.go:424-427`). La estructura `Knowledge` está en `internal/types/knowledge.go` (≈166-250): `id`, `knowledge_base_id`, `title`, `parse_status`, `summary_status`, `enable_status`, `file_name`, `file_type`, `file_size`, `file_hash`, `tags[]`, `error_message`, `created_at`, `processed_at`…
* Si el fichero ya existe → 409 `{"success":false,"message":…,"data":<conocimiento existente>,"code":"duplicate_file"}` (`knowledge.go:208-224`).

### 4.4 Crear conocimiento desde texto

`POST /knowledge-bases/{kb}/knowledge/manual` con `ManualKnowledgePayload` (`internal/types/knowledge.go:327-334`):

```json
{ "title": "Cambio de rodamiento (sintético)", "content": "# Pasos\n1. …", "status": "publish",
  "tag_ids": ["<uuid n2>"], "channel": "api" }
```

* **`status` es por defecto `draft`, y un borrador NO se indexa**: queda con `enable_status: "disabled"`. Hay que enviar `"publish"` (`internal/application/service/knowledge_create.go:757-809`).
* Contenido máximo: 200 000 caracteres (`internal/application/service/knowledge.go:88`).
* Respuesta 200: `{"success":true,"data":Knowledge}` con `parse_status:"pending"`.
* Para editarlo: `PUT /knowledge/manual/{id}` [verificado].

### 4.5 Listar, consultar el estado y borrar

* **Listar**: `GET /knowledge-bases/{kb}/knowledge?page=1&page_size=50&tag_ids=<a>,<b>&parse_status=failed&keyword=&sort_by=created_at&sort_order=desc` → `{"success":true,"data":[Knowledge],"total":N,"page":1,"page_size":50}` (`knowledge.go:966-1105`). `page_size` llega como máximo a 1000 (`search.go:276`).
* **Estado de uno**: `GET /knowledge/{id}` → `data.parse_status` (`knowledge.go:587-647`). Valores (`internal/types/knowledge.go:42-71`):
  * `pending` y `processing`;
  * `finalizing`: ya se puede buscar por vector, pero quedan resúmenes o preguntas por generar;
  * `completed`;
  * `failed` (ver `error_message`);
  * `cancelled` y `deleting`.
* **Estado de varios**: `GET /knowledge/batch?ids=<a>&ids=<b>[&kb_id=<kb>]` (`knowledge.go:1682-1720`).
* **Detalle por etapas**: `GET /knowledge/{id}/stages` (5 etapas, `knowledge.go:649+`).
* **Borrar uno**: `DELETE /knowledge/{id}` → `{"success":true,"message":"Delete task submitted","data":{"task_id":"…"}}`. El borrado es **asíncrono** (`knowledge.go:1352-1414`).
* **Borrar varios**: `POST /knowledge/batch-delete {"kb_id":"…","ids":["…"]}` (`knowledge.go:1416-1435`).
* **Vaciar una base**: `DELETE /knowledge-bases/{kb}/knowledge` (solo `full_access`, `routes_knowledge.go:83`).

### 4.6 Búsqueda: `POST /knowledge-search`

Petición `SearchKnowledgeRequest` (`internal/handler/session/types.go:83-90`; coincide con `docs/swagger.yaml:6538-6568`):

```json
{
  "query": "¿Qué par de apriete lleva la brida B-12?",
  "knowledge_base_ids": ["<kb Público>"],
  "knowledge_ids": [],
  "tag_ids": [],
  "mentioned_items": [
    { "type": "tag", "id": "<uuid n1>", "kb_id": "<kb Mantenimiento>" },
    { "type": "tag", "id": "<uuid n2>", "kb_id": "<kb Mantenimiento>" }
  ]
}
```

Reglas [verificado]:

* Hace falta al menos una base, un documento o una etiqueta con ámbito (`qa.go:881-885`).
* **No existe un campo de número de resultados.** Los umbrales y el `top_k` salen de `RetrievalConfig` del espacio. El número final es `rerank_top_k`, 10 por defecto (`internal/application/service/session_knowledge_qa.go:858-881`; `internal/application/service/chat_pipeline/filter_top_k.go:53-58`). El gateway puede recortar más.
* `tag_ids` sueltos solo valen con **exactamente una** base; para varias bases hay que usar `mentioned_items` con `kb_id` (`internal/handler/session/helpers.go:123-153`).
* Si una base tiene etiquetas en el ámbito, **se busca solo en lo etiquetado**, aunque también aparezca en `knowledge_base_ids` (`session_knowledge_qa.go:515-530`). Las etiquetas se combinan con O: el documento entra si tiene cualquiera de ellas (`internal/types/search.go:37-38`). Los documentos sin etiqueta quedan fuera de ese ámbito, así que **todo documento debe llevar su etiqueta de nivel**.
* Fases: búsqueda (vector + palabra clave por base) → rerank (se salta si no hay modelo de rerank: `chat_pipeline/rerank.go:57-62`; se usa `rerank_model_id` o, si falta, el primer modelo Rerank del espacio: `session_knowledge_qa.go:893-906`) → fusión de fragmentos → top K. No llama al LLM (`session_knowledge_qa.go:908-914`).

Respuesta 200: `{"success":true,"data":[SearchResult]}` (`internal/types/search.go:150-227`). Campos útiles:

| Campo | Contenido |
|---|---|
| `id` | id del fragmento (*chunk*) |
| `content` | texto del fragmento, ampliado con el padre o los vecinos si procede |
| `score` | puntuación final (de rerank si hubo rerank; si no, de la fusión) |
| `knowledge_id`, `knowledge_title`, `knowledge_filename` | documento de origen |
| `knowledge_base_id` | base |
| `chunk_index`, `start_at`, `end_at`, `seq` | posición |
| `match_type` | **entero**: 0 vector, 1 palabra clave, 2 fragmento vecino, 4 padre, 5 relación… (`internal/types/embedding.go:13-26`) |
| `metadata`, `chunk_metadata`, `image_info`, `matched_content` (FAQ), `knowledge_description` | extras |

`SearchResult` no trae las etiquetas. Si el gateway las necesita para volver a filtrar, las obtiene con `GET /knowledge/batch?ids=…` (`data[].tags`).

**Alternativa con `match_count` por petición**: `POST /knowledge-bases/{kb}/hybrid-search` con `SearchParams` (`internal/types/search.go:230-252`): `query_text`, `match_count` (0 → 50), `vector_threshold`, `keyword_threshold`, `disable_keywords_match`, `disable_vector_match`, `knowledge_ids`, `tag_ids`, `knowledge_base_ids` (varias bases con el mismo modelo de embedding). Devuelve `[SearchResult]` **sin rerank** (`internal/handler/knowledgebase.go:321-381`; `internal/application/service/knowledgebase_search.go:131, 296-297, 317-322`).

### 4.7 FAQ

En WeKnora las FAQ viven en una base de tipo `faq` (§4.1).

* **Crear una entrada (síncrono)**: `POST /knowledge-bases/{kbFaq}/faq/entry` con `FAQEntryPayload` (`internal/types/faq.go:302-314`; *handler* en `internal/handler/faq.go:186-221`):

  ```json
  { "standard_question": "¿Cada cuánto se engrasa el husillo?",
    "similar_questions": ["frecuencia de engrase del husillo"],
    "negative_questions": [],
    "answers": ["Cada 40 horas de uso (dato sintético)."],
    "answer_strategy": "all",
    "tag_name": "n1",
    "is_enabled": true }
  ```

  * **Una sola etiqueta por entrada**: `tag_id` (el `seq_id` entero) o `tag_name`, que se crea si no existe. Si no se da ninguna, se usa «未分类» (`internal/application/service/knowledge_faq.go:1828-1858`).
  * Respuesta 200: `data = FAQEntry {id (seq_id), chunk_id, knowledge_id, knowledge_base_id, tag_id (seq_id), tag_name, is_enabled, is_recommended, standard_question, similar_questions, negative_questions, answers, answer_strategy, index_mode, created_at, updated_at}` (`internal/types/faq.go:261-284`).
  * El indexado tiene un margen de 5 s (`internal/application/service/knowledge_faq.go:112`).
* **Importar en bloque (asíncrono)**: `POST …/faq/entries {"entries":[…],"mode":"append|replace","dry_run":false}` → progreso en `GET /faq/import/progress/{task_id}` (`internal/types/faq.go:322-328`).
* **Buscar**: `POST /knowledge-bases/{kbFaq}/faq/search` con `FAQSearchRequest` (`internal/types/faq.go:376-383`):

  ```json
  { "query_text": "engrase husillo", "match_count": 5, "vector_threshold": 0.5,
    "first_priority_tag_ids": [12], "second_priority_tag_ids": [], "only_recommended": false }
  ```

  Aquí `12` es el `seq_id` de la etiqueta `n1`. `match_count` toma 10 por defecto y como máximo 200. Respuesta: `data = [FAQEntry]` con `score`, `match_type` y `matched_question` (`internal/handler/faq.go:368-409`).
* **Listar, editar y borrar**: `GET …/faq/entries?page&page_size&tag_ids&keyword`, `PUT …/faq/entries/{seq_id}`, `DELETE …/faq/entries {"ids":[seq_id…]}` (`internal/router/routes_knowledge.go:157-167`).
* Una base FAQ también se puede incluir en `knowledge_base_ids` de `/knowledge-search`, que fusiona sus resultados (`chat_pipeline/merge_faq.go`) [inferencia sobre el resultado exacto].

### 4.8 Memoria de usuario

Todas las rutas exigen key `full_access` y la cabecera `X-External-User-ID` (§3.3). Están en `internal/handler/memory.go`:

| Acción | Petición | Respuesta |
|---|---|---|
| Consultar el estado | `GET /memory/settings` | `data = {workspace_enabled, user_enabled, effective, write_mode, item_count, max_items}` (`internal/types/memory.go:975-990`) |
| Activar o desactivar para el usuario | `PUT /memory/settings {"enabled":true\|false}` (`internal/handler/memory.go:49-84`) | ajustes actualizados |
| Listar | `GET /memory/items?status=active&limit=50&offset=0` (`internal/handler/memory.go:86-119`) | `{"success":true,"data":[MemoryItem],"total":N}`; `MemoryItem` = `id, kind, content, topic, importance, origin, status, valid_from…` (`internal/types/memory.go:288-311`) |
| Crear a mano | `POST /memory/items {"kind":"preference","content":"…","importance":3}` (`internal/handler/memory.go:246-275`) | `data = MemoryItem` |
| Borrar una | `DELETE /memory/items/{id}` (`internal/handler/memory.go:308-324`) | `{"success":true}` |
| Borrar todas | `DELETE /memory/items` (`internal/handler/memory.go:373-381`) | `{"success":true,"removed":N}` |
| Exportar | `GET /memory/export` | — |

* Los tipos (`kind`) son `profile`, `preference`, `fact`, `task` e `interest` (`internal/types/memory.go:25-34`).
* **«Opt-in» exige trabajo del gateway**: el interruptor del espacio está apagado por defecto (`internal/types/memory.go:334-336`), pero el del usuario **vale `true` si no existe registro** (`internal/application/service/memory/service.go:887-916`). Para que la memoria sea opt-in por persona, el gateway debe enviar `PUT /memory/settings {"enabled":false}` al dar de alta a cada usuario, o no activar nunca el interruptor del espacio y gestionar el consentimiento él mismo [verificado].
* **La extracción automática solo se dispara desde el chat de WeKnora** (`/knowledge-chat` y `/agent-chat`: `internal/handler/session/qa.go:1945`). Como nuestro agente vive en la app y el gateway, la memoria de WeKnora solo se llena con `POST /memory/items` [verificado]. No hay endpoint de búsqueda semántica en la memoria; solo listado y exportación (`internal/router/routes_memory.go:21-39`).

---

## 5. Imágenes arm64

### 5.1 Docker Hub (consulta del 9-10-2026)

[verificado con `https://hub.docker.com/v2/repositories/<repo>/tags`]

| Imagen | Etiqueta | Arquitecturas | Tamaño comprimido amd64 / arm64 |
|---|---|---|---|
| `wechatopenai/weknora-app` | `v0.8.2` (24-09-2026) | amd64, arm64 | 579 / 546 MB |
| `wechatopenai/weknora-ui` | `v0.8.2` | amd64, arm64 | 32 / 32 MB |
| `wechatopenai/weknora-docreader` | `v0.8.2` | amd64, arm64 | 1580 / 1520 MB |
| `wechatopenai/weknora-sandbox` | `v0.8.2-desktop` | amd64, arm64 (la variante `-desktop-cube` solo amd64) | no la usamos |
| `pgvector/pgvector` | `0.8.7-pg17` (01-10-2026) | amd64, arm64 | — |
| `qdrant/qdrant` | `v1.16.2` | amd64, arm64 | — |
| `redis` | `7.2-alpine` | amd64, arm64/v8 y otras | — |
| `valkey/valkey` | `8-alpine`, `8.1-alpine` | amd64, arm64 y otras | — |

Las versiones anteriores de WeKnora (v0.6.3 a v0.8.0) también publican arm64.

### 5.2 Servidor Oracle

[verificado con órdenes de solo lectura]

* `aarch64`, Neoverse-N1, Ubuntu 20.04.6, núcleo 5.15.0-1081-oracle, **páginas de 4 KiB**: Qdrant y jemalloc no tienen el problema de las páginas de 64 KiB. Docker 26.1.3, Compose v2.35.1, cgroup v1, 23 GiB de RAM (19 GiB disponibles) y 112 GB libres en disco.
* Puertos ocupados: 22, 53, 80, 111, 443, 631, 3000, 4001, 4002, 4005, 4010, 5678, 8000, 8090-8092, 8096 y 38791.
* No existen contenedores `WeKnora-*`. `/home/ubuntu/CidIA` está vacío.

### 5.3 Compilar en ARM si hiciera falta

No hace falta. Si alguna vez hubiera que hacerlo:

* `docker/Dockerfile.app` es multiplataforma (`FROM --platform=$TARGETPLATFORM`). `WITH_ANYDOC=1` (por defecto) compila `anydoc` en Rust; con `WITH_ANYDOC=0` la compilación es más corta, pero se pierde el analizador en el propio proceso (`Dockerfile.app:63-81`).
* `docker/Dockerfile.docreader:30-40` reconoce `aarch64`.
* Compilarlo en los 4 núcleos Ampere es viable; no he medido el tiempo [inferencia].

---

## 6. Llamadas salientes y telemetría

Búsquedas hechas en `internal/`, `cmd/`, `frontend/src`, `frontend/index.html`, `docreader/` y `mcp-server/`: SDK de analítica (posthog, sentry, segment, mixpanel, amplitude, gtag, umami…), comprobación de actualizaciones y URL de terceros fijas en el código.

| Origen | ¿Por defecto? | Detalle | Fuente |
|---|---|---|---|
| Analítica o telemetría | **No hay** | Ningún SDK en el backend ni en la UI | búsqueda sin resultados [verificado] |
| Comprobar actualizaciones | No en el servidor | `cmd/desktop/update.go` es solo de la edición de escritorio, no del binario `cmd/server` | [verificado] |
| **Langfuse** | **Sí, si se copia `.env.example`** | Se activa solo cuando hay `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` (`internal/tracing/langfuse/config.go:79-84`). `.env.example:692-694` trae `pk-lf-xxxxxxxx` y `sk-lf-xxxxxxxx` con `LANGFUSE_HOST=http://langfuse-web:3000`. Si se borra el host, el valor por defecto es `https://cloud.langfuse.com` (`config.go:67`). Las trazas incluyen *prompts* y respuestas. **Poner `LANGFUSE_ENABLED=false`.** | [verificado] |
| Iconos de la UI (tdesign) | No | Se cargan en local para no pedir a `tdesign.gtimg.com` (`frontend/index.html:59-64`, `frontend/src/utils/tdesign-icon-offline.ts`) | [verificado] |
| Descarga de modelos de Ollama | Solo si se crea un modelo `local` que no existe | La hace Ollama (registry.ollama.ai), no WeKnora | `internal/application/service/model.go:121-150` [verificado] |
| Proveedores de modelos remotos | Solo los configurados | — | — |
| Búsqueda web (DuckDuckGo, Bing, Tavily…) | Solo si se crea un proveedor y el agente la tiene activa | DuckDuckGo no necesita clave; solo se usa desde el chat de WeKnora | `internal/infrastructure/web_search/*`, `service/web_search_provider.go:131-145` [verificado] |
| Importar URL y navegador (playwright) | Solo bajo demanda | `POST …/knowledge/url` con validación SSRF | `internal/handler/knowledge.go:485-490` [verificado] |
| Skills (clawhub.ai, GitHub) | Solo al instalar una skill | `service/tenant_skill_source.go:27` | [verificado] |
| Canales de mensajería, fuentes de datos (Feishu, Notion, GitLab…), MinerU o PaddleOCR en la nube, WeKnoraCloud, OIDC | Solo si se configuran | `internal/im/*`, `internal/datasource/*`, `internal/infrastructure/docparser/*` | [verificado] |

**Medidas para CidIA**:

1. `weknora`, `docreader`, `qdrant`, `redis` y `postgres` solo en la red `cidia-interna` (`internal: true`), sin salida a Internet.
2. `LANGFUSE_ENABLED=false`.
3. `SSRF_WHITELIST` con solo los nombres internos necesarios.
4. Opcional: `SSRF_DNS_WHITELIST_ONLY=true`. Hace que todo nombre fuera de la lista se rechace antes de consultar el DNS (`security.go:1336-1340`). Con la red `internal` ya no aporta mucho [inferencia].

---

## 7. Riesgos técnicos y de licencia

### 7.1 Palabras clave con Qdrant (afecta a la calidad en castellano)

* Qdrant crea un índice de texto *multilingual* en minúsculas (`internal/application/repository/retriever/qdrant/repository.go:194-209`).
* La búsqueda por palabras clave es un `Scroll` con un filtro `Should` por cada palabra de la consulta y **puntuación fija 1,0**, sin BM25 (`repository.go:747-841`). El propio servicio lo reconoce: «engines that stamp keyword hits at 1.0 (Qdrant, Doris)» (`internal/application/service/knowledgebase_search_fusion.go:83-93`).
* La consulta se trocea con jieba y solo se descartan las palabras de menos de 2 caracteres (`repository.go:1113-1136`). En castellano, «de», «la» o «que» casan con casi cualquier fragmento, así que la lista de palabras clave sale en un orden arbitrario y la fusión RRF con pesos 0,7/0,3 mete ruido [verificado el código; el efecto es inferencia].
* Hay una colección por dimensión y es común a todos los espacios (`weknora_embeddings_1024`); el filtro es por `knowledge_base_id` (`repository.go:54-56, 617-653`).

Recomendación, por orden:

1. Configurar siempre un reranker (§1.5).
2. Medir con y sin `keyword_enabled` en cada base, usando el conjunto sintético de preguntas.
3. Si las palabras clave empeoran el resultado, desactivarlas en WeKnora y que el gateway haga el BM25 en castellano en nuestro PostgreSQL (`to_tsvector('spanish', …)`, licencia PostgreSQL) y fusione con RRF.

`RETRIEVE_DRIVER=postgres` no es alternativa: su búsqueda por palabras clave usa `pg_search` (ParadeDB, AGPL) (`000002_embeddings.up.sql:15-55`).

### 7.2 Redis 7.4 o posterior no es permisivo

Ver §1.7. El compose original usa `redis:7.0-alpine` (BSD), pero una etiqueta flotante como `7-alpine` ya resuelve a 7.4 (RSALv2/SSPLv1) [verificado].

### 7.3 Licencias dentro de la imagen `docreader`

[verificado]

* `docreader/pyproject.toml` incluye `ebooklib`, que es **AGPL-3.0+** (PyPI: `License :: OSI Approved :: GNU Affero General Public License v3 or later`; `LICENSE.txt` del proyecto). Se importa **en el proceso** en `docreader/parser/epub_parser.py:16-17` y es dependencia de `textract==1.5.0` (`docreader/uv.lock:1962-1974`), que se usa para `.doc` (`docreader/parser/doc_parser.py:10`).
* `docker/Dockerfile.docreader:15-27, 93-112` instala `antiword` (GPL-2.0, se ejecuta como programa externo), `libreoffice` (MPL-2.0), `openjdk-17` (GPL-2.0 con excepción *Classpath*) y descarga WebKit de playwright (`Dockerfile.docreader:146-147`).
* Choca con la regla «nada AGPL/GPL».

Opciones:

* **(a)** Prescindir de `docreader`. La imagen oficial de la app enlaza `anydoc` (MIT, `third_party/anydoc-go/Cargo.toml:11`; GitHub API: `firecrawl/anydoc` → MIT). `anydoc` convierte en el propio proceso `doc`, `docx`, `pptx`, `xls`, `xlsx`, `epub` y `pdf` (`internal/infrastructure/docparser/anydoc/anydoc.go:86-103`) y tiene preferencia sobre `docreader` (`internal/types/knowledgebase.go:303-327`). Hay que comprobar en Oracle con `GET /api/v1/system/parser-engines` que `anydoc` está disponible y que la app arranca sin `DOCREADER_ADDR`. PDF escaneados (OCR) y páginas web quedarían fuera [inferencia].
* **(b)** Usar la imagen sin modificar, como servicio separado, y documentarlo en la tabla de licencias. Es una decisión del equipo, no asesoramiento legal.
* **(c)** Construir una imagen propia de `docreader` sin `ebooklib` ni `textract`. El analizador de EPUB tiene una alternativa por ZIP (`epub_parser.py:60-69`).

### 7.4 Otros

* **Interfaz de WeKnora sin castellano**: la consola es solo para el administrador técnico; la experiencia de los empleados es la app CidIA.
* **Ventana de registro abierto**: entre el primer arranque y `DISABLE_REGISTRATION=true` cualquiera con acceso a la API puede registrarse. En Oracle la API solo está en `127.0.0.1` o en la red interna, así que el riesgo es bajo.
* **CORS `*`** en la app (`router.go:122-135`): da igual porque la app no se publica. No exponer nunca `weknora:8080` fuera de la red interna.
* **El borrado es asíncrono** (§4.5): el gateway no debe dar por borrado un documento hasta que deje de aparecer en `GET /knowledge/batch`.

---

## 8. Cliente mínimo del gateway (esqueleto)

Sin probar. Esqueleto para `servidor/gateway/cidia/conocimiento/weknora.py`, con `httpx`:

```python
import httpx

class WeKnora:
    def __init__(self, base: str, api_key: str):
        self.c = httpx.AsyncClient(base_url=base, timeout=60,
                                   headers={"X-API-Key": api_key, "Accept-Language": "es-ES"})

    async def buscar(self, consulta: str, bases: list[str],
                     etiquetas_por_base: dict[str, list[str]], k: int) -> list[dict]:
        menciones = [{"type": "tag", "id": t, "kb_id": kb}
                     for kb, ts in etiquetas_por_base.items() for t in ts]
        r = await self.c.post("/knowledge-search", json={
            "query": consulta, "knowledge_base_ids": bases, "mentioned_items": menciones})
        r.raise_for_status()
        return r.json()["data"][:k]          # el top-K real lo fija rerank_top_k del espacio

    async def subir(self, kb: str, nombre: str, datos: bytes, etiquetas: list[str]) -> dict:
        r = await self.c.post(f"/knowledge-bases/{kb}/knowledge/file",
                              files={"file": (nombre, datos)},
                              data={"tag_ids": ",".join(etiquetas), "channel": "api"})
        if r.status_code == 409:
            return r.json()["data"]          # ya existía
        r.raise_for_status()
        return r.json()["data"]

    async def memoria(self, usuario: str) -> list[dict]:
        r = await self.c.get("/memory/items", headers={"X-External-User-ID": usuario})
        r.raise_for_status()
        return r.json()["data"]
```

---

## 9. Pruebas pendientes para la fase 2 (Oracle)

1. `docker compose config` con el compose de `05_servidor_oracle.md` y las correcciones de §1.7. Arrancar el perfil `weknora` y comprobar `GET /health` y que los registros de migración muestran `Skip embedding: true`.
2. Registro, login, API key `full_access` y `direct_header` (§2.1-2.2).
3. Crear en Ollama un embedding pequeño (`qwen3-embedding:0.6b`) y un LLM pequeño. Comprobar `POST /initialization/embedding/test` → `dimension: 1024`.
4. Crear la base «Público», una de departamento y una FAQ con etiquetas `n1`…`n4` y `formacion`. Subir PDF, DOCX y texto **sintéticos**. Seguir `parse_status` hasta `completed`.
5. `GET /api/v1/system/parser-engines`: ¿anydoc está activo? Probar a parar `docreader` (§7.3a).
6. `/knowledge-search` con `mentioned_items` y sin ellos, con y sin `keyword_enabled`, y con y sin reranker. Medir la calidad en castellano (§7.1).
7. Memoria: dos `X-External-User-ID` distintos no deben verse entre sí. Comprobar que `PUT /memory/settings {"enabled":false}` funciona.
8. Comprobar que no hay tráfico de salida: `docker exec` con `curl -m5 https://example.com` desde `weknora` debe fallar.
9. Opcional: arrancar sin Redis (modo Lite con PostgreSQL) y medir el ahorro de memoria.
