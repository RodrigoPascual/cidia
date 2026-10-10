# CidIA: arquitectura del MVP

Documento de referencia técnico del repositorio. Resume cómo está construido CidIA y fija los contratos entre piezas. El plan completo (por qué y en qué orden) está en `Plan_MVP_CidIA_final.pdf`.

## 1. Piezas

```
Portátiles Windows                       Servidor CidIA (Ubuntu + Docker)
┌──────────────────────────┐            ┌───────────────────────────────────────────────┐
│ App CidIA (base dsh)     │  HTTP      │ gateway  (FastAPI + MCPServer, Python 3.12)   │
│  · plugin cidia          │──────────▶ │   /api/*   API REST de la interfaz            │
│  · interfaz web embebida │            │   /v1/*    API compatible con OpenAI (LLM)    │
│  · proveedor = gateway   │            │   /mcp     servidor MCP para el agente        │
│  · MCP = gateway         │            │   /app/*   interfaz web (SPA React)           │
└──────────────────────────┘            │ postgres (pgvector) · ollama · asr            │
                                        │ espacio-trabajo (contenedores sin red)        │
                                        │ weknora + qdrant + redis (perfil opcional)    │
                                        └───────────────────────────────────────────────┘
```

* **gateway**: único punto de entrada (FastAPI + SDK oficial de MCP 2.x, cuyo servidor se llama `MCPServer`). Autentica, calcula permisos, habla con los modelos, con el motor de conocimiento y con la base de datos. Las tres entradas (`/api`, `/v1`, `/mcp`) llaman a la misma lógica de permisos.
* **web**: interfaz de CidIA (React + Vite + TypeScript). La sirve el gateway en `/app/`. La app de escritorio la muestra dentro de su ventana mediante el plugin `cidia`: cada panel de su barra lateral es un `iframe` a `cidia/gw/app/<ruta>?embed=1`, en el mismo origen que la app, y el Host del plugin hace de proxy autenticado hacia el gateway (`/cidia/gw/*`). Así no hace falta CORS ni cookies de terceros, y actualizar el servidor actualiza la interfaz sin reinstalar nada en los portátiles. Desde un navegador también funciona en `http://servidor:puerto/app/`.
* **postgres**: núcleo de datos de CidIA (imagen `pgvector/pgvector:pg17`).
* **ollama**: modelos locales. Solo escucha en la red interna de Docker.
* **asr**: transcripción de voz propia compatible con `/v1/audio/transcriptions` (faster-whisper sin PyAV y ffmpeg LGPL como programa externo). No usamos la imagen de speaches porque incluye componentes GPL.
* **espacio-trabajo**: ejecuta las órdenes del agente en contenedores sin red, uno por petición, sobre la carpeta `generador-de-contenido/<usuario>/`.
* **Motor de conocimiento**: por defecto, el propio sobre PostgreSQL (pgvector + búsqueda de texto con la configuración `spanish` + fusión RRF), con los permisos aplicados en el propio SQL. **WeKnora** queda como perfil opcional (`--profile weknora`) detrás del mismo interfaz `MotorConocimiento`. Motivos (informe 03): su `docreader` incluye EbookLib (AGPL) y, con Qdrant, la búsqueda por palabras no usa BM25, lo que en castellano da peores resultados que nuestro índice de texto.

## 2. Repositorio

```
cidia/
  app/                      lo que se instala en los portátiles
    plugins/cidia/          plugin de la app (sesión, panel CidIA, marca, bloqueo de proveedores)
    perfil/                 perfil de la app: plugins activos y desactivados, ajustes
    marca/                  logos e iconos de CidIA
    instalador/             script NSIS y lanzador de CidIA-Setup.exe
  servidor/
    gateway/                servicio CidIA (paquete Python `cidia`)
    web/                    interfaz web (SPA)
    espacio-trabajo/        imagen y ejecutor de contenedores aislados
    asr/                    servicio de transcripción (si no se usa speaches)
    despliegue/             docker compose, perfiles por equipo e instalador del servidor
  datos-demo/               solo datos sintéticos de ejemplo
  docs/                     arquitectura, investigación y manuales
```

## 3. Gateway: paquete `cidia`

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Ajustes por variables de entorno (`CIDIA_*`). |
| `db.py` | Motor SQLAlchemy 2 (síncrono, controlador pg8000, BSD), sesión por petición, `Base`. No usamos psycopg porque es LGPL dentro del proceso. |
| `modelos.py` | Todas las tablas (ORM). Único fichero de esquema. |
| `seguridad.py` | Contraseñas (argon2), tokens JWT, dependencias `usuario_actual`, `requiere_rol`, URLs firmadas de ficheros. |
| `identidad/` | Módulo de identidad intercambiable: `base.py` (interfaz), `local.py` (cuentas en nuestra BD), `ldap.py` y `oidc.py` (conectores preparados). |
| `permisos.py` | Calcula el **alcance** de cada usuario: qué departamentos, niveles y material de formación puede encontrar. |
| `xapi.py` | Registro de actividad en formato xAPI. |
| `ia/llm.py` | Cliente OpenAI compatible: chat (con y sin streaming), JSON, visión y embeddings, siempre con modelos permitidos. |
| `ia/asr.py` | Transcripción de audio. |
| `ia/prompts.py` | Plantillas de prompts en castellano. |
| `conocimiento/` | Interfaz `MotorConocimiento` y sus dos motores: `pgvector.py` (propio) y `weknora.py`. Extracción de texto y troceado en `extraccion.py`. |
| `trabajos.py` | Cola de trabajos en segundo plano (hilos) con estado en BD. |
| `rutas/*.py` | Un router FastAPI por dominio; `main.py` los incluye todos automáticamente (cada módulo expone `router`). |
| `servicios/*.py` | Lógica de negocio por dominio, usada por rutas y herramientas MCP. |
| `mcp_servidor.py` | Herramientas MCP para el agente (`MCPServer` del SDK 2.x, streamable HTTP, sin estado, token validado antes de cada llamada). La protección de cabecera Host se configura con `CIDIA_MCP_HOSTS` (por defecto acepta cualquiera: la autenticación es por token). |
| `semilla.py` | Datos sintéticos de demostración. |

### Convenciones de la API

* Prefijo `/api`. JSON con nombres en castellano y `snake_case`.
* Autenticación: cabecera `Authorization: Bearer <token>`. Tipos de token: `usuario` e `invitado`.
* Errores: `HTTPException` con `detail` en castellano, pensado para mostrarse al usuario.
* Ficheros (imágenes, clips, descargas): URLs firmadas y caducables (`/api/ficheros/{ruta}?exp=…&firma=…`), porque `<img>` y `<video>` no envían cabeceras.
* Streaming: Server-Sent Events (`text/event-stream`) con eventos `fuentes`, `token`, `fin` y `error`.
* Toda acción relevante registra una sentencia xAPI; todo cambio de administración, una fila de `auditoria`.

## 4. Permisos

Cada documento tiene `departamento_id`, `nivel_minimo` (orden del nivel), `es_formacion` y `es_publico`.

Un usuario encuentra un documento si se cumple alguna de estas condiciones:

1. `es_publico`.
2. Es de **su departamento** y **su nivel** (orden) es mayor o igual que `nivel_minimo`.
3. Es `es_formacion` y es de un departamento en el que tiene una **formación activa**.
4. Su rol es `admin`.

Los invitados (sin sesión) solo encuentran documentos públicos. Si no hay acceso, el copiloto responde como si el documento no existiera. El alcance se calcula siempre en el servidor a partir de la sesión; el cliente nunca envía departamento ni nivel.

En WeKnora: una base de conocimiento por departamento más una base «Público»; etiquetas `n1`…`n4` y `formacion`. El gateway hace una búsqueda por cada elemento del alcance y fusiona los resultados con RRF. Además vuelve a filtrar los resultados contra la base de datos (defensa en profundidad).

## 5. Roles

| Rol | Puede |
|---|---|
| invitado | Chat general y documentos públicos, con límite de uso. |
| empleado | Su conocimiento, modo planta, formación, evaluación, aportaciones, progreso propio, espacio de trabajo, memoria. |
| empleado con `es_experto` | Además: captura, borradores de instrucciones y aprobación de preguntas de su departamento. |
| jefe | Además: validar aportaciones, subir y etiquetar documentos, observaciones, progreso y matriz ILUO de su departamento, lagunas. |
| admin | Todo: organización, empleados, documentos, modelos permitidos, registro, sistema. |

## 6. Flujos principales

* **Consulta con citas** (`servicios/consulta.py`): alcance → búsqueda híbrida → contexto numerado → respuesta en streaming con citas `[n]` → registro xAPI. Sin respaldo suficiente: respuesta honesta y **laguna** (se agrupan preguntas parecidas por similitud de embeddings).
* **Captura de vídeo** (`servicios/captura.py`): ffmpeg LGPL (audio y fotogramas) → transcripción con marcas de tiempo → cambios de escena (filtro `scdet` de ffmpeg; evitamos OpenCV, que lleva FFmpeg dentro del proceso) → el LLM propone pasos, críticos y riesgos → imagen y clip por paso → borrador de instrucción → el experto lo edita y lo publica → se indexa en la base de su departamento.
* **Aportaciones**: texto o nota de voz → transcripción → el LLM lo ordena en problema, causa y solución → el jefe valida, edita o rechaza → se publica como pregunta frecuente con autor y validador → el copiloto la cita.
* **Modo planta**: un paso por pantalla, confirmación de pasos críticos, pregunta por voz en el contexto del paso, foto final comparada con visión, registro de la ejecución y de las consultas por paso (curva de autonomía).
* **Evaluación**: cuestionario generado desde los pasos y aprobado por el experto; observación en el puesto con lista de comprobación de los pasos; ILUO recalculado con cada evidencia.

## 7. Reglas ILUO (ajustables en `empresa.config_iluo`)

| Nivel | Se alcanza cuando |
|---|---|
| I | Ha empezado el itinerario de la tarea (micro-lección vista, ejecución iniciada o formación activa que la incluye). |
| L | Cuestionario aprobado de la versión vigente y al menos 3 ejecuciones completadas. |
| U | L, observación aprobada por un supervisor y la última ejecución sin consultas en pasos críticos. |
| O | U y validado como formador por un jefe o experto. Sus aportaciones validadas constan como evidencia. |

Cada nivel caduca (12 meses por defecto). Al publicar una nueva versión de una instrucción, las personas con nivel en esa tarea quedan marcadas para reevaluación.

## 8. Despliegue

Manual paso a paso: `docs/manual-servidor.md`. Tras instalar, la herramienta `cidia` (estado, registros, actualizar, modelos, copias y restauración, puerto en la LAN y modo demo) administra el servidor. La demostración de 3 minutos está en `docs/guia-demo.md`.


`servidor/despliegue/` contiene el `docker-compose.yml` y un fichero de entorno por equipo (`perfiles/oracle.env`, `perfiles/msi.env`). `instalar-servidor.sh` deja cualquier Ubuntu con Docker listo como servidor CidIA: comprueba requisitos, instala Docker Engine y el soporte de GPU si hace falta, genera secretos, descarga imágenes y modelos, arranca los servicios, crea el administrador y muestra la dirección que hay que poner en el instalador de los portátiles.

## 9. App de escritorio

`app/` contiene el plugin `cidia`, las plantillas del perfil, la marca y el instalador. `CidIA-Setup.exe` extrae la app base oficial (sin ejecutar su instalador, que sustituiría una instalación existente) en `%LOCALAPPDATA%\Programs\CidIA`, crea un directorio de datos propio (`DSH_HOME`) con una capa de configuración que la interfaz no puede cambiar (sin telemetría ni analítica, sin actualizaciones automáticas, sin herramientas locales del agente, un único proveedor de modelos: el gateway, y un único MCP: el gateway) y un lanzador `CidIA.exe` que fija esas variables. Detalles en los informes 01 y 02 de `docs/investigacion/`.

## 10. Licencias

Solo dependencias con licencia permisiva (MIT, Apache-2.0, BSD, ISC, PostgreSQL) o LGPL como programa externo (ffmpeg). Cada dependencia nueva se anota en `THIRD_PARTY_NOTICES.md`. Decisiones tomadas por licencia: pg8000 en lugar de psycopg, servicio de voz propio en lugar de speaches, `scdet` de ffmpeg en lugar de PySceneDetect/OpenCV, Redis 7.2 (BSD) en lugar de 7.4+, PostgreSQL con pgvector en lugar de ParadeDB (AGPL).
