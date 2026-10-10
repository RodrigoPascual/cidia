# Avisos de terceros

CidIA se construye sobre piezas de código abierto con licencias que permiten su uso comercial, su redistribución y su sublicencia. Este fichero recoge cada componente, su licencia y cómo se usa. Antes de añadir una dependencia nueva se comprueba su licencia y se anota aquí.

## App de escritorio

| Componente | Licencia | Uso |
|---|---|---|
| DeepSeek Harness 0.2.0-rc.2 (app base, Electron) | MIT | Base de la app de escritorio. Se conserva su aviso de licencia en la carpeta de la app. Su nombre y marca no se usan en CidIA (normas de marca del proyecto). |
| Electron, Chromium y Node.js (dentro de la app base) | MIT y licencias de Chromium (BSD y otras); `ffmpeg.dll` de Electron, LGPL | Incluidos en la app base. Del ejecutable de Electron solo se cambian recursos de Windows (icono y datos de versión, con rcedit) y el nombre (`app\CidIA.exe`); el código, las DLL (también `ffmpeg.dll`) y el `app.asar` no se modifican. |
| LibreOfficeKit (`libreoffice-kit-win32-x64`, dentro de la app base) | MPL-2.0 | Incluido sin modificar por la app base para vistas previas de documentos. La MPL permite el uso comercial y la redistribución; si se modificara algún fichero suyo habría que publicar ese fichero. |
| NSIS | zlib/libpng | Genera `CidIA-Setup.exe` y el lanzador. |
| rcedit 2.0.0 (`github.com/electron/rcedit`, Copyright (c) 2013 GitHub Inc.) | MIT | Solo en la construcción (no se distribuye): pone el icono y los datos de versión de CidIA al ejecutable de la app (`app/instalador/marca-app.ps1`). Se descarga el `rcedit-x64.exe` del release oficial con sha256 fijado. |

## Servidor

| Componente | Licencia | Uso |
|---|---|---|
| FastAPI | MIT | API del gateway |
| Starlette | BSD-3-Clause | Base de FastAPI |
| Uvicorn | BSD-3-Clause | Servidor ASGI |
| SDK oficial de MCP para Python (`mcp`) | MIT | Servidor MCP del gateway |
| SQLAlchemy | MIT | Acceso a datos |
| pg8000 | BSD-3-Clause | Controlador de PostgreSQL |
| pgvector (extensión y biblioteca de Python) | PostgreSQL License / MIT | Búsqueda por vectores |
| PostgreSQL 17 (imagen `pgvector/pgvector`) | PostgreSQL License | Base de datos |
| Pydantic, pydantic-settings | MIT | Validación y configuración |
| PyJWT | MIT | Tokens de sesión |
| argon2-cffi | MIT | Contraseñas |
| HTTPX | BSD-3-Clause | Cliente HTTP |
| python-multipart | Apache-2.0 | Subida de ficheros |
| pypdf | BSD-3-Clause | Texto de PDF |
| python-docx, python-pptx, openpyxl | MIT | Texto de Office |
| Ollama | MIT | Servidor de modelos locales |
| faster-whisper, CTranslate2 | MIT | Transcripción de voz |
| ONNX Runtime | MIT | Detector de voz de faster-whisper |
| tokenizers, huggingface-hub | Apache-2.0 | Carga de modelos de voz |
| NumPy | BSD-3-Clause | Audio |
| Pillow | MIT-CMU (HPND) | Imágenes de los pasos de los datos de demostración |
| Fuentes DejaVu (paquete fonts-dejavu-core) | Licencia Bitstream Vera / dominio público | Texto con tildes en las imágenes de los pasos |
| FFmpeg (compilación LGPL de BtbN/FFmpeg-Builds) | LGPL-3.0 | Programa externo sin modificar para audio, fotogramas, escenas y clips. Código fuente en https://ffmpeg.org y https://github.com/BtbN/FFmpeg-Builds |
| Docker Engine | Apache-2.0 | Contenedores en el servidor |

### Caja de arena del espacio de trabajo del agente (imagen `cidia-sandbox`)

pandas, NumPy, contourpy y lxml (BSD-3-Clause); Matplotlib (licencia de Matplotlib, tipo PSF/BSD); Pillow (MIT-CMU); ReportLab 4.5 o posterior (BSD); cycler y kiwisolver (BSD); openpyxl, et_xmlfile, python-docx, fonttools, pyparsing, pytz, six y charset-normalizer (MIT); python-dateutil (BSD/Apache-2.0); packaging (Apache-2.0 o BSD-2-Clause); tzdata (Apache-2.0); typing_extensions (PSF-2.0). Dentro de la caja de arena hay además bash y utilidades de Debian, que se usan como programas independientes (GPL) y no se modifican ni se enlazan con CidIA. La lista y su comprobación están en `servidor/espacio-trabajo/README.md`.

### Opcionales (perfil `weknora`, no se despliegan por defecto)

| Componente | Licencia | Nota |
|---|---|---|
| WeKnora 0.8.2 (app y UI) | MIT | Motor de conocimiento alternativo |
| WeKnora docreader | MIT con dependencias de terceros | Incluye EbookLib (AGPL-3.0) y antiword (GPL-2.0). Por eso no forma parte del despliegue por defecto. |
| Qdrant | Apache-2.0 | Base vectorial de WeKnora |
| Redis 7.2 | BSD-3-Clause | Cola de WeKnora. Las versiones 7.4 y posteriores no se usan (licencias no libres). |

## Interfaz web

| Componente | Licencia |
|---|---|
| React, React DOM | MIT |
| React Router | MIT |
| lucide-react | ISC |
| react-markdown, remark-gfm | MIT |
| Vite, @vitejs/plugin-react, TypeScript | MIT / Apache-2.0 |
| Fira Sans (vía @fontsource) | SIL Open Font License 1.1 (paquete MIT) |

## Modelos

| Modelo | Licencia | Dónde |
|---|---|---|
| Ministral 3 8B | Apache-2.0 | MSI (modelo principal, con visión) |
| Qwen3-Embedding 0.6B | Apache-2.0 | Búsqueda por significado |
| Qwen3 0.6B, Qwen3.5 0.8B | Apache-2.0 | Solo pruebas en el servidor ARM |
| Whisper (faster-whisper base, small, large-v3-turbo) | MIT | Transcripción |

## Herramientas de vídeo (`herramientas/video/`, no se distribuyen)

Sirven solo para producir el vídeo de demostración; se descargan en `herramientas/video/.herramientas/` (fuera de git) y ninguna va dentro de CidIA. Detalle y comparación de voces en [`herramientas/video/README.md`](herramientas/video/README.md).

| Componente | Licencia | Uso |
|---|---|---|
| Kokoro-82M (hexgrad), voces em_alex y ef_dora | Apache-2.0 | Voz del vídeo, sintetizada en local |
| kokoro-onnx 0.6.1, ONNX Runtime | MIT | Ejecutar Kokoro |
| phonemizer 3.4, espeak-ng (en espeakng-loader, MIT) | GPL-3.0 | Texto a fonemas; se usan como programas aparte, el audio generado no queda sujeto a la GPL |
| NumPy, soundfile (libsndfile LGPL-2.1), Pillow | BSD-3-Clause / MIT-CMU | Audio, tarjetas y rótulos |
| Fira Sans en TTF (google/fonts) | SIL Open Font License 1.1 | Tipografía del vídeo |
| FFmpeg LGPL de BtbN con OpenH264 (BSD-2-Clause) y libass (ISC) | LGPL-3.0 | Grabación, montaje y codificación |
| Microsoft Edge sin cabeza (o Chromium) | Licencia de Microsoft / BSD | Dibuja la interfaz para grabarla |
| Piper 2023.11.14-2 y voz es_ES-carlfm-x_low | MIT / dominio público | Solo para comparar voces (las demás voces es_ES de Piper derivan de datos de licencia de investigación o NC y no se usan) |

## Descartados por licencia

ParadeDB (AGPL-3.0), speaches (incluye piper-tts y phonemizer, GPL-3.0), ruedas binarias de PyAV (incluyen x264/x265, GPL), ffmpeg de Debian/Ubuntu (GPL), psycopg (LGPL dentro del proceso), Redis 7.4 o posterior, Llama y Gemma (condiciones de uso propias), Open WebUI, Dify y FastGPT (cláusulas de marca o de uso), Zitadel y Permify (AGPL), Docker Desktop (propietario).
