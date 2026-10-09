# 04. Stack del servidor y modelos diminutos para ARM

Fecha: 2026-10-09. Fuentes primarias: PyPI (API JSON), código de los paquetes descargados a una carpeta temporal (sin instalar), GitHub (API y ficheros en bruto de tags concretos), Docker Hub y GHCR (manifiestos), `registry.ollama.ai` (manifiestos y capas de licencia), Hugging Face (API) y ollama.com. Servidor Oracle: **solo lectura**.

Convenciones: **[verificado]** = leído en código, manifiesto o documentación del tag citado. **[inferencia]** = deducción razonada pendiente de medir en la fase 2. Las rutas `mcp/...` se refieren al wheel `mcp-2.3.0-py3-none-any.whl`; `docs/...` y `docs_src/...`, al sdist `mcp-2.3.0.tar.gz`.

---

## 0. Resumen

**Decisiones y datos clave**

* **SDK MCP:** la última versión es `mcp` **2.3.0** (2026-10-02, MIT, Python ≥ 3.10). **`FastMCP` ya no existe en la 2.x: ahora se llama `MCPServer`** (`from mcp.server.mcpserver import MCPServer, Context`). Importar `mcp.server.fastmcp` lanza `ModuleNotFoundError` [verificado: `mcp/server/fastmcp.py:1-16`]. Hay que actualizar el plan y `docs/arquitectura.md`, donde pone «FastAPI + FastMCP».
* La app (cliente MCP de dsh) negocia en modo `auto` y con nuestro servidor acabará en el protocolo **2026-07-28**, que **no tiene sesión**. Se aplica tanto al clon `dsh-v0.2.1-alpha.1` como a la 0.2.0-rc.2 instalada [verificado]. `stateless_http=True` solo afecta a clientes antiguos, pero conviene dejarlo puesto.
* **Base Python de todas las imágenes propias: 3.12** (`python:3.12-slim`). Con 3.10 o 3.11 no se pueden instalar las versiones que fijamos: SQLAlchemy 2.1 pide ≥ 3.11 y numpy 2.5 y PyAV 19 piden ≥ 3.12 (pip resolvería versiones anteriores). Todas las dependencias tienen ruedas `manylinux aarch64` para cp312 [verificado en PyPI].
* **Ollama 0.40.2** (`ollama/ollama`, amd64 + arm64) ofrece `/v1/chat/completions` con streaming, visión con imágenes en base64 (sin URL http) y herramientas, además de `/v1/embeddings` y `/api/embed`. **No admite `tool_choice`. El contexto por defecto es de 4096 tokens** (en GPU de menos de 24 GiB también es 4K), así que hay que fijar `OLLAMA_CONTEXT_LENGTH` [verificado].
* **Trío para Oracle:** `qwen3:0.6b` (chat y agente, 523 MB), `qwen3.5:0.8b` (visión con herramientas, 1,32 GB) y `qwen3-embedding:0.6b` (639 MB, **el mismo que en el MSI**). Los tres son Apache-2.0 [verificado: capa de licencia en `registry.ollama.ai` y, para el de embeddings, la tarjeta de Hugging Face]. Para voz, faster-whisper `base` o `small` en int8 sobre CPU.
* **Trío del MSI confirmado:** `ministral-3:8b` (6,02 GB, Q4_K_M, visión y herramientas, 256K de contexto, Apache-2.0), `qwen3-embedding:0.6b` (1024 dimensiones) y Whisper `large-v3-turbo` (faster-whisper, MIT).

**Alertas de licencia (contradicen el plan)**

1. **La imagen de speaches incluye componentes GPL dentro del proceso** (corregido en la verificación: se distingue la imagen publicada `0.8.3` de la rama `master`):
   * en la imagen `0.8.3` (`uv.lock` del tag v0.8.3): `phonemizer-fork` 3.3.1 (GPL-3.0+), que llega a través de `kokoro-onnx` 0.4.5, y la biblioteca eSpeak NG (GPL-3.0+), que cargan `espeakng-loader` 0.2.4 y `piper-phonemize` 1.2.0. En esa imagen `piper-tts` es la 1.2.0, que es **MIT** (rhasspy/piper);
   * en `master` (futura 0.9.x): `piper-tts>=1.3.0` (GPL-3.0-or-later, OHF-Voice/piper1-gpl), importado en `src/speaches/executors/piper.py:11`;
   * en las dos, el `ffmpeg` de Ubuntu, instalado con `apt` en su `Dockerfile` y compilado con GPL.

   El plan la da por «MIT» (`plan_mvp_cidia_final.tex:789`, `:808`). **Propuesta: un servicio `asr` propio y mínimo** (FastAPI + faster-whisper + ffmpeg LGPL como programa externo). Va en el §3.4.
2. **Los wheels binarios de PyAV (`av`), de los que faster-whisper depende, traen FFmpeg enlazado con libx264 y libx265 (GPL-2.0+).** El proyecto `pyav-ffmpeg` parchea el `configure` de FFmpeg para que esas dos librerías no exijan `--enable-gpl` [verificado: `patches/ffmpeg.patch` y `scripts/build-ffmpeg.py:183-186`]. **Mitigación:** compilar `av` desde el código fuente contra el FFmpeg LGPL de BtbN (§3.5).
3. **`psycopg` 3 es LGPL-3.0-only** y se carga dentro del proceso. Si se aplica al pie de la letra la regla «LGPL solo como programa externo», hay que usar **`asyncpg` (Apache-2.0)** con SQLAlchemy (`postgresql+asyncpg://`). Los wheels de `opencv-python-headless` también llevan FFmpeg LGPL-2.1 dentro del proceso (§4).
4. **`redis:7.0-alpine`**, que fija WeKnora 0.8.2 en `docker-compose.yml:553`, **no se reconstruye desde el 2024-09-08**. Alternativas BSD-3 mantenidas: `valkey/valkey:8.1-alpine` o `redis:7.2-alpine` (§8).

---

## 1. SDK oficial de MCP para Python (`mcp`)

### 1.1 Versión y requisitos [verificado: PyPI y `METADATA` del wheel]

| Dato | Valor |
|---|---|
| Última 2.x | **2.3.0** (2026-10-02). Antes: 2.0.0 (2026-07-28), 2.0.1, 2.1.x, 2.2.0 (2026-09-07). La rama 1.x sigue: la última es la **1.30.0** (2026-09-07). |
| Licencia | MIT |
| Python | `>=3.10` (clasificadores de 3.10 a 3.14) |
| Dependencias | Nuevas respecto a la 1.30: `mcp-types==2.3.0` (los tipos del protocolo), `httpx2>=2.10.0` (sustituye a `httpx` y `httpx-sse`) y `opentelemetry-api`. Desaparece `pydantic-settings`. Siguen como en la 1.x: `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, `starlette>=0.27` y `uvicorn` |
| Fijar en el proyecto | `mcp>=2.3,<3`. `ctx.headers` ya existe desde la 2.0.0 [verificado en los wheels 2.0.0, 2.2.0 y 2.3.0] |

### 1.2 `FastMCP` pasa a ser `MCPServer`

* La API está en `from mcp.server.mcpserver import MCPServer, Context` y también se exporta en `mcp.server` [verificado: `mcp/server/__init__.py:4`, `mcp/server/mcpserver/__init__.py:28`].
* `ctx.fastmcp` pasa a ser `ctx.mcp_server`, y `get_context()` desaparece: el `Context` se recibe por anotación [verificado: `docs/migration.md:645-675`, `:884-904`].
* **Los parámetros de transporte ya no van al constructor.** `json_response`, `stateless_http`, `streamable_http_path`, `host` y `transport_security` se pasan a `run()` o a `streamable_http_app()` [verificado: `docs/migration.md:752-759`; firma en `mcp/server/mcpserver/server.py:1288-1319`].

### 1.3 Definir herramientas

* Se usa el decorador `@mcp.tool()`, con paréntesis obligatorios (sin ellos lanza `TypeError`). Parámetros: `name`, `title`, `description`, `annotations`, `icons`, `meta` y `structured_output` [verificado: `mcp/server/mcpserver/server.py:669-737`].
* El esquema JSON de entrada sale de las anotaciones de tipo y la descripción, del docstring.
* El parámetro anotado con `Context` no aparece en el esquema y el modelo no lo ve [verificado: `docs/handlers/context.md`].

### 1.4 Montar el transporte streamable HTTP en FastAPI o Starlette

Todo lo de este apartado está verificado en `docs/run/asgi.md`, `docs/run/deploy.md` y `mcp/server/lowlevel/server.py:732-852`.

* `mcp.streamable_http_app(...)` devuelve una app **Starlette** con la ruta `/mcp` (configurable con `streamable_http_path`). Su lifespan arranca `mcp.session_manager.run()` (`lowlevel/server.py:851`).
* **Si se monta dentro de otra app, el lifespan de la sub-app no se ejecuta.** La app principal tiene que entrar en `mcp.session_manager.run()` dentro de su propio lifespan. Si no lo hace, la primera petición falla con `RuntimeError: Task group is not initialized` (`streamable_http_manager.py:184-185`).
* `mcp.session_manager` solo existe después de llamar a `streamable_http_app()`. Por eso la sub-app se construye a nivel de módulo y el manager solo se toca dentro del lifespan.
* **Protección contra DNS rebinding:** si no se pasa `transport_security` y el parámetro `host` de `streamable_http_app()` es el de por defecto (`"127.0.0.1"`, o `"localhost"`/`"::1"`), el servidor solo acepta `Host` igual a `127.0.0.1:*`, `localhost:*` o `[::1]:*` (`lowlevel/server.py:752-758`). Detrás de un nombre o una IP de la LAN, **todas las peticiones devuelven `421 Invalid Host header`**.
  * Si se pasa `host="0.0.0.0"` sin `transport_security`, la protección **no** se activa y no hay comprobación de `Host` ni de `Origin` (`lowlevel/server.py:753`, `transport_security.py:46-48`; `docs/migration.md:756`). No es lo que queremos: mejor pasar siempre `transport_security`.
  * Hay que pasar `TransportSecuritySettings(allowed_hosts=[...])` con la forma sin puerto y con `:*`: el patrón `nombre:*` exige que el `Host` lleve puerto (`transport_security.py:60-67`), así que detrás de un proxy en el 443 hace falta también `"nombre"` a secas. Detrás de un proxy que ya controla `Host`, se puede usar `enable_dns_rebinding_protection=False`.
  * Si no llega cabecera `Origin`, se acepta (`transport_security.py:72-76`); si llega y no está en `allowed_origins`, responde `403` (`:118-121`). El cliente MCP de dsh corre en el proceso Node del host (la app trae su propio `resources/runtime/bin/node`) y el `fetch` de Node no envía `Origin` [inferencia: comprobar en la fase 2; si aparece `403 Invalid Origin header`, añadir el origen a `allowed_origins`].
* Si `Mount("/")` va primero, captura todas las rutas. Las rutas propias de FastAPI deben declararse **antes** del `app.mount("/", mcp_app)`.
* El cuerpo de las peticiones tiene un límite de **4 MiB** por defecto (`transport_security.py:15`). Si una herramienta recibe imágenes en base64, hay que subirlo con `max_request_body_size=`.
* Detrás de un proxy TLS, uvicorn necesita `--proxy-headers --forwarded-allow-ips=...` (`docs/run/deploy.md`).

### 1.5 Modo sin estado y eras del protocolo

* El transporte enruta cada petición según la cabecera `MCP-Protocol-Version` [verificado: `streamable_http_manager.py:192-204`].
  * Si la cabecera **existe** y no es una versión con handshake (`2024-11-05` a `2025-11-25`, `mcp_types/version.py:33-38`), la petición va a la **ruta moderna 2026-07-28**: un POST con su respuesta, sin `Mcp-Session-Id`.
  * Si la cabecera **no llega**, o es una versión con handshake, la petición va a la ruta antigua: con `stateless_http=True`, cada POST crea un transporte nuevo, no hace falta `initialize` y no hay `Mcp-Session-Id` (`:206-259`; `docs/run/deploy.md`, tabla «Workers»).
* **La app (dsh)** usa `@modelcontextprotocol/client` 2.0.0 con `versionNegotiation: { mode: 'auto' }`:
  * clon: `packages/mcp/mcp-client/package.json` y `src/connection.ts:258-262`;
  * 0.2.0-rc.2 instalada: `dsh-mcp-client/lib/index.js:601` con `versionNegotiation: { mode: "auto" }` y `:46` con `requestInit: { headers: config.headers }`; su `package.json` fija `@modelcontextprotocol/client` 2.0.0. Dentro del cliente, las constantes son `FIRST_MODERN_PROTOCOL_VERSION = "2026-07-28"` y `MODERN_WIRE_REVISION = "2026-07-28"` (`dist/src-D_zzAWoS.mjs:444` y `:4024`) [verificado en `resources/app.asar`, solo lectura];
  * en `auto`, el cliente envía primero `server/discover` con la cabecera `mcp-protocol-version: 2026-07-28`, que el transporte saca del sobre `_meta` de la petición (`dist/index.mjs:2635-2645` y `:5059-5064`). Por eso nuestro servidor lo enruta a la ruta moderna, y `MCPServer` contesta `server/discover` en todos los transportes (`docs/protocol-versions.md:37`).

  **Conclusión: con nuestro gateway la conexión será 2026-07-28, sin sesión**, y se puede escalar a varios workers sin sesiones fijas.
* Lo que se pierde sin sesión: el servidor no puede pedir cosas al cliente por iniciativa propia (sampling, elicitación tipo push, `roots/list`). En 2026-07-28 se usan peticiones de varias vueltas (`InputRequiredResult`). Si hay varios workers, deben compartir clave y nombre: `RequestStateSecurity(keys=[...])` y el **mismo** nombre de `MCPServer` (`docs/run/deploy.md`).
* Cabeceras de la app: `transport.ts:40-44` pasa `config.headers` como `requestInit.headers`. Así llega `Authorization: Bearer <jwt>` configurado en el plugin [verificado en el clon].

### 1.6 Leer `Authorization` dentro de una herramienta

Hay tres maneras, en orden de preferencia [verificado]:

1. **`TokenVerifier` + `get_access_token()` (recomendada).**
   * Con `MCPServer(..., token_verifier=..., auth=AuthSettings(...))`, el SDK valida el bearer **antes** de despachar. Sin token, o con uno inválido, responde `401` con `WWW-Authenticate` y no ejecuta ninguna herramienta.
   * Dentro de la herramienta, `get_access_token()` devuelve el mismo `AccessToken` que construyó el verificador, con `subject`, `scopes`, `claims` y `expires_at`.
   * Código: `mcp/server/auth/provider.py:53-60` y `:124-136`, `mcp/server/auth/middleware/auth_context.py:13-20`; documentación en `docs/run/authorization.md` y `docs_src/authorization/tutorial002.py`.
   * `AuthSettings` exige `issuer_url` y `resource_server_url` (este puede ser `None`). Con `resource_server_url` puesto, conviene fijar `validate_token_resource` explícitamente: si no, aparece un aviso de deprecación (`mcp/server/auth/settings.py:20-70`).
2. **`ctx.headers`**: el `Mapping` de cabeceras de la petición HTTP, o `None` en stdio (`mcp/server/mcpserver/context.py:288-296`). La documentación avisa de que una cabecera no prueba la identidad. Solo sirve si el propio código verifica el JWT.
3. **`ctx.request_context.request`**: la `starlette.requests.Request` cruda (`mcp/server/context.py:47`).

`get_access_token()` lee una `ContextVar` que fija `AuthContextMiddleware` en la tarea ASGI de la petición.
* En la ruta moderna, en modo JSON, el handler corre en esa misma tarea. En modo SSE corre en una tarea hija, que hereda el contexto [verificado: docstring de `mcp/server/_streamable_http_modern.py:1-19`].
* En la ruta antigua sin estado, la tarea se crea desde la de la petición con `task_group.start()`. anyio copia el contexto de quien la crea, así que también funciona [inferencia sobre anyio/asyncio].
* En la ruta antigua **con** sesión no está garantizado. Otra razón para `stateless_http=True`.

### 1.7 Ejemplo mínimo verificado

Cómo se ha verificado:
* sintaxis comprobada con `py_compile`;
* los 7 símbolos importados de `mcp` existen en el wheel 2.3.0, comprobado con un script AST contra el wheel extraído;
* la estructura reproduce los ejemplos oficiales `docs_src/asgi/tutorial002.py`, `docs_src/deploy/tutorial001.py` y `docs_src/authorization/tutorial002.py`.

**No se ha ejecutado** porque en esta fase no se instala nada en el PC: se ejecutará en la fase 2. Requisitos: Python 3.12, `mcp==2.3.0`, `fastapi==0.143.0`, `uvicorn==0.54.0` y `pyjwt==2.15.1`.

```python
# servidor/gateway/cidia/main.py (esqueleto)
import contextlib, os
from collections.abc import AsyncIterator

import jwt  # PyJWT
from fastapi import FastAPI
from pydantic import AnyHttpUrl
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

JWT_SECRET = os.environ["CIDIA_JWT_SECRET"]          # >= 32 bytes, fuera del código
PUBLIC_URL = os.environ.get("CIDIA_PUBLIC_URL", "http://127.0.0.1:18700")
ALLOWED_HOSTS = os.environ.get("CIDIA_ALLOWED_HOSTS", "127.0.0.1:*,localhost:*").split(",")


class CidiaJWTVerifier(TokenVerifier):
    """Valida el JWT que emite el propio gateway en /api/sesion (HS256)."""
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"],
                                audience="cidia-mcp", issuer=PUBLIC_URL)
        except jwt.PyJWTError:
            return None                                # -> 401, no se ejecuta nada
        return AccessToken(token=token, client_id="cidia-app",
                           scopes=str(claims.get("scope", "")).split(),
                           expires_at=claims.get("exp"), subject=str(claims["sub"]), claims=claims)


mcp = MCPServer(
    "cidia",
    instructions="Herramientas de CidIA: instrucciones de trabajo, formación y evaluación.",
    token_verifier=CidiaJWTVerifier(),
    auth=AuthSettings(issuer_url=AnyHttpUrl(PUBLIC_URL),
                      resource_server_url=AnyHttpUrl(f"{PUBLIC_URL}/mcp"),
                      validate_token_resource=False),  # la audiencia la comprueba el verificador
)


@mcp.tool()
async def quien_soy(ctx: Context) -> dict:
    """Devuelve el usuario autenticado de la petición actual."""
    token = get_access_token()
    return {"usuario": token.subject if token else None,
            "permisos": token.scopes if token else [],
            "trae_authorization": "authorization" in (ctx.headers or {}),  # nunca devolver el token
            "protocolo": ctx.protocol_version}


mcp_app = mcp.streamable_http_app(                    # antes del lifespan
    stateless_http=True, json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=ALLOWED_HOSTS, allowed_origins=[]),
)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():             # obligatorio al montar
        yield


app = FastAPI(title="CidIA gateway", lifespan=lifespan)


@app.get("/api/salud")
async def salud() -> dict:
    return {"estado": "ok"}


app.mount("/", mcp_app)   # al final: POST /mcp y GET /.well-known/oauth-protected-resource/mcp
```

Prueba con curl para la fase 2, por la ruta antigua sin estado, que acepta `tools/list` sin `initialize` (`streamable_http_manager.py:235-243`):

```bash
curl -s http://127.0.0.1:18700/mcp -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# sin token: HTTP 401 con WWW-Authenticate: Bearer ... resource_metadata="…/.well-known/oauth-protected-resource/mcp"
```

Resultado esperado: un JSON-RPC con `quien_soy` en `result.tools`. Desde la app, el plugin configura el MCP `streamable-http` con `url: http://127.0.0.1:18700/mcp` y `headers.Authorization`.

---

## 2. Librerías del gateway [verificado: PyPI, 2026-10-09]

| Paquete | Versión (fecha) | Licencia | Python | Rueda aarch64 | Nota |
|---|---|---|---|---|---|
| fastapi | 0.143.0 (2026-10-08) | MIT | ≥3.10 | pura | `starlette>=0.46` |
| starlette | 1.7.0 | BSD-3 | ≥3.10 | pura | |
| uvicorn | 0.54.0 (2026-09-25) | BSD-3 | ≥3.10 | pura | `uvicorn[standard]` trae uvloop y httptools, ambos MIT con cp312 aarch64 |
| sqlalchemy | **2.1.4** (2026-10-07) | MIT | **≥3.11** | cp311 a cp314 | Serie 2.1. Para async: `sqlalchemy[asyncio]` (greenlet, MIT/PSF, cp312 aarch64) |
| alembic | 1.20.0 | MIT | ≥3.10 | pura | Migraciones |
| psycopg (+ psycopg-binary) | 3.3.6 (2026-09-18) | **LGPL-3.0-only** | ≥3.10 | binary cp310 a cp314 | Ver alerta 3 |
| **asyncpg** | 0.32.0 (2026-10-06) | **Apache-2.0** | ≥3.9 | cp310+ | **Recomendado**: `postgresql+asyncpg://` |
| pg8000 | 1.31.5 | BSD-3 | ≥3.9 | pura | Alternativa síncrona |
| pgvector (Python) | 0.5.1 (2026-10-09) | MIT | ≥3.10 | pura | `from pgvector.sqlalchemy import VECTOR, HALFVEC`. Registrar el tipo solo hace falta para arrays de vectores |
| argon2-cffi | 25.1.0 | MIT | ≥3.8 | vía `argon2-cffi-bindings` 26.1.0 (MIT, abi3 aarch64) | `PasswordHasher().hash()/verify()` |
| pyjwt | 2.15.1 (2026-09-28) | MIT | ≥3.9 | pura | `pyjwt[crypto]` añade cryptography 50.0.2 (Apache-2.0 o BSD, abi3 aarch64) |
| httpx | 0.28.1 (**2024-12-06**) | BSD-3 | ≥3.8 | pura | Sin versiones estables desde hace 22 meses; solo prereleases `1.0.devN` (la última, `1.0.dev6`, del 2026-08-31) |
| **httpx2** | 2.13.1 (2026-09-23) | BSD-3 | ≥3.10 | pura | Continuación de httpx mantenida por Pydantic. Ya llega como dependencia de `mcp` |
| python-multipart | 0.0.32 | Apache-2.0 | ≥3.10 | pura | Para `UploadFile` y `Form` |
| pydantic / pydantic-core | 2.14.0 / 2.50.0 | MIT | ≥3.10 | cp312 aarch64 | |
| pydantic-settings | 2.15.0 | MIT | ≥3.10 | pura | |

Propuesta de `requirements` del gateway (sin probar):

```text
mcp==2.3.0
fastapi==0.143.0
uvicorn[standard]==0.54.0
sqlalchemy[asyncio]==2.1.4
asyncpg==0.32.0
alembic==1.20.0
pgvector==0.5.1
argon2-cffi==25.1.0
pyjwt==2.15.1
httpx2==2.13.1
python-multipart==0.0.32
pydantic-settings==2.15.0
```

Hay versiones muy recientes: fastapi salió ayer y mcp hace 7 días. Conviene fijarlas con un lockfile (`uv lock`) y no subir sin pasar las pruebas. Referencia útil: el `uv.lock` del sdist de `mcp` 2.3.0 prueba el SDK con starlette 1.6.0, uvicorn 0.35.0, pydantic 2.12.5, httpx2 2.10.0 y pyjwt 2.13.0; nuestra lista resuelve starlette 1.7.0 y pydantic 2.14.0 (publicado ayer). Si algo falla en la fase 2, lo primero es bajar a esas versiones.

---

## 3. Whisper en Linux aarch64

### 3.1 faster-whisper y CTranslate2 [verificado]

* **faster-whisper 1.2.1** (2025-10-31, MIT, Python ≥ 3.9). Dependencias: `ctranslate2>=4.0,<5`, `huggingface-hub`, `tokenizers`, `onnxruntime` (el VAD Silero) y **`av>=11`**.
* **ctranslate2 4.8.2** (2026-08-31, MIT): ruedas `manylinux_2_27/2_28_aarch64` para cp39 a cp314, de 15-16 MB.
  * En aarch64 se compila **solo para CPU, con OpenBLAS y Ruy** (`python/tools/prepare_build_environment_linux.sh:66-67`). Ruy es el motor int8.
  * La CUDA solo está en las ruedas x86_64. **Corregido en la verificación:** la nota del README de faster-whisper 1.2.1 («CUDA 12 and cuDNN 9») está desfasada para ctranslate2 4.8.2. Desde la 4.6.3, Conv1D tiene implementación CUDA propia y cuDNN pasa a ser opcional (`CHANGELOG.md`, #1949), y la rueda x86_64 de la 4.8.2 se compila con CUDA 12.8, `-DWITH_CUDNN=OFF` y `-DCUDA_DYNAMIC_LOADING=ON` (`prepare_build_environment_linux.sh:23-37` y `:69`). En el MSI hacen falta las librerías de CUDA 12 (cuBLAS), pero **no cuDNN**. Que el driver tenga que admitir CUDA 12.8 es una inferencia que se comprueba en la fase 2.
* Ruedas aarch64 de las demás dependencias: onnxruntime 1.31.0 (MIT, cp311 a cp314), tokenizers 0.23.3 (abi3), numpy 2.5.3 (cp312+) y av 19.0.1 (cp312 abi3).
* **El Oracle (Neoverse-N1) admite** `asimd`, `asimddp` (dot product) y `atomics`, pero **no SVE ni i8mm** [verificado: `/proc/cpuinfo`]. Ruy usa NEON y dot product [inferencia].

### 3.2 Tamaños de los modelos [verificado: API de Hugging Face, árbol `main`]

Los repos guardan `model.bin` en **float16**. Con `compute_type="int8"`, CTranslate2 cuantiza al cargar, así que en memoria ocupa más o menos la mitad [inferencia].

| Alias en faster-whisper (`utils.py:11-30`) | Repositorio | Descarga | Pesos int8 en RAM (aprox.) | Licencia |
|---|---|---|---|---|
| `tiny` | Systran/faster-whisper-tiny | 78 MB | ~40 MB | MIT |
| `base` | Systran/faster-whisper-base | 148 MB | ~75 MB | MIT |
| `small` | Systran/faster-whisper-small | 486 MB | ~245 MB | MIT |
| `medium` | Systran/faster-whisper-medium | 1,53 GB | ~0,8 GB | MIT |
| `large-v3-turbo` / `turbo` | `mobiuslabsgmbh/…`, **que redirige (307) a `dropbox-dash/faster-whisper-large-v3-turbo`** | 1,62 GB | ~0,8 GB | MIT |

Referencia oficial (README v1.2.1): `small` en CPU con int8 y beam 5 transcribe 13 minutos de audio en **1 m 42 s y 1477 MB de RAM** (i7-12700K, 8 hilos). En el Oracle, con 2 hilos y núcleos N1, calcular de 4 a 8 veces más lento [inferencia].

### 3.3 La imagen de speaches

* **Sí tiene variante CPU para arm64:** `ghcr.io/speaches-ai/speaches:latest-cpu` y `:0.8.3-cpu` publican `linux/amd64` y `linux/arm64`, y las `-cuda` también [verificado: índice OCI en GHCR].
  * Última estable: v0.8.3 (2025-09-19). Hay `v0.9.0-rc.3` (2025-12-27).
* **Licencias, que es el problema** (corregido en la verificación, separando el tag v0.8.3 de la rama `master`):
  * `Dockerfile` (v0.8.3, líneas 8-11) instala `ffmpeg` con `apt-get` sobre Ubuntu 24.04 (`nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04` por defecto), compilado con GPL (§5).
  * En la imagen 0.8.3, `uv.lock` fija `kokoro-onnx` 0.4.5, que arrastra `phonemizer-fork` 3.3.1 (**GPL-3.0+**) y `espeakng-loader` 0.2.4. Este último trae la biblioteca compartida de eSpeak NG (**GPL-3.0+**), con ruedas de unos 10 MB por plataforma. También fija `piper-phonemize` 1.2.0, que enlaza eSpeak NG.
  * En la 0.8.3, `piper-tts` es la 1.2.0, que es **MIT** (rhasspy/piper). La `piper-tts>=1.3.0` **GPL-3.0-or-later** (PyPI; repo `OHF-Voice/piper1-gpl`), importada en `src/speaches/executors/piper.py:11`, solo está en `master` (las v0.9.0-rc).
  * El `Dockerfile` instala el extra `ui` (`uv sync --extra ui`), que trae `gradio`; `aiortc` es dependencia directa. `pyannote-audio` solo aparece en `master`. Nada de esto nos hace falta.

  **Con la regla «nada GPL», no se debe distribuir ni recomendar.**

### 3.4 Propuesta: servicio `asr` propio (OpenAI-compatible)

Usa `faster-whisper` con el audio ya decodificado a un array de numpy por un **ffmpeg LGPL externo**. Así no se llama a la decodificación de PyAV: `transcribe()` se salta `decode_audio` si recibe un `np.ndarray` (`transcribe.py:875`). Firmas verificadas en v1.2.1: `WhisperModel.__init__` (`transcribe.py:621-634`) y `transcribe(audio, language, …, vad_filter=False)` (`:747-782`). Sin ejecutar:

```python
# servidor/asr/app.py
import os, subprocess
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from faster_whisper import WhisperModel

modelo = WhisperModel(os.environ.get("ASR_MODELO", "small"),
                      device=os.environ.get("ASR_DISPOSITIVO", "cpu"),      # MSI: "cuda"
                      compute_type=os.environ.get("ASR_PRECISION", "int8"), # MSI: "int8_float16"
                      cpu_threads=int(os.environ.get("ASR_HILOS", "2")),
                      download_root="/modelos")
app = FastAPI()

def a_pcm(datos: bytes) -> np.ndarray:   # ffmpeg LGPL como programa externo
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
                        "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
                       input=datos, capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32)

@app.post("/v1/audio/transcriptions")
def transcribir(file: UploadFile = File(...), model: str = Form("whisper"),
                language: str | None = Form("es"), response_format: str = Form("json")):
    segmentos, info = modelo.transcribe(a_pcm(file.file.read()), language=language, vad_filter=True)
    segs = [{"start": s.start, "end": s.end, "text": s.text} for s in segmentos]
    texto = "".join(s["text"] for s in segs).strip()
    if response_format == "verbose_json":
        return {"text": texto, "language": info.language, "duration": info.duration, "segments": segs}
    return {"text": texto}
```

La función `def` es síncrona: FastAPI la ejecuta en su pool de hilos y no bloquea el bucle de eventos.

**Descarga de modelos (añadido en la verificación):** `WhisperModel(..., download_root=...)` descarga con `cache_dir` (`transcribe.py:681-687`) y funciona con cualquier `huggingface-hub`. En cambio, `faster_whisper.download_model(..., output_dir=...)` pasa `local_dir_use_symlinks=False` (`utils.py:106-108`), un argumento que `huggingface-hub` 2.2.0 ya no admite (`_snapshot_download.py:123-144`). Como faster-whisper pide `huggingface-hub>=0.21` sin tope, pip instala la 2.2.0, y esa llamada daría `TypeError` [inferencia a partir de las firmas]. Para precargar modelos en la imagen hay que usar `download_root` o `huggingface_hub.snapshot_download(..., local_dir=...)`, y nunca `download_model(output_dir=...)`.

### 3.5 PyAV sin GPL [verificado: fuentes; receta sin probar]

* `faster_whisper/audio.py:15` hace `import av` al importar el paquete, así que `av` hace falta aunque no se use.
* Los wheels de PyPI incluyen el FFmpeg de `pyav-ffmpeg`, que **enlaza x264 y x265** (README y `build-ffmpeg.py:183-186`), con el `configure` parcheado (`patches/ffmpeg.patch`).
* El README de PyAV 19.0.1 dice: «This release supports FFmpeg 9.x», y explica que se compila con `pip install av --no-binary av`, lo que necesita las cabeceras y `pkg-config`.
* El paquete `lgpl-shared` de BtbN trae `bin/`, `lib/*.so`, `lib/pkgconfig/*.pc` (reubicables con `${pcfiledir}`) e `include/` [verificado: `variants/linux-install-shared.sh`].

Receta:

```dockerfile
FROM python:3.12-slim AS base
ARG TARGETARCH
ARG FF_TAG=autobuild-2026-10-09-14-16
ARG FF_VER=n9.0.2-24-gfd5d616c29
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
 && case "$TARGETARCH" in amd64) A=linux64 ;; arm64) A=linuxarm64 ;; esac \
 && curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/${FF_TAG}/ffmpeg-${FF_VER}-${A}-lgpl-shared-9.0.tar.xz" \
    | tar -xJ -C /opt && mv /opt/ffmpeg-* /opt/ffmpeg && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/ffmpeg/bin:$PATH LD_LIBRARY_PATH=/opt/ffmpeg/lib PKG_CONFIG_PATH=/opt/ffmpeg/lib/pkgconfig

FROM base AS build
# libc6-dev es solo "Recommends" de gcc-14 en Debian trixie: con --no-install-recommends hay que pedirlo
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev pkg-config
RUN pip wheel --no-binary av "av==19.0.1" -w /wheels

FROM base
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/av-*.whl faster-whisper==1.2.1 fastapi==0.143.0 \
    uvicorn==0.54.0 python-multipart==0.0.32
```

Las herramientas de compilación (gcc) solo están en la etapa `build` y no se distribuyen. Los ficheros de `autobuild-*` de BtbN **hay que** copiarlos al GitHub privado. Su README tiene una política de retención: guarda los 14 últimos builds diarios y el último de cada mes durante dos años. Por eso `autobuild-2026-10-09-14-16` desaparecerá en unos 14 días, salvo que sea el último de octubre. Alternativa: fijar el último build mensual. Corregido en la verificación: antes ponía que no constaba la retención.

---

## 4. PySceneDetect y opencv-python-headless en aarch64 [verificado: PyPI]

* **scenedetect 0.7.1** (2026-07-22, BSD-3, Python ≥ 3.10) es Python puro. Desde la 0.7 **exige `opencv-python`** (la versión con interfaz gráfica). La 0.6.7 lo tenía como extra `[opencv-headless]`.
  * En `python:3.12-slim`, `opencv-python` necesita `libGL`, y además entra en conflicto con `headless` porque los dos instalan el módulo `cv2`.
  * Instalación recomendada:

    ```bash
    # --no-deps no comprueba las restricciones de scenedetect (click!=8.3.0,~=8.0): se repiten a mano
    pip install opencv-python-headless==4.14.0.94 numpy "click~=8.0,!=8.3.0" platformdirs tqdm
    pip install --no-deps scenedetect==0.7.1
    ```

* **opencv-python-headless:** PyPI marca como «última» la `5.0.0.93` (2026-07-02) porque es el número mayor, pero **la más reciente es la `4.14.0.94` (2026-07-28)**.
  * Las dos tienen ruedas `manylinux2014_aarch64` y `manylinux_2_28_aarch64` (abi3, unos 34-37 MB).
  * Recomiendo la serie 4.x: no consta que PySceneDetect 0.7.1 esté probado con OpenCV 5 [inferencia].
  * Licencias: el paquete es MIT y OpenCV, Apache-2.0. **Todos los wheels incluyen FFmpeg LGPL-2.1** (README de opencv-python, sección de licencias), cargado dentro del proceso. Es aceptable en LGPL (biblioteca dinámica, sustituible), pero conviene anotarlo en la tabla de licencias.
* Uso básico: `from scenedetect import detect, ContentDetector; escenas = detect("video.mp4", ContentDetector())` (README).
* Alternativa sin OpenCV: el filtro `scdet` de ffmpeg, llamado como programa externo (`ffmpeg -i v.mp4 -vf scdet=threshold=10 -f null -`), con los tiempos en el log [inferencia: no comprobado en esta fase].

---

## 5. ffmpeg con licencia LGPL [verificado]

* **BtbN/FFmpeg-Builds** (scripts con licencia MIT) publica versiones `lgpl`. Según su README, son las que no llevan «libraries that are GPL-only. Most prominently libx264 and libx265».
  * La configuración base de LGPL es `--enable-version3` con `COPYING.LGPLv3` (`variants/defaults-lgpl.sh`), así que **la licencia efectiva es LGPL-3.0**, no la LGPL-2.1 que pone el plan (`plan_mvp_cidia_final.tex:810`).
  * Requiere glibc ≥ 2.28 (README). El Oracle tiene 2.31 y `python:3.12-slim` (Debian), más.
* **URLs.** `latest` se reescribe cada día, así que para producción es mejor fijar un `autobuild-*` y copiarlo al GitHub privado, porque BtbN solo guarda los 14 últimos diarios y el último de cada mes durante dos años (README, «Release Retention Policy»):
  * Siempre la última (versión 9.0):
    * `https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-linux64-lgpl-9.0.tar.xz` (estática, 138 MB)
    * `https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-linuxarm64-lgpl-9.0.tar.xz` (estática, 117 MB)
    * Variante `-lgpl-shared-9.0.tar.xz`: 63,5 MB en linux64 y 54 MB en linuxarm64.
  * Fijada:
    * `https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-09-14-16/ffmpeg-n9.0.2-24-gfd5d616c29-linux64-lgpl-9.0.tar.xz`
    * `https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-09-14-16/ffmpeg-n9.0.2-24-gfd5d616c29-linuxarm64-lgpl-9.0.tar.xz`
    * La 8.1 sigue disponible: `ffmpeg-n8.1.3-16-ge0a878dd70-linux{64,arm64}-lgpl-8.1.tar.xz`.
* **Atención:**
  * El ffmpeg de Debian y Ubuntu se compila con `--enable-gpl` y enlaza `libx265` y `libx264` (`debian/rules:30`, `:65` y `:177` en `salsa.debian.org/multimedia-team/ffmpeg`, rama `debian/master`). Es GPL: **no se puede usar `apt install ffmpeg`** en ninguna imagen de CidIA.
  * Las `libav*` del sistema son igual de GPL, así que tampoco valen para compilar PyAV (§3.5).

---

## 6. Ollama [verificado: Docker Hub y documentación de `ollama/ollama` en el tag v0.40.2]

### 6.1 Imagen

* `ollama/ollama:0.40.2` (2026-10-08): `linux/amd64` (3604 MB comprimidos, con CUDA) y `linux/arm64` (2676 MB). Licencia MIT. `latest` apunta a lo mismo. Las `-rocm` son solo amd64.
* Solo CPU: `docker run -d -v ollama:/root/.ollama -p 11434:11434 ollama/ollama` (`docs/docker.mdx`). Con NVIDIA en el MSI: NVIDIA Container Toolkit y `--gpus=all`.

### 6.2 API compatible con OpenAI (`docs/api/openai-compatibility.mdx`)

* `POST /v1/chat/completions`: admite **streaming**, `stream_options.include_usage`, JSON mode, `tools`, `reasoning_effort` y `reasoning.effort`, y visión (líneas 211-253).
  * **No admite** `tool_choice`, `logprobs`, `n` ni `logit_bias` (línea 248).
  * Ollama recibe el JSON con `c.ShouldBindJSON(&req)` en `ChatMiddleware` (`middleware/openai.go:452`; la referencia anterior a `openai/openai.go:366` era errónea), y `openai.ChatCompletionRequest` no tiene campo `tool_choice`. Por tanto, los campos desconocidos se ignoran sin error [inferencia sobre el comportamiento por defecto de gin, que no activa `DisallowUnknownFields`].
  * **El gateway debe quitar `tool_choice`** o asumir que no se aplica.
* **Visión:** las imágenes van como partes `image_url` de `content`.
  * El código acepta tanto `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}` como la forma de cadena `"image_url":"data:…"` (`openai/openai.go:651-661`).
  * `decodeImageURL` solo admite `data:image/{jpeg,jpg,png,webp};base64,` o `data:;base64,`, y **rechaza URLs `http(s)`** con el error «image URLs are not currently supported» (`openai/openai.go:830-858`).
* **Thinking:** con `reasoning_effort: "none"` se desactiva en los modelos que piensan (qwen3 y qwen3.5) (línea 253). Conviene usarlo en el Oracle para ganar velocidad.
* `POST /v1/embeddings`: `input` como cadena o lista de cadenas, `encoding_format` y **`dimensions`** (líneas 304-315). `dimensions` sirve para recortar Qwen3-Embedding gracias a MRL.
* `POST /v1/responses` también existe, pero sin estado.
* `POST /v1/audio/transcriptions` también existe en la 0.40.2 (`server/routes.go:2345`). **No es Whisper**: `TranscriptionMiddleware` lee un multipart de hasta 25 MB y lo convierte en una petición de chat con el audio para un modelo de Ollama con entrada de audio (`middleware/openai.go:1295-1360`). No sustituye al servicio `asr` (no tiene segmentos con marcas de tiempo), pero conviene saberlo [añadido en la verificación].
* Ejemplo:

```bash
curl -s http://ollama:11434/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model":"qwen3.5:0.8b","stream":true,"stream_options":{"include_usage":true},"reasoning_effort":"none",
  "messages":[{"role":"user","content":[{"type":"text","text":"¿Qué pieza aparece?"},
    {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,'"$IMG_B64"'"}}]}]}'
```

### 6.3 API nativa de embeddings (`docs/api.md:1666-1690`)

* `POST /api/embed` recibe `{"model": "...", "input": "..." | [...]}`, con `truncate` (por defecto `true`), `dimensions`, `keep_alive` y `options`.
* Devuelve `{"embeddings": [[...], ...]}` **normalizado L2** (`docs/capabilities/embeddings.mdx`).

### 6.4 Variables que hay que fijar (`docs/faq.mdx`, `docs/context-length.mdx`)

* **`OLLAMA_CONTEXT_LENGTH`**: por defecto **4096** (`faq.mdx:25`). Con GPU de menos de 24 GiB, 4K. Para agentes, la propia documentación recomienda ≥ 64000. En el código, `ContextLength` vale 0 por defecto (`envconfig/config.go:230`) y el servidor elige 4096, 32768 o 262144 según la VRAM total, con umbrales de 23 y 47 GiB. En CPU o con 12 GB sale 4096 (`server/routes.go:2470-2484`). Un `num_ctx` en el Modelfile del modelo tiene prioridad (`:197-202`).
  * El prompt de sistema de dsh con las herramientas no cabe en 4K [inferencia].
  * **MSI: 32768. Oracle: 16384** (propuesta).
* `OLLAMA_NUM_PARALLEL`: 1 por defecto. La memoria escala con `NUM_PARALLEL × CONTEXT_LENGTH` (`faq.mdx:335`).
* `OLLAMA_MAX_LOADED_MODELS`: 3 en CPU (`:334`).
* `OLLAMA_KV_CACHE_TYPE=q8_0`: la mitad de memoria que `f16` (`:354-364`). Solo actúa con Flash Attention activa (`:350`). En el MSI conviene poner también `OLLAMA_FLASH_ATTENTION=1` y comprobar en el log que se aplica.
* `OLLAMA_FLASH_ATTENTION`: automático (`:346`).
* `OLLAMA_KEEP_ALIVE` (`:316`).
* `OLLAMA_NO_CLOUD`: ya comprobado en el informe 05, §6.5.
* **No hay endpoint de reranking** en 0.40.2: no figura en `docs/api.md` ni en `docs/openapi.yaml`. El Qwen3-Reranker del plan necesita otro servicio (§9).

---

## 7. Modelos diminutos para pruebas en CPU ARM

Tamaños, cuantización y licencia leídos del manifiesto y de la capa `application/vnd.ollama.image.license` de `registry.ollama.ai`. Capacidades según ollama.com. Licencias contrastadas con la API de Hugging Face (`license:apache-2.0` en todos los de la tabla) [verificado].

### 7.1 Chat y agente

| Modelo (tag) | Total | Cuant. | Capacidades | Contexto | Licencia | Comentario |
|---|---|---|---|---|---|---|
| **`qwen3:0.6b`** | **523 MB** | Q4_K_M | tools, thinking | 40K | Apache-2.0 | **Recomendado**: el más ligero con herramientas. Multilingüe |
| `qwen3:1.7b` | 1,36 GB | Q4_K_M | tools, thinking | 40K | Apache-2.0 | Algo más capaz |
| `qwen2.5:0.5b` | 398 MB | Q4_K_M | — | — | Apache-2.0 | El más pequeño. Capacidad de herramientas no comprobada |
| `granite4:350m` | 708 MB | BF16 | tools | 32K | Apache-2.0 | Sin cuantizar: pesa más que qwen3:0.6b |
| `granite4:micro` (3B) | 2,10 GB | Q4_K_M | tools | 128K | Apache-2.0 | |
| `smollm2:360m` | 726 MB | F16 | — | — | Apache-2.0 | En Hugging Face solo consta inglés. **Descartado** |
| `smollm2:135m` | 271 MB | F16 | — | — | Apache-2.0 | Solo para pruebas de humo |

### 7.2 Visión

| Modelo (tag) | Total | Detalle | Capacidades | Licencia | Comentario |
|---|---|---|---|---|---|
| **`qwen3.5:0.8b`** | **1,32 GB** | modelo de 812 MB (Q8_0), proyector de 207 MB y borrador MTP de 303 MB | vision, tools, thinking. 256K | Apache-2.0 | **Recomendado**: visión con herramientas en un solo modelo |
| `qwen3-vl:2b` | 1,89 GB | Q4_K_M | visión | Apache-2.0 | |
| `ministral-3:3b` | 2,95 GB | Q4_K_M | vision, tools. 256K | Apache-2.0 | **Misma familia que el MSI**, para pruebas de fidelidad |
| `moondream:1.8b` | 1,74 GB | 829 MB del modelo y 910 MB del proyector (Q4_0, base phi2) | visión | Apache-2.0 | Antiguo, sin herramientas y orientado al inglés |
| `granite3.2-vision:2b` | 2,44 GB | Q4_K_M | visión | Apache-2.0 | |
| `qwen2.5vl:3b` | 3,20 GB | Q4_K_M | visión | Apache-2.0 | Ya pesado para el Oracle |

### 7.3 Embeddings

| Modelo (tag) | Total | Dimensiones | Idiomas | Licencia | Comentario |
|---|---|---|---|---|---|
| **`qwen3-embedding:0.6b`** | **639 MB** (Q8_0) | **1024** (MRL de 32 a 1024). Contexto de 32K | más de 100 | Apache-2.0 (Hugging Face. La capa de Ollama no trae licencia) | **El mismo en Oracle y en el MSI**: mismas colecciones y nada que reindexar |
| `granite-embedding:278m` | 563 MB (F16) | 768 | multilingüe, incluye `es` | Apache-2.0 | Plan B del plan |
| `granite-embedding:30m` | 63 MB | 384 | solo inglés | Apache-2.0 | Solo integración continua |
| `all-minilm:22m` / `:33m` | 46 / 67 MB | 384 | inglés | Apache-2.0 | Solo humo |
| `nomic-embed-text` | 274 MB | 768 | inglés | Apache-2.0 | |
| `bge-m3` | 1,16 GB | 1024 | multilingüe | MIT | Más pesado |
| `embeddinggemma` | 622 MB | — | — | **Gemma Terms of Use** | **Descartado** |

Datos de Qwen3-Embedding-0.6B: `hidden_size 1024` y `max_position_embeddings 32768` (`config.json`). La tarjeta dice «Embedding Dimension: Up to 1024» y recomienda prompts de instrucción para las consultas [verificado: Hugging Face].

### 7.4 Recomendación para Oracle (Neoverse-N1, 4 núcleos y 23 GB, sin GPU)

| Función | Modelo | Por qué |
|---|---|---|
| Chat y agente | `qwen3:0.6b` | 523 MB, con herramientas. Coincide con el informe 05, §6.5 |
| Visión | `qwen3.5:0.8b` | 1,32 GB, con visión y herramientas. Si hay que ahorrar RAM, **puede hacer también de chat** y quedarse solo |
| Embeddings | `qwen3-embedding:0.6b` | Mismas 1024 dimensiones que el MSI |
| Voz | faster-whisper `base` (velocidad) o `small` (calidad en castellano), en int8 y con 2 hilos | 148 / 486 MB de descarga |

Los pesos de modelo suman unos 2,5 GB.

Estimaciones de velocidad con 2-4 hilos [**inferencia, a medir en la fase 2** con los campos `eval_count/eval_duration` y `prompt_eval_*` de `/api/chat`]:
* generación: unos 15-30 tokens/s con qwen3:0.6b, 8-15 con qwen3.5:0.8b (Q8_0) y 3-6 con ministral-3:3b;
* **procesamiento del prompt**: unos 50-150 tokens/s, así que un prompt de agente de 8K tarda **1-2 minutos** en dar el primer token.

En la siguiente vuelta, la caché de prefijo de Ollama lo reduce. **En el Oracle el agente es para probar que funciona, no para medir rendimiento.**

Notas:
* qwen3.5 es la arquitectura `qwen35`, con proyector y capa `draft`. Hay que comprobar en la fase 2 que la 0.40.2 la carga en arm64 con visión [inferencia].
* `ministral-3` exige Ollama ≥ 0.13.1 (ollama.com).

### 7.5 Confirmación del trío del MSI (amd64, RTX 4080 de 12 GB)

| Función | Modelo | Datos [verificado] |
|---|---|---|
| LLM con visión | `ministral-3:8b` | 6022 MB, Q4_K_M, 8,9 B parámetros, vision + tools, 256K, Apache-2.0. En Hugging Face consta `es` entre los idiomas |
| Embeddings | `qwen3-embedding:0.6b` | 639 MB, 1024 dimensiones, Apache-2.0 |
| Voz | faster-whisper `large-v3-turbo` | 1,62 GB en fp16, MIT. En GPU, `compute_type="int8_float16"`. Con ctranslate2 4.8.2 necesita las librerías de CUDA 12 (cuBLAS), pero no cuDNN (§3.1, corregido en la verificación) |

Presupuesto de VRAM [inferencia, a medir con `ollama ps` y `nvidia-smi`]:
* La KV cache de Ministral 3 8B ocupa 2 × 34 capas × 8 cabezas KV × 128 × 2 bytes = **136 KiB por token** en f16 (`config.json`: `num_hidden_layers 34`, `num_key_value_heads 8`, `head_dim 128`).
* Con 32K de contexto: 4,25 GiB en f16 o **unos 2,2 GiB en q8_0**.
* Suma: 6,0 GB de pesos, más ~2,2 de KV q8_0, más ~0,5-1 de búferes y codificador de visión, más ~0,8 de embeddings: **unos 9,5-10 GB**. Queda poco margen para Whisper turbo en GPU (~1,5-2 GB).
* Propuesta:
  * `OLLAMA_CONTEXT_LENGTH=32768`, `OLLAMA_KV_CACHE_TYPE=q8_0` y `OLLAMA_NUM_PARALLEL=1`. Para dos usuarios: `NUM_PARALLEL=2` con 16K cada uno, que ocupa lo mismo.
  * Whisper **a demanda**: se carga, transcribe y se libera. Si no cabe, `small` en int8 en la CPU del MSI, que según el benchmark oficial hace 13 minutos de audio en unos 1 m 42 s con 8 hilos.

Licencia de NVIDIA: los runtimes de CUDA (dentro de la imagen de Ollama y de las ruedas `nvidia-*`) **no son software libre**, aunque se pueden redistribuir. Con ctranslate2 4.8.2, el servicio `asr` ya no necesita cuDNN, así que basta con cuBLAS y no hace falta una imagen base `-cudnn`. Hay que anotarlos en la tabla de licencias como excepción de sistema (§9).

---

## 8. Imágenes multi-arquitectura

Datos de Docker Hub y GHCR del 2026-10-09. Los tamaños están comprimidos y en MiB: Docker Hub da bytes, y por ejemplo ollama arm64 son 2806 × 10⁶ bytes = 2676 MiB [verificado].

| Imagen y tag recomendado | amd64 | arm64 | Tamaño arm64 | Licencia | Nota |
|---|---|---|---|---|---|
| `pgvector/pgvector:0.8.7-pg17-bookworm` | ✓ | ✓ | 151 MB | PostgreSQL (pgvector) | Hoy `pg17` = `0.8.7-pg17` = `pg17-bookworm` (mismo digest `sha256:ac08538c…`). Existe también `pg17-trixie`, con otro digest. **Fijar la base Debian y no cambiarla** con datos dentro: el cambio de glibc altera el orden de cotejo de los índices [inferencia] |
| `qdrant/qdrant:v1.16.2` | ✓ | ✓ | 68 MB | Apache-2.0 | Es la que fija WeKnora 0.8.2 (`docker-compose.yml:657`). La última es la `v1.19.2` (71 MB). El Oracle usa páginas de 4096 bytes, sin el problema de jemalloc con páginas de 64K [verificado: `getconf PAGESIZE`] |
| `valkey/valkey:8.1-alpine` (8.1.10) | ✓ | ✓ | ~20 MB | BSD-3 | **Recomendada** en lugar de Redis. Compatible a nivel de protocolo. Con WeKnora (go-redis/asynq) **está por probar** [inferencia] |
| `redis:7.2-alpine` (7.2.12) | ✓ | ✓ | 16 MB | BSD-3 | `LICENSE.txt` de Redis: «Redis Open Source 7.2 and prior releases remain subject to the BSDv3». A partir de la 8, RSALv2, SSPLv1 o AGPLv3. La 7.4 ya salió con RSALv2/SSPLv1, sin BSD: no usar ninguna 7.4+ [esto último no consta en ese `LICENSE.txt`; procede del cambio de licencia de 2024] |
| `redis:7.0-alpine` | ✓ | ✓ | 13 MB | BSD-3 | **Última reconstrucción: 2024-09-08**. Sin parches. No usar |
| `ollama/ollama:0.40.2` | ✓ | ✓ | 2676 MB | MIT | |
| `python:3.12-slim` | ✓ | ✓ | 42 MB | PSF | Base de gateway, asr y captura |
| `wechatopenai/weknora-{app,docreader,ui,sandbox}:v0.8.2` | ✓ | ✓ | 521 / 1449 / 31 / 187 MB | — | Licencia: ver la tabla del plan |
| `ghcr.io/speaches-ai/speaches:0.8.3-cpu` | ✓ | ✓ | — | MIT el código, con **dependencias GPL** | No usar (§3.3) |
| `paradedb/paradedb:v0.22.6-pg17` | ✓ | ✓ | 478 MB | **AGPL-3.0** (repo `paradedb/paradedb`) | No usar |

**WeKnora sin ParadeDB** [verificado en el código de v0.8.2]: con `RETRIEVE_DRIVER=qdrant`, `internal/container/container.go:809-818` pone `app.skip_embedding=true` en la DSN de las migraciones. Las cuatro migraciones que crean o actualizan `pg_search` (`000002`, `000008`, `000011` y `000099`) empiezan con `IF current_setting('app.skip_embedding', true) = 'true' THEN RETURN`. Por eso basta con `pgvector/pgvector:pg17` (`uuid-ossp` viene en el contrib de la imagen oficial). Añadido en la verificación: la migración `000041` ejecuta `CREATE EXTENSION IF NOT EXISTS pg_trgm` sin condición (línea 32), y `pg_trgm` también viene en el contrib. Las de vectores posteriores (`000059` y `000095`) comprueban antes que exista la tabla o la extensión `vector`. Con `RETRIEVE_DRIVER=qdrant`, WeKnora no crea la extensión `vector`; si la usa el núcleo de CidIA, la crea nuestra propia migración.

---

## 9. Riesgos y preguntas abiertas

**Riesgos**

1. **El plan nombra FastMCP**, pero en la 2.x es `MCPServer`. Si alguien instala `mcp` sin fijar versión y copia ejemplos de la 1.x, falla al importar. Hay que fijar `mcp==2.3.0` y corregir el plan y `arquitectura.md`.
2. **speaches trae GPL**: en la imagen 0.8.3, phonemizer-fork, eSpeak NG y el ffmpeg de Ubuntu; en `master`, además, piper-tts ≥ 1.3. Hay que sustituirlo por un `asr` propio y corregir la tabla de licencias del plan (`:789`, `:808` y `:1408`).
3. **Los wheels de PyAV llevan x264 y x265.** Hay que compilar `av` desde fuente contra el FFmpeg LGPL de BtbN (receta del §3.5, sin probar), o que lo valide un asesor.
4. **psycopg LGPL** dentro del proceso: usar asyncpg. **opencv-headless** lleva FFmpeg LGPL-2.1 dentro del proceso: decidir si se acepta o usar el `scdet` de ffmpeg.
5. **Contexto de Ollama a 4K por defecto.** Sin `OLLAMA_CONTEXT_LENGTH`, el agente se corta sin avisar.
6. **El MSI va justo de VRAM** con Ministral 8B a 32K, embeddings y Whisper turbo (§7.5). Whisper tiene que ir a demanda.
7. **Lentitud del Oracle** con prompts largos de agente (1-2 minutos hasta el primer token) [inferencia]. No sirve para demos ni para medir.
8. **Versiones muy recientes:** fastapi 0.143.0 salió ayer, Ollama 0.40.2 ayer y mcp 2.3.0 hace 7 días. Hay que fijarlas con lockfile.
9. El Oracle tiene **Ubuntu 20.04** (fuera de soporte estándar desde abril de 2025), Python 3.8 en el host y cgroup v1. Todo lo de CidIA va en contenedores. El efecto de cgroup v1 en Ollama está en el informe 05, §1.

**Preguntas abiertas**

1. **Reranker:** Ollama 0.40.2 no tiene endpoint de reranking. ¿Qwen3-Reranker con un servicio propio (CTranslate2 u ONNX), el `rerank_server_demo.py` de WeKnora, o sin reranker en el MVP?
2. ¿Se admite **LGPL dentro del proceso** para librerías dinámicas sin modificar (psycopg, OpenCV, PyAV compilado contra FFmpeg LGPL)? ¿O la regla es estrictamente «solo programa externo»?
3. ¿Aceptamos los **runtimes de NVIDIA** (CUDA y cuDNN) como excepción de sistema en la tabla de licencias?
4. ¿WeKnora 0.8.2 funciona con **Valkey 8.1**? Se prueba en la fase 2 en el Oracle.
5. ¿`qwen3.5:0.8b` con visión funciona en Ollama 0.40.2 arm64 sobre CPU? Plan B: `ministral-3:3b`.
6. ¿Qué tamaño tiene el prompt de sistema de dsh con las herramientas de CidIA? Fija `OLLAMA_CONTEXT_LENGTH` en los dos servidores.

---

## 10. Fuentes principales

* PyPI JSON: `https://pypi.org/pypi/<paquete>/json` (versiones, fechas, licencias, `requires_dist` y ruedas).
* MCP Python SDK 2.3.0: wheel y sdist de PyPI. Ficheros citados: `mcp/server/fastmcp.py`, `mcp/server/mcpserver/{server,context}.py`, `mcp/server/lowlevel/server.py`, `mcp/server/streamable_http_manager.py`, `mcp/server/_streamable_http_modern.py`, `mcp/server/transport_security.py`, `mcp/server/auth/{settings,provider}.py`, `mcp/server/auth/middleware/auth_context.py`. Documentación: `docs/run/{asgi,deploy,authorization}.md`, `docs/migration.md`, `docs/protocol-versions.md`, `docs/handlers/context.md` y `docs_src/{asgi,deploy,authorization}/`.
* dsh: clon `dsh-v0.2.1-alpha.1` (`packages/mcp/mcp-client/{package.json,src/connection.ts,src/transport.ts}`) y `resources/app.asar` de la 0.2.0-rc.2 instalada (solo lectura).
* Ollama v0.40.2: `docs/api/openai-compatibility.mdx`, `docs/api.md`, `docs/faq.mdx`, `docs/context-length.mdx`, `docs/docker.mdx`, `docs/capabilities/{embeddings,vision}.mdx`, `openai/openai.go`, `docs/openapi.yaml`. Manifiestos en `https://registry.ollama.ai/v2/library/<modelo>/manifests/<tag>` y páginas `https://ollama.com/library/{qwen3,qwen3.5,ministral-3,qwen3-embedding,granite4}`.
* Hugging Face API: `https://huggingface.co/api/models/<repo>` y `/tree/main`. `config.json` de Qwen3-Embedding-0.6B y de Ministral-3-8B-Instruct-2512.
* faster-whisper v1.2.1: `README.md`, `faster_whisper/{utils,audio,transcribe,__init__}.py`. CTranslate2: `README.md` y `python/tools/prepare_build_environment_linux.sh`.
* speaches: `Dockerfile`, `pyproject.toml`, `src/speaches/executors/piper.py` e índices OCI en `ghcr.io/v2/speaches-ai/speaches/manifests/{latest-cpu,0.8.3-cpu,...}`.
* PyAV: `README.md` (v19.0.1). pyav-ffmpeg: `README.md`, `scripts/build-ffmpeg.py`, `patches/ffmpeg.patch`.
* BtbN/FFmpeg-Builds: API de releases (`latest` y `autobuild-2026-10-09-14-16`), `README.md` y `variants/{defaults-lgpl,linuxarm64-lgpl,linux-install-shared,linux-install-static}.sh`.
* Debian ffmpeg: `https://salsa.debian.org/multimedia-team/ffmpeg/-/raw/debian/master/debian/rules`.
* opencv-python: `README.md` (sección de licencias). PySceneDetect: `README.md` y PyPI.
* Redis `LICENSE.txt` (rama `unstable`) y `COPYING` (7.2.11). pgvector `LICENSE`. API de GitHub para las licencias de los repos.
* Docker Hub: `https://hub.docker.com/v2/repositories/<repo>/tags/<tag>`.
* WeKnora v0.8.2 (clon local): `docker-compose.yml`, `.env.example`, `internal/container/container.go`, `migrations/versioned/*.up.sql`.
* Servidor Oracle (solo lectura): `uname`, `lscpu`, `/proc/cpuinfo`, `free`, `df`, `ldd --version`, `getconf PAGESIZE`, `docker info`, `docker ps` y `ss -ltn`.

---

## Verificación

Revisión escéptica del 2026-10-09 con las mismas reglas: en el PC no se instala nada, en el Oracle solo hay comandos de lectura y no se toca ningún secreto. Fuentes:
* PyPI JSON, con el SHA-256 de los artefactos `mcp` 2.3.0 y 2.0.0 contrastado con PyPI;
* el wheel y el sdist de `mcp` 2.3.0;
* `app.asar` de la 0.2.0-rc.2 instalada, leído con un lector propio sin extraer la app;
* el clon `dsh-v0.2.1-alpha.1`;
* ficheros en bruto de GitHub en los tags `ollama v0.40.2`, `faster-whisper v1.2.1`, `CTranslate2 v4.8.2`, `PyAV v19.0.1`, `speaches v0.8.3`/`master` y `pgvector-python v0.5.1`;
* los manifiestos de `registry.ollama.ai`, Docker Hub, GHCR, la API de Hugging Face y la página de releases de BtbN;
* `salsa.debian.org`, `packages.debian.org` y el clon de WeKnora v0.8.2.

Al final no se pudo ejecutar el ejemplo del gateway: en este PC no están FastAPI, Starlette ni pydantic, y no se instalan.

### Confirmado

* **SDK MCP 2.3.0** (2026-10-02, MIT, `>=3.10`):
  * `mcp/server/fastmcp.py:1-16` lanza `ModuleNotFoundError`;
  * `MCPServer` y `Context` están en `mcp.server.mcpserver` (`__init__.py:15`, `:28`) y `MCPServer` también en `mcp.server` (`:4`);
  * el constructor no acepta parámetros de transporte (`server.py:158-186`) y `streamable_http_app()` sí (`:1288-1319`);
  * `@mcp.tool()` sin paréntesis da `TypeError` (`:719-722`);
  * `session_manager` solo existe tras `streamable_http_app()` (`:313-323`);
  * el lifespan de la sub-app es `session_manager.run()` (`lowlevel/server.py:851`);
  * hay `RuntimeError: Task group is not initialized` (`streamable_http_manager.py:184-185`);
  * el límite de cuerpo es de 4 MiB (`transport_security.py:15`);
  * el aviso de que el lifespan de la sub-app no se ejecuta está en `docs/run/asgi.md:62-66`;
  * `--proxy-headers` (`docs/run/deploy.md:50`, `:185`) y «mismas claves y mismo nombre» con varios workers (`:143-145`, `:188`).
* **Autenticación:**
  * `TokenVerifier` (Protocol, `auth/provider.py:124-136`), `AccessToken` con `subject` y `claims` (`:53-60`) y `get_access_token()` (`auth_context.py:13-20`);
  * `AuthSettings` exige `issuer_url` y `resource_server_url` y avisa si falta `validate_token_resource` (`settings.py:27-69`);
  * `RequireAuthMiddleware` envuelve la ruta `/mcp` (`lowlevel/server.py:812-824`) y responde 401 con `WWW-Authenticate`;
  * la ruta de metadatos es `/.well-known/oauth-protected-resource/mcp` (`auth/routes.py:201-216`);
  * con verificador propio y sin `auth_server_provider`, el `issuer_url` http no se valida (`validate_issuer_url` solo se llama en `create_auth_routes`, `routes.py:83`);
  * en la ruta moderna, la `Request` de Starlette llega como `request_context` (`_streamable_http_modern.py:458-462`), así que `ctx.headers` (`context.py:288-296`; existe ya en el wheel 2.0.0) y `ctx.request_context.request` funcionan;
  * en modo JSON, el handler corre en la tarea ASGI (docstring, líneas 1-19).
* **Era del protocolo:**
  * `HANDSHAKE_PROTOCOL_VERSIONS` no incluye 2026-07-28 (`mcp_types/version.py:33-38`);
  * el cliente 2.0.0 de la app manda `server/discover` con `mcp-protocol-version: 2026-07-28` (ver §1.5), así que la app llega por la ruta moderna, sin sesión;
  * `transport.ts:40-44` y el esquema `headers` (`index.ts:91-92`, `:136`) confirman que `Authorization` viaja desde la configuración del plugin.
* **Librerías** (versión, fecha, licencia, `requires_python` y ruedas aarch64): todas las de la tabla del §2 coinciden con PyPI. Detalles:
  * `argon2-cffi-bindings` 26.1.0 tiene `cp310-abi3` aarch64;
  * `asyncpg` 0.32.0 tiene `cp312 manylinux_2_28_aarch64`;
  * httpx2 es un proyecto de `pydantic/httpx2` que se presenta como continuación de HTTPX;
  * `pgvector.sqlalchemy` exporta `VECTOR` y `HALFVEC`, y `register_vector` solo hace falta para arrays (README v0.5.1).
* **Whisper:**
  * faster-whisper 1.2.1: dependencias, alias `utils.py:11-30`, `import av` en `audio.py:15` (y `__init__.py:1` lo importa siempre), firmas `transcribe.py:621-634` y `:747-790`, y el salto de `decode_audio` con `np.ndarray` en `:875-876`;
  * benchmark del README (`small`, int8, 1 m 42 s y 1477 MB, i7-12700K con 8 hilos);
  * ctranslate2 4.8.2 en aarch64 compila con OpenBLAS + Ruy y sin CUDA (`prepare_build_environment_linux.sh:66-67`);
  * tamaños de los repos de Hugging Face: 78, 148, 486, 1531 y 1622 MB; el `model.bin` de `small` pesa 484 MB, lo que cuadra con fp16;
  * la redirección `mobiuslabsgmbh` → `dropbox-dash`;
  * licencias MIT.
* **speaches:** `0.8.3-cpu` y `latest-cpu` publican `linux/amd64` y `linux/arm64` (GHCR); v0.8.3 es del 2025-09-19 y v0.9.0-rc.3 del 2025-12-27; el `ffmpeg` se instala con `apt`. La conclusión de no usarlo se mantiene.
* **PyAV y ffmpeg:**
  * el README de PyAV 19.0.1 dice «This release supports FFmpeg 9.x» y documenta `--no-binary av`;
  * `pyav-ffmpeg` añade `--enable-libx265` y `--enable-libx264` (`build-ffmpeg.py:183-186`) y su `patches/ffmpeg.patch` saca libx264 y libx265 de `EXTERNAL_LIBRARY_GPL_LIST`;
  * BtbN: `defaults-lgpl.sh` usa `--enable-version3` y `COPYING.LGPLv3`, el README pide glibc ≥ 2.28 y la variante `lgpl` es la que va sin x264 ni x265;
  * `linux-install-shared.sh` copia `lib/*.so`, los `.pc` con `${pcfiledir}` e `include/`;
  * las 4 URLs de 9.0 y las de 8.1 existen, con los tamaños citados (GitHub los muestra en MiB);
  * `debian/rules` lleva `--enable-gpl` (línea 30), `--enable-libx265` (`:65`) y `--enable-libx264` (`:177`).
* **OpenCV y PySceneDetect:**
  * scenedetect 0.7.1 exige `opencv-python` y la 0.6.7 tenía el extra `opencv-headless`;
  * opencv-python-headless: la 5.0.0.93 es del 2026-07-02 y la 4.14.0.94 del 2026-07-28, las dos con ruedas abi3 aarch64;
  * el README de opencv-python dice «All wheels ship with FFmpeg licensed under the LGPLv2.1» (línea 203);
  * `detect(..., ContentDetector())` está en el README.
* **Ollama 0.40.2:**
  * imagen del 2026-10-08, amd64 y arm64, `-rocm` solo amd64, MIT;
  * tabla de compatibilidad con OpenAI (`openai-compatibility.mdx:211-253`, `:304-316`);
  * imágenes en `openai/openai.go:651-661` y `:830-861`;
  * `/api/embed` (`docs/api.md:1666-1684`) devuelve vectores normalizados L2 (`embeddings.mdx:68`);
  * variables de `faq.mdx` (líneas 25, 316, 334-336, 346 y 350-364);
  * `context-length.mdx:7-14`;
  * `OLLAMA_NO_CLOUD` (`envconfig/config.go:238`);
  * no hay ruta de reranking (`server/routes.go:2302-2348`).
* **Modelos** (manifiestos de `registry.ollama.ai`):
  * qwen3:0.6b: 523 MB, Q4_K_M y Apache-2.0;
  * qwen3.5:0.8b: 1322 MB, que se reparten en 812 MB de modelo Q8_0, 207 MB de proyector y 303 MB de borrador; familia `qwen35` y Apache-2.0;
  * ministral-3:3b: 2954 MB, Q4_K_M, Apache-2.0; la configuración declara 3,8 B parámetros;
  * ministral-3:8b: 6022 MB, Q4_K_M, 8,9 B parámetros y Apache-2.0;
  * qwen3-embedding:0.6b: 639 MB y Q8_0, sin capa de licencia;
  * granite-embedding:278m: 563 MB y F16;
  * embeddinggemma: Gemma Terms of Use;
  * granite4:350m: 708 MB en BF16; smollm2:360m: 726 MB en F16;
  * capacidades y contextos de ollama.com: qwen3 tools y thinking con 40K; qwen3.5 vision, tools y thinking con 256K; ministral-3 vision y tools con 256K, que necesita Ollama 0.13.1;
  * Hugging Face: todos Apache-2.0; Ministral 3 incluye `es`; SmolLM2 solo `en`;
  * `config.json`: Qwen3-Embedding con `hidden_size` 1024 y `max_position_embeddings` 32768, y la tarjeta dice «32 to 1024»; Ministral 3 8B con 34 capas, 8 cabezas KV y `head_dim` 128, de donde salen 136 KiB por token en f16.
* **Imágenes:**
  * los `pg17` comparten digest `sha256:ac08538c6f8b…` y `pg17-trixie` tiene otro;
  * qdrant v1.16.2 y v1.19.2 tienen arm64;
  * `redis:7.0-alpine` no se actualiza desde el 2024-09-08;
  * valkey 8.1-alpine y redis 7.2-alpine se actualizaron el 2026-09-21;
  * las cuatro `weknora-*:v0.8.2` tienen arm64;
  * licencias: valkey `COPYING` BSD-3, pgvector PostgreSQL, qdrant Apache-2.0 y paradedb AGPL-3.0.
* **WeKnora:** `docker-compose.yml:553` (`redis:7.0-alpine`) y `:657` (`qdrant v1.16.2`); `container.go:809-825`; guardas `skip_embedding` en `000002`, `000008`, `000011` y `000099`.
* **Oracle** (ssh de solo lectura, hoy):
  * `aarch64`, 4 núcleos Neoverse-N1 con `asimd`, `asimddp` y `atomics`, sin `sve` ni `i8mm`;
  * 23 GiB de RAM con 18 disponibles;
  * páginas de 4096, glibc 2.31 y Ubuntu 20.04.6;
  * cgroup v1 (`/sys/fs/cgroup` es `tmpfs`);
  * Docker 26.1.3 y compose 2.35.1;
  * 106 GiB libres en `/` según `df -h` (antes ponía 112: varía con el uso).
* **Plan:** las líneas citadas (`362`, `788`, `789`, `808`, `810`, `1162` y `1408`) dicen lo que el informe afirma. `docs/arquitectura.md:10` y `:66` siguen poniendo FastMCP.

### Corregido en este informe

1. **Rama 1.x del SDK:** la última es la 1.30.0 (2026-09-07), no la 1.29.1. Las dependencias nuevas de la 2.x son solo `mcp-types`, `httpx2` y `opentelemetry-api`; `pyjwt`, `python-multipart`, `sse-starlette`, `starlette` y `uvicorn` ya estaban en la 1.x (§1.1).
2. **DNS rebinding:** la protección automática depende también del parámetro `host` de `streamable_http_app()`. Con `host="0.0.0.0"` y sin `transport_security` no hay comprobación. Se añaden dos detalles: `nombre:*` exige puerto en `Host`, y un `Origin` presente que no está permitido da `403` (§1.4).
3. **Enrutado por versión:** sin cabecera `MCP-Protocol-Version` la petición va a la ruta antigua, no a la moderna. Los literales del `app.asar` son `FIRST_MODERN_PROTOCOL_VERSION` y `MODERN_WIRE_REVISION`, con las líneas exactas (§1.5).
4. **httpx:** sí hay publicaciones desde 2024, pero solo prereleases `1.0.dev1` a `1.0.dev6` (§2).
5. **cuDNN:** ctranslate2 4.8.2 no lo necesita (Conv1D en CUDA desde la 4.6.3; rueda x86_64 con `-DWITH_CUDNN=OFF`). La nota del README de faster-whisper está desfasada (§3.1, §7.5 y nota de NVIDIA).
6. **speaches:** la imagen 0.8.3 lleva `piper-tts` 1.2.0, que es MIT. Su GPL viene de `phonemizer-fork` (no `phonemizer`), de eSpeak NG (`espeakng-loader` y `piper-phonemize`) y de `ffmpeg`. `piper-tts>=1.3.0`, `executors/piper.py:11` y `pyannote-audio` son de `master`, y `gradio` entra por `--extra ui` (§0 y §3.3).
7. **Receta de PyAV:** faltaba `libc6-dev` (en Debian trixie solo es *Recommends* de `gcc-14`): con `--no-install-recommends`, la compilación fallaría (§3.5).
8. **Retención de BtbN:** sí está documentada (14 builds diarios y el último de cada mes durante dos años). El `autobuild-*` fijado caduca, así que hay que copiarlo al GitHub privado (§3.5 y §5).
9. **Ruta del `ShouldBindJSON` de Ollama:** es `middleware/openai.go:452` (`ChatMiddleware`), no `openai/openai.go:366` (§6.2).
10. **Precisiones añadidas:**
    * `uv.lock` del SDK MCP, con las versiones con las que se probó (§2);
    * `download_model(output_dir=...)` de faster-whisper, incompatible con `huggingface-hub` 2.x (§3.4);
    * `click~=8.0,!=8.3.0` en la receta de PySceneDetect (§4);
    * `/v1/audio/transcriptions` de Ollama, que no es Whisper (§6.2);
    * lógica de contexto por VRAM y KV `q8_0` solo con Flash Attention (§6.4);
    * `pg_trgm` sin condición en la migración `000041` de WeKnora (§8);
    * Redis 7.4 sin BSD (§8);
    * los tamaños de las imágenes están en MiB (§8).

### Sigue sin confirmar

* El ejemplo del gateway (§1.7), el servicio `asr` (§3.4) y las recetas de PyAV y ffmpeg (§3.5) solo están revisados contra el código y la sintaxis: no se han ejecutado. Para la fase 2:
  * `curl` sin token debe dar 401;
  * con token, `tools/list`;
  * conexión desde la app con `Authorization`;
  * comprobar que la app no envía `Origin`.
* Que el `fetch` de Node del host de dsh no envíe `Origin` (inferencia).
* Que el driver del MSI tenga que admitir CUDA 12.8 para las ruedas de ctranslate2 4.8.2.
* Que Ollama 0.40.2 en arm64 con CPU cargue `qwen3.5:0.8b` con visión (arquitectura `qwen35` con proyector y borrador).
* Velocidades en el Oracle y presupuesto de VRAM del MSI: siguen siendo estimaciones.
* Si WeKnora 0.8.2 (go-redis/asynq) funciona con Valkey 8.1.
* Que eSpeak NG vaya enlazado dentro de las ruedas de `espeakng-loader`: su descripción dice que carga la biblioteca compartida y las ruedas son binarias de unos 10 MB, pero no se ha abierto la rueda.
* La compatibilidad del SDK MCP 2.3.0 con starlette 1.7.0 y pydantic 2.14.0, más nuevas que las de su `uv.lock`.
