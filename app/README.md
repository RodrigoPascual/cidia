# App de escritorio CidIA

Lo que se instala en los portátiles de la planta. La app de escritorio de CidIA es **DeepSeek Harness 0.2.0-rc.2** (MIT) configurada como producto, sin recompilarla:

* un **plugin** (`plugins/cidia`) que muestra la interfaz web de CidIA dentro de la app como secciones de la barra lateral, gestiona la sesión con el servidor de la empresa y pone la marca y el castellano;
* un **perfil** (`perfil/`) que fija la configuración del producto: sin telemetría, sin servicios de DeepSeek, un único proveedor de modelos (el servidor CidIA) y un modo de agente sin herramientas locales;
* un **lanzador** (`CidIA.exe`) y un **instalador** (`CidIA-Setup.exe`) propios, por usuario y sin permisos de administrador.

```
app/
  plugins/cidia/      plugin: Host (index.js), cliente (client.js), cordis.patch.yml,
                      idioma/es.json (castellano para la app), locale/ (metadatos), pruebas/
  perfil/             plantillas de configuración
    home/             capa home ($DSH_HOME/cordis.patch.yml) y .env.plantilla (se llama así
                      porque git ignora los .env; el instalador escribe $DSH_HOME/.env)
    profiles/desktop/ package.json (bundle cidia), cordis.patch.yml, pnpm-workspace.yaml
  marca/              logo (SVG), PNG, cidia.ico, imágenes del instalador y generar.py
  instalador/         construir.ps1, CidIA.nsi, lanzador.nsi, comun.nsh, perfiles/, textos/,
                      verificar.mjs (comprobación de una instalación por CDP)
                      salida/ (CidIA-Setup.exe, ignorada por git)
```

## 1. Cómo funciona

```
┌──────────────────────────── App CidIA (DeepSeek Harness 0.2.0-rc.2) ────────────────────────────┐
│ Renderer  dsh-app://app                                                                          │
│  client.js: marca · paneles (sidebar.panellist + main) · botón de sesión · idioma · título        │
│   └ cada panel: <iframe src="cidia/gw/app/<ruta>?embed=1">  (mismo origen: sin CORS)              │
│        la interfaz web guarda el token en localStorage 'cidia.token' y avisa con postMessage      │
│ Host (Node)  index.js                                                                            │
│   /cidia/gw/*    proxy en streaming al gateway (+ x-forwarded-prefix: /cidia/gw)                  │
│   /cidia/sesion  adopta el token de la interfaz / da uno de invitado / cierra sesión              │
│   credencial CIDIA_GATEWAY_TOKEN  → proveedor de modelos 'cidia' (gateway /v1)                    │
│   cliente MCP hijo (gateway /mcp) → se reconecta con el token de la persona                       │
└──────────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                               │ HTTP (red de la empresa, sin proxy)
                                    Servidor CidIA (gateway): /api · /app · /v1 · /mcp
```

* **Interfaz.** Es la SPA del gateway (`servidor/web`). Actualizar el servidor actualiza la interfaz sin reinstalar nada en los portátiles. El plugin crea una sección por servicio según `perfil.servicios` de `GET /api/auth/yo` (validado por el Host, nunca por el renderer):
  Inicio, Copiloto, Modo planta, Formación, Evaluación, Mi progreso, Aportaciones, Espacio de trabajo y, con permiso, Captura, Instrucciones, Documentos, Validar, Lagunas, Equipo y Administración. Sin sesión: Acceso y Copiloto. «Mi perfil» se abre desde el botón de sesión del pie de la barra lateral, que también cierra la sesión.
* **Sesión.** Al arrancar, el Host pide un token de invitado (`POST /api/auth/invitado`), lo renueva antes de que caduque y lo deja en `localStorage` para que el copiloto funcione sin iniciar sesión. Cuando la persona entra en la sección Acceso, la interfaz guarda su token; el plugin se lo pasa al Host, que lo comprueba en el servidor, fija la credencial del modelo (se resuelve en cada petición, sin recargar) y reinicia el cliente MCP con la nueva cabecera `Authorization` (`fiber.update`). Al cerrar sesión, el Host revoca el token en el servidor y vuelve a invitado.
* **Proxy.** `/cidia/gw/*` reenvía en streaming (subidas, descargas, SSE y rangos para vídeo), corta la petición al servidor si el renderer cancela, reescribe los `Location` para que no salgan del proxy y nunca reenvía la cookie de la app. Si la interfaz no manda `Authorization`, pone el token del Host. Usa `node:http`, sin el proxy corporativo: el servidor está en la red de la empresa (el lanzador añade su host a `NO_PROXY` para el modelo y el MCP, y manda todo lo demás a un sumidero local: ver §4).
* **Configuración del producto** (`perfil/home/cordis.patch.yml`, capa *home*: la interfaz no la puede cambiar): telemetría y analítica de producto apagadas; proveedores y búsqueda de DeepSeek apagados; modos de agente estándar, PTC, mínimo y Creator apagados y `preset-cidia` por defecto (persona en castellano, sin terminal, ficheros ni web); paneles de terminal, ficheros, navegador, «abrir en app», Creator, Plugins, Modelos y Cuenta apagados; marca oficial apagada; idioma `es`; proveedor único `cidia` (`openai-completions` contra `gateway/v1`, clave `CIDIA_GATEWAY_TOKEN`) y modelo por defecto; servidor web local en un puerto libre.
* **Marca e idioma.** Logo y nombre CidIA en la barra lateral y en el estado vacío del chat, título de la ventana «CidIA», idioma `es` registrado por el plugin con diccionarios para las partes más visibles de la app (lo que falta se ve en inglés).

## 2. Construir el instalador

Requisitos (en el equipo que construye): Windows 10/11 x64, Windows PowerShell 5.1, [7-Zip](https://www.7-zip.org) instalado, Node 22 (para las pruebas del plugin), conexión a Internet la primera vez y unos 3 GB libres.

```powershell
powershell -ExecutionPolicy Bypass -File app\instalador\construir.ps1                 # perfil «pruebas»
powershell -ExecutionPolicy Bypass -File app\instalador\construir.ps1 -Perfil empresa
powershell -ExecutionPolicy Bypass -File app\instalador\construir.ps1 -Rapido         # zlib: compila antes, ocupa más
```

En este PC: con LZMA, entre 9 y 16 minutos de compilación (según la carga del equipo) y un `CidIA-Setup.exe` de 243 MB; con `-Rapido`, unos 3 minutos y 361 MB. La primera vez se suman la descarga (289 MB) y la extracción (unos 40 s); después se reutilizan de la caché.

Qué hace `construir.ps1`:

1. Ejecuta las pruebas del plugin (`node --test`); `-SinPruebas` las omite.
2. Descarga el instalador **oficial fijado** `deepseek-harness-0.2.0-rc.2-win-x64.exe` (289 313 640 bytes) a la caché `%LOCALAPPDATA%\CidIA-construccion\cache` y comprueba tamaño, **sha512** (fijado en el script y contra el feed oficial `nightly.yml` mientras anuncie esa versión) y **firma Authenticode** de *Hangzhou DeepSeek Artificial Intelligence Co., Ltd.*
3. **No ejecuta el instalador oficial.** Extrae con 7-Zip `$PLUGINSDIR\app-64.7z` y de ahí la app (1,1 GB, 9 769 ficheros) a la carpeta de carga, borra `resources\app-update.yml` (sin actualizaciones automáticas) y vuelve a comprobar la firma de `DeepSeek Harness.exe`.
4. Copia a la carga el plugin (sin `pruebas/`), las plantillas del perfil, la marca y los textos (la licencia se convierte a UTF-16 para la página de NSIS).
5. Genera `plantillas.nsh`: cada plantilla de `perfil/` se convierte en una macro NSIS que escribe el fichero **en UTF-8** (NSIS solo escribe en la página de códigos del sistema; con rutas de usuario con tildes eso rompería el `package.json`). Los marcadores `{{MODELO}}`, `{{MODELO_NOMBRE}}` y `{{CONTEXTO}}` salen del perfil de construcción; `{{GATEWAY_URL}}` y `{{RUTA_PLUGIN}}` se rellenan al instalar.
6. Descarga **NSIS 3.11 portable** (zip oficial de SourceForge, licencia zlib, sha256 publicado y fijado) en `%LOCALAPPDATA%\CidIA-construccion\herramientas`, sin instalarlo, y compila `lanzador.nsi` → `CidIA.exe` y `CidIA.nsi` → `app\instalador\salida\CidIA-Setup.exe` (más su `.sha256`).

Perfiles de construcción (`instalador/perfiles/*.json`): `servidor` (dirección que propone el instalador), `modelo`, `modelo_nombre` y `contexto` (el modelo por defecto del proveedor `cidia`; su `id` debe ser uno de los que el gateway acepta en `/v1`). `pruebas` apunta al servidor de pruebas por el túnel SSH (`http://127.0.0.1:18700`, `qwen3:0.6b`); `empresa` es un ejemplo para una planta (`ministral-3:8b`).

Los iconos se regeneran con `marca/generar.py` (Pillow en un entorno aparte; ver la cabecera del script).

## 3. Instalar

* **Con ventanas**: `CidIA-Setup.exe`. Páginas en castellano: bienvenida, condiciones y licencias, **dirección del servidor CidIA** (con botón «Comprobar conexión», que consulta `/api/sistema/info`), carpeta, progreso y final («Abrir CidIA ahora»).
* **Sin ventanas**: `CidIA-Setup.exe /S /SERVIDOR=http://servidor-cidia:18700`. Si CidIA está abierta, termina con código 2.
* Vuelve a ejecutar el instalador para actualizar o cambiar de servidor: sustituye la app y el plugin, reescribe la configuración y conserva las conversaciones.

Qué deja en el equipo (todo en el usuario de Windows):

| Ruta | Contenido |
|---|---|
| `%LOCALAPPDATA%\Programs\CidIA\` | `app\` (app base sin `app-update.yml`), `plugins\cidia\`, `plantillas\`, `textos\`, `CidIA.exe`, `cidia.ico`, `Desinstalar CidIA.exe` |
| `%LOCALAPPDATA%\CidIA\datos\` (`DSH_HOME`) | `.env` (`CIDIA_GATEWAY_URL`, `CIDIA_LLM_URL`, `CIDIA_MCP_URL`, `CIDIA_GATEWAY_TOKEN` de arranque), `cordis.patch.yml` (capa home), `profiles\desktop\` (con `node_modules\cidia` como *junction* al plugin), conversaciones y caché |
| `%LOCALAPPDATA%\CidIA\navegador\` | datos de Chromium de la app (`--user-data-dir`) |
| `HKCU\Software\CidIA` | `Instalacion`, `Version`, `Servidor`, `Datos` |
| `HKCU\…\Uninstall\CidIA` | entrada «CidIA» en Aplicaciones instaladas |
| Escritorio y menú Inicio | acceso directo «CidIA» al lanzador |

Para cambiar de servidor sin reinstalar: edita las tres líneas `CIDIA_*_URL` de `%LOCALAPPDATA%\CidIA\datos\.env` y reinicia CidIA.

**Desinstalar**: desde Aplicaciones instaladas o `"%LOCALAPPDATA%\Programs\CidIA\Desinstalar CidIA.exe"`. Una página pregunta si borrar también los datos (sin marcar por defecto); sin ventanas: `/S` conserva los datos y `/S /BORRARDATOS` los borra. Quita primero el *junction* del perfil (nunca borra a través de él), después la instalación, los accesos directos y las claves del registro, y devuelve el protocolo `dsh://` a DeepSeek Harness si está instalada.

## 4. El lanzador `CidIA.exe`

Un acceso directo no puede fijar variables de entorno y la app base solo lee su carpeta de datos de `DSH_HOME`, así que los accesos directos abren el lanzador (sin ventana), que:

1. **comprueba y repara el perfil**: que `profiles\desktop\package.json` siga incluyendo el bundle `cidia` (el diálogo de recuperación tras un fallo de la app lo quita), que exista el *junction* al plugin y que estén `.env`, la capa home y `pnpm-workspace.yaml`;
2. fija `DSH_HOME=%LOCALAPPDATA%\CidIA\datos`, `DSH_TELEMETRY_DISABLED=1` y borra `CIDIA_GATEWAY_TOKEN` del entorno (si viniera de fuera, la credencial quedaría de solo lectura);
3. **limita la red de la app al servidor CidIA**: añade el servidor, `127.0.0.1`, `localhost` y `::1` a `NO_PROXY` y fija `NODE_USE_ENV_PROXY=1` con `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:9`, un «proxy sumidero» donde no escucha nadie. Así, lo que el proceso principal o el Host intenten sacar con `fetch` de Node fuera del servidor CidIA se rechaza al momento, en el propio equipo. Es lo que corta la consulta de la política de actualización obligatoria (§6), que no se puede apagar por configuración. Node 24 (Electron 44) solo aplica esas variables con `NODE_USE_ENV_PROXY=1`; Chromium no las lee en Windows, así que no afecta a la interfaz;
4. abre la app con `--user-data-dir=%LOCALAPPDATA%\CidIA\navegador`, que **aísla la instancia única** de Electron (comprobado: con DeepSeek Harness abierta, CidIA arranca como instancia propia y su `lockfile` queda en esa carpeta);
5. si el protocolo `dsh://` era de otra app, se lo devuelve en cuanto la app base lo registra a su nombre al arrancar.

Los argumentos que recibe pasan a la app (por ejemplo `CidIA.exe --remote-debugging-port=9333`).

## 5. Pruebas

* **Plugin** (sin la app ni red; `ctx` simulado con la forma de la 0.2.0-rc.2 y un gateway falso):

  ```
  cd app/plugins/cidia && node --test "pruebas/*.test.*"
  ```

  `host.test.mjs` (16 casos): valla de la app (401 sin cookie), token de invitado al arrancar, credencial y MCP; proxy con token del Host, sin cookie y con `x-forwarded-prefix`; `Authorization` de la interfaz respetada; cuerpo POST; base de la SPA y `Location` reescritos; SSE en streaming; rangos 206; cancelación propagada; adopción de la sesión de usuario sin devolver el token; tokens caducados o inválidos; cierre de sesión con revocación; renovación automática del invitado tras un 401; diccionario y rutas desconocidas; servidor caído (502 en castellano); descarga del plugin (ruta retirada y credencial borrada).
  `cliente.test.cjs`: React 18.3.1 real (de `servidor/web/node_modules`), marca con prioridad -10, título, invitado sembrado, paneles por servicio y su orden, vistas con el iframe correcto, mensajes de otro origen ignorados, inicio y caducidad de sesión, «Continuar sin sesión», aviso sin servidor, idioma y limpieza al descargar.
* **App instalada, sin interfaz gráfica**: lanzar `CidIA.exe --remote-debugging-port=9333` y ejecutar `node app/instalador/verificar.mjs [--captura captura.png]`. Usa el protocolo CDP (Node 22 tiene `WebSocket` nativo) sobre el destino `dsh-app://app/` y comprueba título, logo, idioma, secciones, `fetch('cidia/gw/salud')`, `fetch('cidia/estado')`, que el `iframe` carga la interfaz con `<base href="/cidia/gw/app/">` y que la credencial `CIDIA_GATEWAY_TOKEN` del Host es el token de la sesión de la interfaz (compara huellas SHA-256, nunca imprime tokens; `--datos` cambia la carpeta `DSH_HOME`); con `--captura` guarda un `Page.captureScreenshot`.
* **Comprobado en este PC** (con la DeepSeek Harness del usuario abierta todo el rato): instalación silenciosa y reinstalación encima; arranque como instancia propia (`lockfile` en `CidIA\navegador`); marca, título «CidIA» e interfaz de la app en castellano; secciones Acceso y Copiloto sin sesión con la interfaz web cargada por el proxy (`<base href="/cidia/gw/app/">`); `fetch('cidia/gw/salud')` → `{"estado":"ok"}`; «Continuar sin sesión» adoptado por el Host (credencial reescrita); conversación nueva con el modo CidIA y el modelo del perfil; ninguna conexión del Host fuera del servidor CidIA; desinstalación con `/S /BORRARDATOS` que deja el equipo limpio; `~/.dsh`, el perfil de Chromium y el protocolo `dsh://` de DeepSeek Harness sin cambios.
* **Comprobado con sesión** (10/10/2026, `CidIA-Setup.exe` reconstruido e instalado encima de la versión anterior con `/S`, código 0, unos 160 s, conserva datos y *junction*): inicio de sesión en la sección Acceso con la cuenta de administración del servidor de pruebas; el Host adopta el token (modo `usuario`), la barra lateral pasa de Acceso y Copiloto a las 15 secciones que da `perfil.servicios` de una cuenta `admin` (Inicio, Copiloto, Modo planta, Formación, Evaluación, Mi progreso, Aportaciones, Espacio de trabajo, Captura, Instrucciones, Documentos, Validar, Lagunas, Equipo, Administración) y se abre Inicio; los iframes de Inicio, Formación y Administración cargan la interfaz (`…/cidia/gw/app/<ruta>?embed=1`); la credencial `CIDIA_GATEWAY_TOKEN` del Host es el token de la sesión (misma huella SHA-256; `verificar.mjs` lo comprueba); el cliente MCP se reinicia con la cabecera nueva (en el registro del gateway, `POST /mcp` justo después de `POST /api/auth/login` y `GET /api/auth/yo`); al reiniciar la app la sesión sigue abierta; «Cerrar sesión» en el botón del pie vuelve a invitado (Acceso y Copiloto, credencial con el token de invitado nuevo) y el token anterior queda revocado (401). Red: con el lanzador nuevo, ninguna conexión de los procesos de CidIA fuera del equipo durante 100 s de arranque y sesión (con el anterior, una a CloudFront por la política de actualización, ver §6); el MCP y el proxy siguen llegando al servidor.

## 6. Limitaciones conocidas

* **Textos y marca del proceso Electron en inglés** hasta el rebrand compilado de la fase 4: menú («Application», «Edit»), «Acerca de», icono de la bandeja, diálogos de salida, recuperación y actualización, ventana de bienvenida y de actualización obligatoria; el ejecutable y los procesos se llaman «DeepSeek Harness.exe» y las ventanas pueden agruparse con DeepSeek Harness en la barra de tareas. Dentro de la interfaz de la app, lo que no está en `idioma/es.json` se ve en inglés (p. ej. partes de Ajustes y del detalle de las herramientas).
* **Política de actualización obligatoria (cortada por el lanzador).** La app base trae en el `package.json` de su `app.asar` la clave `dshMandatoryUpdatePolicy` (`origin: https://harness.deepseek.com`, anónima). En una app empaquetada solo se lee de ahí (la variable `DSH_DESKTOP_MANDATORY_UPDATE_CONFIG` solo vale en desarrollo), así que no se puede apagar por configuración; quitarla exigiría modificar el `app.asar` de la app base (sería posible, porque el fusible `EnableEmbeddedAsarIntegrityValidation` de Electron está apagado, pero se descarta para no alterar la app base antes de la fase 4). Al arrancar y luego cada 10 minutos (hasta 1 hora si falla), el **proceso principal** hace `GET https://harness.deepseek.com/api/v0/check_client_update?scenario=launch|periodic` con `fetch` de Node, sin cookies, enviando plataforma, arquitectura, versión de la app y de dsh, canal (`nightly`), idioma y huso horario; si DeepSeek respondiera `code: 40005`, bloquearía la app con su ventana de actualización obligatoria. Es la conexión a **3.173.21.63:443** que se vio al vigilar la red: es un nodo de CloudFront (`harness.deepseek.com` es un CNAME de `d3bbv8sr76az5s.cloudfront.net`, igual que `api.deepseek.com` y `chat.deepseek.com`), no analítica ni telemetría (esas viven en el Host y están apagadas). **Solución aplicada**: el lanzador manda el `fetch` de Node a un proxy sumidero local (§4, paso 3); la consulta falla en el propio equipo y, sin respuesta, la app no se bloquea. Comprobado: con el sumidero, ninguna conexión de CidIA sale del equipo (antes, la de CloudFront en cada arranque) y la app, la sesión y el MCP siguen funcionando. Como defensa adicional, la planta puede bloquear `harness.deepseek.com` y `download.deepseek.com` en su cortafuegos. Solución definitiva en la fase 4 (compilar sin política). Si se abre `DeepSeek Harness.exe` directamente, sin el lanzador, la consulta vuelve a salir.
* **Puerto del servidor local.** La 0.2.0-rc.2 arranca su servidor local siempre en `127.0.0.1:19387` (el informe 01 citaba el puerto aleatorio de la 0.2.1-alpha.1). Con DeepSeek Harness abierta, CidIA fallaba al arrancar (`EADDRINUSE`); la capa home pone `port: 0` en la fila `webserver` y la app usa el puerto que le da el sistema.
* **Micrófono en las secciones.** Electron solo concede el micrófono al marco principal de la app, nunca a un `iframe`, y la cámara a nadie. El plugin ya graba por la interfaz embebida (mensajes `cidia:microfono`: `empezar`, `parar`, `cancelar`; responde `grabando`, `lista` con el `Blob` de audio, `cancelada` o `error`), pero `useGrabadora` de la SPA aún tiene que usar ese puente cuando va embebida (cambio pendiente en `servidor/web/src/ui`).
* **Enlaces** con `target="_blank"` a rutas del propio servidor no abren ventana nueva (la app solo abre fuera los `http(s)`); las descargas deben hacerse con `download` o `Content-Disposition`.
* **Seguridad en el equipo.** El token de la sesión vive en `localStorage` (la interfaz) y en `$DSH_HOME\.credentials.yaml` (referencia `CIDIA_GATEWAY_TOKEN`, para el modelo). Al salir de la app no se borra de este último: la app termina el Host sin darle tiempo a retirar la credencial, así que queda hasta el siguiente arranque (el Host la reescribe al empezar) o hasta cerrar la sesión, igual que la sesión guardada en `localStorage`, que es la que permite volver a entrar sin contraseña. Ambos están en la carpeta del usuario de Windows. «Cerrar sesión» revoca el token en el servidor (comprobado: después responde 401). F12 abre las herramientas de desarrollo. Los permisos reales los aplica siempre el gateway.
* **Selector de permisos** del chat («Espacio de trabajo») sigue visible aunque el modo CidIA no tiene herramientas locales; el «Espacio predeterminado» de la app apunta a `Documentos\deepseek-harness\default-workspace` (el mismo nombre que usa DeepSeek Harness), aunque CidIA no escribe en él.
* **Sin firma de código**: `CidIA-Setup.exe` y `CidIA.exe` no están firmados, Windows SmartScreen puede avisar la primera vez. La app base sí conserva la firma de DeepSeek.
* **Versión fijada**: dsh es *alpha*; el plugin declara `@deepseek-ai/dsh-mcp-client` `0.2.0-rc.2` exacta y la construcción comprueba el sha512 fijado. Cada cambio de versión exige repetir las pruebas.
* **Disco**: 1,1 GB la instalación y unos 10 MB los datos del navegador.
