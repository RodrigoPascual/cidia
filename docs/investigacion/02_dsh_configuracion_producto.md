# 02 · DeepSeek Harness como producto CidIA: configuración

Investigación para dejar la app de escritorio de DeepSeek Harness (dsh) configurada como **producto CidIA** sin recompilarla (fase 1). Objetivos: instalación aislada, sin telemetría ni actualizaciones, proveedores bloqueados, sin herramientas locales del agente, plugins preinstalados y en castellano.

## 0. Fuentes, versiones y convenciones

| Fuente | Detalle |
|---|---|
| Código fuente | Clon superficial del tag `dsh-v0.2.1-alpha.1` (commit `5badb15`) en `scratchpad/deepseek-harness`. Las rutas del tipo `apps/...` y `packages/...` son relativas a ese clon. |
| App instalada | 0.2.0-rc.2 en `%LOCALAPPDATA%\Programs\DeepSeek Harness`. La leí **solo en lectura** extrayendo ficheros concretos de `resources/app.asar` con un lector propio de solo lectura (`scratchpad/tools/asar-read.mjs`). |
| Perfil del usuario | `~/.dsh/profiles/desktop/{package.json,cordis.patch.yml}`, solo en lectura. No se imprimió ningún secreto. |
| Plugin propio | `03_MVP/plugins/cidia-proveedores` (client.js, index.js, suscripcion/index.js). |
| Red | `curl -I` y lectura del feed `nightly.yml` (unos pocos bytes). **No se descargó el instalador.** |

Marcas que uso en el informe:
- **[V]**: verificado en el código o en el sistema, con ruta y línea.
- **[V-rc2]**: verificado además en la 0.2.0-rc.2 instalada.
- **[I]**: inferencia. Hay que probarlo.
- **[P]**: prueba propuesta para la fase siguiente.

**Diferencias entre la rc.2 y la alpha.1 relevantes aquí.** La alpha.1 añade estas filas: `schedule`, `ui-schedule`, `tool-schedule` y `time-context` en el preset estándar. Comparé los identificadores de fila de `dsh-base` y `dsh-web-app`, y por lo demás coinciden. Comprobé en el `app.asar` de la rc.2 que todos los mecanismos de este informe existen con el mismo comportamiento:
- `DSH_HOME`, el bloqueo de instancia única, `app-update.yml` y `check_client_update`;
- la capa *home* `cordis.patch.yml` y `DSH_TELEMETRY_DISABLED`;
- las filas de analítica de producto;
- `addLanguage`, `mcp-client` con `streamable-http`, el evento `credentials/reference-updated` y el rechazo de escrituras que una capa *home* anula.

---

## Resumen ejecutivo

| # | Pregunta | Respuesta corta |
|---|---|---|
| 1 | ¿Respeta `DSH_HOME`? ¿Segunda instancia? | **Sí** respeta `DSH_HOME` [V-rc2]. El ejecutable de escritorio **no acepta ningún argumento** para elegir el directorio de datos; solo lee la variable de entorno. Un `.lnk` no puede fijar variables, así que hace falta un **lanzador**. El bloqueo de instancia única **no depende de `DSH_HOME`**: es de Electron y va por el directorio `userData` (`%APPDATA%\@deepseek-ai\dsh-desktop`), que comparten la app oficial y una CidIA lanzada desde el mismo ejecutable. |
| 2 | Telemetría y actualización | `DSH_TELEMETRY_DISABLED` (cualquier valor no vacío) **solo apaga `session-telemetry-otel`**. La **analítica de producto** del escritorio (`desktop-product-telemetry` y `product-analytics`) sigue activa y hay que desactivarla aparte por patch [V]. **No hay variable para la actualización**. Se apaga si falta `resources/app-update.yml`. La **política de actualización obligatoria** (`harness.deepseek.com`) va dentro del `app.asar` y **no se puede desactivar por configuración** [V-rc2]. |
| 3 | Herramientas locales | Las herramientas viven en los **presets de agente** (`preset-standard`, `-ptc`, `-minimal`, `-cordis`). Hay que desactivar los cuatro, insertar un `preset-cidia` sin shell, ficheros ni web, y apagar las filas de interfaz que actúan sobre el PC: terminal, ficheros, navegador, «abrir en app», Creator y gestor de plugins. Lista exacta en §3. **Excepción:** el propio Host de escritorio monta en la raíz la herramienta `load_workspace_dependencies`, que **no se puede quitar por patch** (§3.1). |
| 4 | Proveedor único | `llm-pi-ai` con una única ruta `cidia` (`openai-completions`, `baseURL` del gateway, `apiKeyEnv`). Hay que desactivar `llm-deepseek`, `llm-deepseek-account` y `web-search-deepseek`, y ocultar la página de Modelos desactivando `ui-settings-models`. Si se fija en la capa *home* (`$DSH_HOME/cordis.patch.yml`), la interfaz **no puede cambiarlo** [V]. |
| 5 | MCP y token en caliente | La fila `@deepseek-ai/dsh-mcp-client` admite `transport: streamable-http`, `url` y `headers` [V-rc2]. La **apiKey** del proveedor se resuelve en cada petición mediante `ctx.credentials`. Con `credentials.set` basta, **sin recargar** [V]. Las **cabeceras MCP no son *volatile***: `settings.mutate` no las alcanza. Hay que reiniciar la fila: un *child plugin* con `fiber.update` o `configEditor.edit`, que además escribe el token en disco. |
| 6 | Preinstalar plugins sin CLI | Hay que escribir `package.json` (dependencia `link:` + `dsh.profile.bundles`), crear la *junction* `node_modules/<pkg>` y añadir `cordis.patch.yml` **antes del primer arranque**. El escritorio nunca sobrescribe ficheros que ya existen. Es exactamente el patrón que ya funciona con `cidia-proveedores` [V]. |
| 7 | Instalador oficial | **NSIS de electron-builder**, **solo por usuario**, en `%LOCALAPPDATA%\Programs\DeepSeek Harness`, con `/S` silencioso. Ocupa **289 313 640 B** (0.2.0-rc.2) y no hay versión para Linux ni ARM. Si se instala en otra carpeta, **desinstala la instalación previa**, porque usa la misma clave de registro [V]. |
| 8 | Castellano | La interfaz web admite **paquetes de idioma** por plugin: `ctx.locale.addLanguage({id:'es',…})` más diccionarios por espacio de nombres [V-rc2]. El idioma se fija con la fila `locale` → `preference: es`. Quedan en **inglés y con la marca DeepSeek** los menús, la bandeja, «Acerca de», los diálogos y la ventana de bienvenida del proceso Electron, y el instalador. Eso no cambia hasta la fase 4. |

---

## 1. Directorio de datos aislado e instancia única

### 1.1 `DSH_HOME` [V-rc2]

- `packages/util/home-paths/src/index.ts:17-18` define `DSH_HOME_ENV = 'DSH_HOME'`. En las líneas 87-91, `resolveDshHome()` sigue esta precedencia: una ruta explícita, luego `$DSH_HOME` (no vacía) y por último `~/.dsh`.
- `apps/desktop/src/paths.ts:17-21` es el proceso principal de Electron. Toma el perfil de `join(resolveDshHome(), 'profiles', 'desktop')` y crea el bloqueo `profiles/desktop/lock`. `main.ts:320` lo llama sin argumentos, así que lee `process.env`.
- El Host hereda el entorno del proceso Electron. En Windows no lee ningún *login shell* (`login-shell-environment.ts:176`: `if (platform === 'win32') return { environment: base … }`) y `main.ts:444-445` le pasa `{ ...hostEnvironment, DSH_CLIENT_VERSION }`. El Host vuelve a resolver `DSH_HOME` en `apps/desktop-host/src/index.ts:10,98`.
- Dentro de `DSH_HOME` cuelga todo lo de usuario:
  - `profiles/desktop`, `.credentials.yaml`, `.env`;
  - `cordis.patch.yml` (capa *home*), `sessions`, `storages`, `attachments`, `cache`;
  - `.anonymous-user-id` y `dsh-runtimes/`.
  
  `dsh-runtimes/` es una copia del runtime principal (Python, Node y pnpm) de **unos 289 MB por cada `DSH_HOME`** (`desktop-host/src/index.ts:95-99`; lo medí en `~/.dsh`). *Corregido en la verificación:* la copia **no se hace al arrancar**. La hace la herramienta `load_workspace_dependencies` la primera vez que el agente la llama (`packages/skill/tool-workspace-dependencies/README.md`: «copied under the Harness home on first use»; `src/index.ts:249-266`). Si el agente nunca la usa, ese directorio no aparece.
- **Las variables `DSH_*` no pueden venir de un `.env`.** `packages/boot/app-boot/src/index.ts:157` (`BOOTSTRAP_PREFIXES = ['DSH_', …]`) y las líneas 207-220 lanzan un error si un `.env` las define. Tienen que estar en el **entorno heredado** del proceso. El error **impide arrancar**: el `.env` de CidIA no debe contener ningún `DSH_*`, `XDG_*` ni los nombres de `BOOTSTRAP_NAMES` (líneas 133-154, entre ellos `PATH`, `NODE_OPTIONS`, `DEEPSEEK_BASE_URL` y `SSL_CERT_FILE`). La única excepción son `HTTP(S)_PROXY`, `ALL_PROXY` y `NO_PROXY`, que se admiten en el `.env` del *home* (línea 166).

### 1.2 Cómo lanzar CidIA con su propio `DSH_HOME`

- `main.ts` solo inspecciona `process.argv` para `--updated` (línea 346). **No existe** ningún argumento para elegir el directorio de datos.
- Un acceso directo `.lnk` de Windows **no puede** fijar variables de entorno. Hay tres opciones:

| Opción | Cuándo | Notas |
|---|---|---|
| **Lanzador `CidIA.exe`** que fija las variables y ejecuta la app | Fase 1, en cualquier PC | Recomendado. Lleva icono y nombre de CidIA y no abre ventana de consola. |
| Variable de usuario persistente `HKCU\Environment\DSH_HOME` | PCs de empresa donde solo está CidIA | Cubre también los arranques que no pasan por el lanzador: el enlace `dsh://` con la app cerrada y «Ejecutar al terminar» del instalador. `app.relaunch()` (`main.ts:103,963`) y el reinicio tras actualizar parten del propio proceso, así que **probablemente heredan** ya el entorno del lanzador [I: comportamiento de Electron/NSIS, sin probar]. **En este PC rompería la DeepSeek Harness del usuario.** El desinstalador oficial respeta un `DSH_HOME` publicado así y no lo borra (`apps/desktop/installer/uninstall.nsh:23-24`). |
| `cmd /c "set DSH_HOME=…&& start "" "…\DeepSeek Harness.exe""` | Solo para pruebas | Abre una ventana de consola. |

Este lanzador se genera con el propio NSIS que usaremos para `CidIA-Setup.exe` [I]. Lo compilé mentalmente, no lo he ejecutado. Se basa en que `SetEnvironmentVariable` cambia el entorno del proceso y `Exec` lo hereda:

```nsis
; lanzador.nsi -> CidIA.exe (sin ventana, sin privilegios)
Unicode true
Name "CidIA"
OutFile "CidIA.exe"
Icon "cidia.ico"
RequestExecutionLevel user
SilentInstall silent

Section
  System::Call 'kernel32::SetEnvironmentVariable(t "DSH_HOME", t "$LOCALAPPDATA\CidIA\datos")i.r0'
  System::Call 'kernel32::SetEnvironmentVariable(t "DSH_TELEMETRY_DISABLED", t "1")i.r0'
  Exec '"$LOCALAPPDATA\Programs\CidIA\app\DeepSeek Harness.exe"'
SectionEnd
```

La ruta del `Exec` corresponde a la opción B de §7, la extracción portable. Con la opción A, el instalador oficial con `/S`, sería `$LOCALAPPDATA\Programs\DeepSeek Harness\DeepSeek Harness.exe`. **El lanzador no debe fijar `CIDIA_GATEWAY_TOKEN` en el entorno.** Si lo hace, ese valor tapa al almacén de credenciales y `credentials.set` lo rechaza (§5.2).

### 1.3 ¿El bloqueo de instancia única es por `DSH_HOME`?

**No.** Hay dos bloqueos distintos:

1. **Bloqueo de instancia única de Electron, de por vida y global.** `main.ts:1336` llama a `claimDesktopSingleInstance(app, …)` y `single-instance.ts:20-24` a `app.requestSingleInstanceLock()`. Si otro proceso tiene el bloqueo, el segundo hace `app.quit()` y el primero recibe `second-instance` y se enfoca.
   - Chromium ata ese bloqueo al **directorio `userData`** [I: comportamiento de Electron/Chromium, *ProcessSingleton*]. Lo confirma lo que vi en el sistema: existe `%APPDATA%\@deepseek-ai\dsh-desktop\lockfile`.
   - El nombre sale de que el `package.json` empaquetado no tiene `productName` y `name` es `@deepseek-ai/dsh-desktop` (`app.asar:package.json`). También cuadra con `uninstall.nsh:28-31` y con el comentario de `main.ts:937`.
   - **Consecuencia:** con el mismo ejecutable y el mismo `userData`, **CidIA y la DeepSeek Harness oficial no pueden abrirse a la vez** en la misma cuenta de Windows. Al abrir la segunda solo se enfoca la primera.
2. **Bloqueo de operaciones de perfil, por `DSH_HOME`.** Es `DSH_HOME/profiles/desktop/lock` (`project-manager.ts:93-130`) y solo dura mientras se aplica la versión al arrancar o durante la recuperación.

Hay dos salidas para aislar también el `userData`:
- **`--user-data-dir=<dir>`**: es un *switch* de Chromium que Electron no documenta como soportado **[P: primera prueba]**. Si en `<dir>` aparece un `lockfile`, funciona y se pueden tener las dos apps abiertas.
- **Fase 4**: compilar con otro `name`/`productName`/`appId`, que da otro `userData` y otra clave de registro.

En los PCs de empresa, donde solo estará CidIA, esto no importa.

---

## 2. Telemetría y actualizaciones

### 2.1 Telemetría: hay tres filas, no una [V-rc2]

| Fila (bundle) | Qué envía | Cómo se apaga |
|---|---|---|
| `session-telemetry-otel` (`dsh-base`, `base/cordis.patch.yml:204-218`) | La sesión, **solo al enviar feedback** (modo `FEEDBACK_ONLY` por defecto, `packages/session/session-telemetry-otel/src/index.ts:33-39`), a `https://dsh-otel-collector.deepseeksvc.com/v1/logs`. | `DSH_TELEMETRY_DISABLED=<cualquier cosa no vacía>`: `packages/boot/app-boot/src/profile-context.ts:39-55` genera el patch `{id: session-telemetry-otel, disabled: true}` y `profile-boot.ts:294` lo aplica también en el escritorio. Equivalentes: `DSH_TELEMETRY_MODE=DISABLED`, o el patch `disabled: true`. |
| `desktop-product-telemetry` (`web-app/cordis.patch.yml:45-55`, solo con el perfil `desktop`) | El exportador OTLP de analítica de producto. Por defecto apunta a `https://dsh-otel-collector.deepseeksvc.com/v1/logs` (`packages/host/product-telemetry-otel/src/index.ts:47`). | **No le afecta `DSH_TELEMETRY_DISABLED`.** Hay que poner `disabled: true`. |
| `product-analytics` (`web-app/cordis.patch.yml:57-62`, `enabled: true`) | Eventos de uso **activados por defecto y sin interruptor en la interfaz**: `desktop_app_launch`, `send_button_click`, `model_switch`, `plugin_install_click` y otros. Van con `device_id`, `user_id`, `app_version` y `os_version` (`packages/client/product-analytics/src/index.ts:81-100`, `src/events.ts`). | `disabled: true`. **Desactivarla no rompe nada.** El escritorio lo tolera (`main.ts:456` `analyticsEnabled().catch(() => false)`; `account-backend.ts:115-118` pone `false` ante cualquier marco que no sea `item`), y la interfaz llama siempre con `ctx.get('productAnalytics')?.track(...)` (comprobado en `ui-chat`, `ui-conversation`, `ui-model-selection`, `ui-plugin-manager`, `ui-sidebar`, `ui-workspace`, `ui-settings-account` y `ui-settings-models`). |

Otros orígenes de red que conviene conocer:
- `deepseek-account` habla con `platform.deepseek.com` **solo** si alguien inicia sesión con DeepSeek o hay una sesión guardada. Las líneas 53-56 de `packages/credentials/deepseek-account-platform/src/index.ts` solo fijan los orígenes por defecto. El comportamiento está en otras líneas: `Service.init` y `getState` son locales (167-190), y los accesos a red (`getProfile`, saldo, bonos) devuelven `null` sin llamar a la red si `readCurrentGrant` no encuentra una concesión guardada (192+). El inicio de sesión está en 403+.
- `web-search-deepseek` va a `api.deepseek.com` (§4).
- La actualización y la política obligatoria se ven en §2.2.

### 2.2 Actualización automática [V-rc2]

- **No hay variable de entorno para desactivarla.** El comprobador solo está activo si `app.isPackaged && existsSync(join(process.resourcesPath, 'app-update.yml'))` (`apps/desktop/src/update-coordinator.ts:54`). Se configura con `autoDownload=false`, `autoInstallOnAppQuit=false` y canal `nightly` (líneas 67-72), así que no instala nada en silencio: **pregunta al usuario**.
- Comprueba al arrancar, al recuperar el foco y al reanudar, y cada 10 min por defecto (`update-schedule.ts:19-27`; `main.ts:914-918,1070,1325`). `DSH_DESKTOP_UPDATE_CHECK_INTERVAL_MS` (máximo 2 147 483 647) solo espacia las comprobaciones. La primera se hace igualmente, porque `nextCheck = -Infinity`.
- **Forma de desactivarla en una instalación propia de CidIA:** borrar `resources\app-update.yml`. En este PC contiene `provider: generic`, `url: https://download.deepseek.com/dsh-desk/feeds/win-x64/` y `channel: nightly`. No toqué la instalación del usuario.
- **Política de actualización obligatoria** (`apps/desktop/src/mandatory-update-policy.ts`; `main.ts:1284-1324`):
  - Se lee del `package.json` **dentro del `app.asar`**. En la rc.2 es: `"dshMandatoryUpdatePolicy": {"origin": "https://harness.deepseek.com", "allowedPageOrigins": ["https://harness.deepseek.com"], "authentication": "anonymous"}`. *Corregido en la verificación:* la versión anterior del informe omitía `allowedPageOrigins`, que es obligatorio (`resolveDesktopPolicyConfig` lanza un error sin él: `mandatory-update-policy.ts:58-60`).
  - Al arrancar, al recuperar el foco y al reanudar, y cada 10 min (`intervalMs` 600 000, con *backoff* de hasta 1 h), consulta `GET /api/v0/check_client_update?scenario=…`. Envía las cabeceras de plataforma, arquitectura, canal `nightly` y versión del runtime (líneas 158-163, 187-190). Si DeepSeek responde `code: 40005`, **bloquea la app** con la ventana de actualización obligatoria (`mandatory-update-policy.ts:112-125`).
  - Si la red falla, **no bloquea un arranque nuevo**: el estado pasa a `error: 'unavailable'` (líneas 201-205). *Matiz de la verificación:* un bloqueo ya recibido **se mantiene** aunque después falle la red, mientras dure el proceso (comentario de la línea 25 y `...this.current` en la 204). El estado solo vive en memoria y se pierde al reiniciar.
  - `DSH_DESKTOP_MANDATORY_UPDATE_CONFIG` solo se lee **sin empaquetar** (`main.ts:1286`).
  - **No hay forma de apagarla por configuración.** Hay dos mitigaciones:
    - bloquear la salida a `harness.deepseek.com` y `download.deepseek.com`, con cortafuegos o *hosts* gestionado por IT, o como mínimo en la red de la demo;
    - en la fase 4, compilar sin política. `createElectronBuilderConfig` la exige siempre: `apps/desktop/scripts/electron-builder-config.mjs:54` llama a `resolveDesktopPolicyEnvironment` (`apps/desktop/scripts/desktop-policy-environment.mjs:18-44`), que falla sin el origen. Hay que parchear el *build*.
    - *Añadido en la verificación:* `electron-builder-config.mjs:233-236` declara un destino `linux: AppImage`. Pero con la política configurada, `main.ts:1297` lanza `desktop policy: unsupported platform` en cualquier sistema que no sea win32/darwin x64/arm64, y el constructor (`mandatory-update-policy.ts:153-154`) rechaza Windows que no sea x64. Un escritorio Linux o Windows ARM **solo arrancaría compilado sin política** [I: deducido del código, sin compilar].

---

## 3. Desactivar las herramientas locales sin romper la interfaz

### 3.1 Dónde están las herramientas [V-rc2]

- En el perfil web/escritorio, `dsh-web-app` **desactiva en la raíz** las filas de herramientas del agente (`tool-bash`, `tool-pwsh`, `tool-fs`, `tool-fs-search`, `tool-jobs`, `tool-web`, `tool-skill`, subagentes, `workflow`…; `web-app/cordis.patch.yml:465-575`). Después **cada preset de agente las vuelve a montar** en su propio ámbito (`web-app/presets/*.patch.yml`).
- En la rc.2 hay cuatro presets, y el registro tiene `default: standard` (`web-app/cordis.patch.yml:580-583`):

| Preset | Qué incluye |
|---|---|
| `preset-standard` | bash/pwsh, fs, búsqueda, jobs, skills, web, subagentes, workflow, `present` |
| `preset-ptc` | Igual que standard, más presentación PTC |
| `preset-minimal` | **Terminal PTY persistente** (`dsh-terminal`, `tool-bash-persistent`/`tool-pwsh-persistent`) |
| `preset-cordis` (Creator) | Igual que standard, más `tool-cordis` y skills de desarrollo de plugins |

- Las filas de preset viven dentro de `config.plugins` de cada preset. **No se pueden parchear una a una por `id`** desde el perfil (`presets/standard.patch.yml:1-3`). Lo limpio es **desactivar los cuatro presets e insertar `preset-cidia`**. *Verificación:* lo confirma `applyEntryPatches`, que solo indexa por `id` las filas raíz y los hijos de filas `group: true` con `config` de tipo lista (`vendor/include/src/index.ts:66-73`). El hijo de un `agent-preset` está en `config.plugins`, no en `config`, así que un patch por `id` nunca lo alcanza.
- Las herramientas MCP de una fila `mcp-client` en la raíz se registran en la capa global de `tools` y **las heredan todos los agentes** (`packages/core/tools/README.md:83`).
- **Herramienta global que no se puede quitar por patch** (*añadido en la verificación*, [V-rc2]). El Host de escritorio no monta `desktop-office` como fila del perfil. Lo monta por código sobre su contexto raíz: `apps/desktop-host/src/index.ts:95-99` → `office.ts:28-36`, y en la rc.2 `dsh-desktop-host/lib/index.js:76,326`. Con él llegan:
  - `@deepseek-ai/dsh-tool-workspace-dependencies`, que registra la herramienta **`load_workspace_dependencies`** en la capa global (`packages/skill/tool-workspace-dependencies/src/index.ts:249`). Por lo tanto también la ve el agente de `preset-cidia`. Solo devuelve rutas del Python/Node empaquetado y versiones, pero la primera llamada copia unos 289 MB a `DSH_HOME/dsh-runtimes`.
  - Las *skills* de Office (`dsh-skill-office`, registradas como proveedor del registro `skills`). Sin `tool-skill` en el preset, el agente no puede cargarlas [I].
  - **Mitigación** [I, sin probar]. Hay dos opciones:
    - **Recomendada:** un plugin Host CidIA en la raíz que registre un *guard* global. `ctx.tools.guard(fn)` deniega la ejecución cuando `fn` devuelve un texto; un *guard* de contexto plano aplica a todos los agentes (`packages/core/tools/src/index.ts:1126-1136`; `ToolExecution.name`, línea 333):

      ```js
      ctx.tools.guard(e => e.name === 'load_workspace_dependencies' ? 'No disponible en CidIA' : undefined)
      ```

      La herramienta seguirá apareciendo en el catálogo que ve el modelo, pero no se ejecutará.
    - **Alternativa:** `ctx.tools.restrict({ deny: [...] })` la oculta, pero exige un contexto con ámbito de agente (lanza error sin él) y que la herramienta ya esté registrada (líneas 1097-1118).
    - En la fase 4, quitar `desktopOffice` del Host.

### 3.2 Filas que hay que desactivar

Comprobé dos cosas:
- que los identificadores existen en la rc.2;
- el grafo de dependencias declarado en `package.json` (`dsh.client.inject` / `dsh.host.inject`), obtenido con `scratchpad/tools/inject-graph.mjs`.

El grafo **no** cubre los `static inject` escritos en código. Esos casos los revisé a mano cuando importaban.

| Grupo | Filas | ¿Rompe algo? |
|---|---|---|
| Presets con herramientas | `preset-standard`, `preset-ptc`, `preset-minimal`, `preset-cordis` y `agent-preset-registry → config: {default: cidia}` | Las sesiones guardadas con otro preset no se podrán reanudar (`agent-preset-registry/README.md`). En una instalación nueva no las hay. |
| Terminal del usuario (PTY en el PC) | `ui-sidebar-terminal`, `terminal-controller` | Nadie inyecta `ui-sidebar-terminal`; a `terminal-controller` solo lo inyecta `ui-sidebar-terminal`. Que el cliente monte el *remote* `terminal` sin servidor detrás debería dar error solo al llamarlo [I], porque `$mount` es local: `packages/api/gateway/src/client/index.ts:202-210`. **[P]** |
| Ficheros, navegador y apps del PC | `ui-sidebar-files`, `ui-sidebar-browser`, `open-in-app`, `ui-open-in-app` | Son hojas: nadie las inyecta. |
| Creator y Cordis dinámico | `ui-cordis`, `cordis-host-runner`, `cordis-inspect-providers` | Son hojas. |
| Instalar o configurar plugins desde la interfaz | `ui-plugin-manager`, `ui-settings-plugins`, `ui-settings-plugin-inventory`, `ui-settings-shell`. `ui-settings-agent-loop`, `ui-settings-subagent` y `ui-settings-web-search` inyectan `ui-plugin-manager`, así que dejan de cargar solas. *Verificación:* también la inyecta `@deepseek-ai/dsh-experimental-client-ui-voice-input`. Si algún día se añade al perfil el bundle de voz local de DSH, su interfaz tampoco cargaría. | Conviene mantener activa la fila Host `plugin-manager`: la usan los plugins CidIA (`remote.pluginManager.setPluginEnabled`). |
| Opcionales | `ui-deliverables` + `workspace-changes` (panel de entregables y cambios git), `message-feedback` + `ui-message-feedback` | Son hojas. **[P]** |

**Lo que no se puede quitar en la fase 1:** el menú tiene **F12 → DevTools** registrado también en la versión empaquetada (`main.ts:972-980`). Un usuario con DevTools puede llamar a los *remotes*, así que las restricciones de la interfaz son de comodidad. **Los permisos reales los aplica el gateway.**

### 3.3 `preset-cidia`

Va en el patch del bundle CidIA. Los paquetes existen en la rc.2 (`dsh-persona`, `dsh-tool-ask-user`, `dsh-tool-todo`, `dsh-compaction-*`).

```yaml
- insert:
    - id: preset-cidia
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: cidia
        name: CidIA
        order: 0
        plugins:
          - id: persona
            name: '@deepseek-ai/dsh-persona'
            config:
              prefix: >-
                Eres CidIA, el copiloto de formación de la planta. Respondes en castellano
                y te apoyas en las herramientas del servidor CidIA para citar la documentación.
          - id: tool-ask-user
            name: '@deepseek-ai/dsh-tool-ask-user'
          - id: tool-todo
            name: '@deepseek-ai/dsh-tool-todo'
          - id: compaction
            name: cordis:group
            group: true
            isolate:
              compaction: true
              toolResultPruner: true
            config:
              - id: compaction-basic
                name: '@deepseek-ai/dsh-compaction-basic'
              - id: command-compact
                name: '@deepseek-ai/dsh-command-compact'
              - id: tool-result-pruner
                name: '@deepseek-ai/dsh-compaction-tool-result-pruner'
                config:
                  thresholdChars: 8192
                  headChars: 4096
                  tailChars: 1024
```

`dsh-persona` debe ir **dentro** del preset. En la raíz choca con el registro del prompt (`packages/preset/persona/README.md`).

---

## 4. Proveedor de modelos único

### 4.1 Cómo lo hace hoy `cidia-proveedores` [V]

- **Interruptores de rutas `llm-pi-ai`.** Usa `remote.settings.mutate('llm-pi-ai', [{op:'set', path:['providers', id], value: perfil}])` y `op:'unset'` (`client.js:52-58`).
- **DeepSeek oficial.** No es una ruta de `llm-pi-ai`: lo enciende y apaga como fila con `remote.pluginManager.setPluginEnabled(entryId, …)` sobre `moduleName === '@deepseek-ai/dsh-llm-deepseek-api-key'` (`client.js:37-50`). Eso escribe `- id: llm-deepseek disabled: …` en el patch del perfil, como se ve en `~/.dsh/profiles/desktop/cordis.patch.yml`.
- **Interfaz.** Usa los *slots* `settings.models.provider-card` (con las claves `llm-pi-ai` y `llm-deepseek`) y `settings.models.footer` (`client.js:250-261`).
- **Canal Cliente→Host.** Es un campo *volatile* propio (`loginRequest`/`loginState`) que el Host vigila (`suscripcion/index.js:6-29,75-79`).

Para el producto, esa experiencia de interruptores se sustituye por una **configuración fija**.

### 4.2 Configuración propuesta

- **Ruta única en `llm-pi-ai`.** Su campo `providers` es `Volatile<Record<…>>` y cada perfil admite `api`, `baseURL`, `apiKeyEnv`, `models`, `compat` y `headers` (`docs/config-catalog.md:1616-1718`). La clave se resuelve **en cada petición** por `ctx.credentials`.

```yaml
- id: llm-pi-ai
  config:
    providers:
      cidia:
        displayName: CidIA
        api: openai-completions
        baseURL: !!js process.env.CIDIA_LLM_URL
        apiKeyEnv: CIDIA_GATEWAY_TOKEN
        compat:
          supportsDeveloperRole: false
          maxTokensField: max_tokens
        models:
          - id: ministral-3-8b
            name: Ministral 3 8B
            contextWindow: 32768
            input: [text, image]
- id: agent-default-model
  config:
    provider: cidia
    model: ministral-3-8b
```

- **Desactivar los proveedores de DeepSeek:**
  - `llm-deepseek`, que es `dsh-llm-deepseek-api-key` (`base/cordis.patch.yml:525-526`);
  - `llm-deepseek-account` (línea 528);
  - `web-search-deepseek` (líneas 478-481).
  
  Nadie las inyecta. **Sí hay que mantener** `deepseek-account`, `account-controller` y `credentials`: el escritorio llama a `account/getState`, `llm/listConfigurableProviders` y `credentials/describe` al arrancar, y si falta alguno el arranque es fatal (`welcome-backend.ts:72-121`, `main.ts:567-580`).
- **Que no salga la ventana de bienvenida de DeepSeek.** La bienvenida nativa aparece si `!loggedIn && !hasApiKey` (`welcome-api.ts:73-75`). `hasApiKey` es verdadero si **alguna** ruta configurable tiene su `apiKeyEnv` configurada (`welcome-backend.ts:95-118`). Por eso el instalador **debe** dejar `CIDIA_GATEWAY_TOKEN` resuelto antes del primer arranque. Recomiendo ponerlo en `$DSH_HOME/.env`:
  - `credentials-local` lo lee en este orden: proceso > `.credentials.yaml` > `.env` del proyecto o del *home* (`credentials-local/src/index.ts:553-631`). El nivel «proceso» es la **instantánea del entorno heredado** (`getFrom(ref, ['process'])`, línea 555), no el `process.env` vivo;
  - `loadLayeredEnv` también lo vuelca en `process.env` para los `!!js` (`app-boot/src/index.ts:235-256`).
  - *Verificación:* si el nombre llega en el **entorno heredado** (desde el lanzador o HKCU), `describe` lo marca `writable: false` y `set`/`unset` lanzan un error (`assertUnshadowed`, líneas 774-781). Con el valor en el `.env`, en cambio, se puede escribir (`writable: true`, línea 629) y `set` lo sustituye.
  - Desactivar `llm-deepseek` no rompe la bienvenida: si falta el espacio `llm-deepseek`, `ref` queda `undefined` sin error (`welcome-backend.ts:75-76`).
- **Ocultar Modelos y Cuenta.** `ui-settings-models` y `ui-settings-account` son hojas. *Corregido en la verificación:* `ui-settings-account` no ocupa solo `settings.models.sign-in`. También ocupa otros *slots* (`packages/client/ui-settings-account/src/client/index.ts:252-292`):
  - `shell.overlay`, con la incorporación de escritorio (`desktop-onboarding`) y la página de la plataforma DeepSeek;
  - `shell.quota-notice`, el aviso de cuota;
  - `settings.launcher`, el menú de cuenta;
  - `settings.section`. Al desactivarla desaparecen todos esos elementos, lo cual es lo deseado sin cuenta DeepSeek. Plan B si `ui-settings-account` molesta: dejarla con `step: done`, como en el perfil actual del usuario.
- **Bloquearlo.** Las filas anteriores se ponen en **`$DSH_HOME/cordis.patch.yml`**, la capa *home*:
  - en el escritorio se aplica **después** del patch del perfil (`profile-context.ts:63-75`; rc.2 `dsh-app-boot/lib/index.js:1023-1034`);
  - el servicio de ajustes **rechaza** cualquier escritura que esa capa anularía (`config-editor/src/index.ts:136-140`: «overridden by a home patch or command-line overlay»; documentado en `packages/settings/settings/README.md:37`). *Verificación:* `settings.update`/`mutate` pasan por `configEditor.edit` (`packages/settings/settings/src/index.ts:382-390`), que **escribe siempre en el patch del perfil** (`documentPath = profileContext.patchPath`, `config-editor/src/index.ts:34`), nunca en el del *home*. El README del paquete de idioma dice que la preferencia se guarda en `$DSH_HOME/cordis.patch.yml` (`packages/client/locale/README.md:12`), pero el código lo contradice, así que esa frase está desfasada.
- **Matiz.** Si queremos que un plugin CidIA mantenga la lista de modelos al día (por ejemplo, leyendo `/v1/models` del gateway), la ruta `llm-pi-ai` debe ir en la capa de **perfil**, gestionada por ese plugin con `ctx.settings.update`, y **no** en la *home*.

---

## 5. Cliente MCP y token en caliente

### 5.1 Fila MCP [V-rc2]

`@deepseek-ai/dsh-mcp-client` exporta `name`, `inject: ['tools']`, `Config` y `apply` (`packages/mcp/mcp-client/src/index.ts:31-34,119-142`). Su config para `streamable-http`:
- `serverName`, que debe cumplir `[A-Za-z0-9_-]{1,32}`;
- `url`, `headers`, `toolCallTimeoutMs`, `failOnStartupError` (por defecto `false`) y `reconnect`.

Las herramientas aparecen como `mcp__<serverName>__<tool>`. La activación **espera** a la primera conexión (`index.ts:194-202`). Si falla y `failOnStartupError` es falso, se registra en el log y reintenta: 10 intentos con espera exponencial y después abandona hasta que se recargue.

Variante estática, válida para el modo sin sesión. El patch del bundle CidIA la inserta con el token de puesto de `.env`:

```yaml
- insert:
    - id: mcp-cidia
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: streamable-http
        serverName: cidia
        url: !!js process.env.CIDIA_MCP_URL
        headers:
          Authorization: !!js "`Bearer ${process.env.CIDIA_GATEWAY_TOKEN}`"
        failOnStartupError: false
```

*Notas de la verificación:*
- **No hay que montar a la vez esta fila estática y el *child plugin* de §5.2 con el mismo `serverName: cidia`.** El segundo fallaría con `serverName "cidia" is already in use` (`mcp-client/src/index.ts:162-176`). Hay que elegir uno; para el token de sesión, el de §5.2.
- Como `apply` espera a la primera conexión (líneas 194-202), si el gateway no responde, el arranque de esa fila tarda lo que tarde en fallar el primer intento. Hay que medir si eso retrasa la ventana del escritorio **[P]**.

### 5.2 Actualizar el token tras iniciar sesión

| Qué cambia | Mecanismo | ¿Recarga la fila? |
|---|---|---|
| apiKey del LLM (`apiKeyEnv: CIDIA_GATEWAY_TOKEN`) | `ctx.credentials.set(credentialRef('CIDIA_GATEWAY_TOKEN'), token)` en el Host, o `remote.credentials.set(ref, token)` desde el Cliente. El *remote* lo expone `CredentialsController`: `packages/api/settings-controller/src/credentials.ts:99-105`. | **No.** La resolución se hace en cada petición (`packages/credentials/credentials/src/index.ts:175-183`). Se emite `credentials/reference-updated` (líneas 258-268). Al cerrar sesión, `unset` y se vuelve al token de puesto de `.env`. |
| `providers` de `llm-pi-ai`, `agent-default-model`, `locale` | `remote.settings.mutate` / `ctx.settings.update` | **No.** Son campos *volatile*: hay evento `loader/volatile-update` y las rutas se registran en vivo (`base/cordis.patch.yml:120-126`). *Verificación:* si esas filas están fijadas en la capa *home* de §9, estas escrituras se **rechazan** (§4.2). |
| `headers`/`url` de `mcp-client` | **No son *volatile***. El servicio de ajustes solo expone campos *volatile* (`docs/subsystems/settings.md:9`: «Ordinary fields are excluded»). Hay tres alternativas: (a) `ctx.configEditor.edit(entry, …)`, que reescribe `cordis.patch.yml` del perfil y recarga la fila (`config-editor/src/index.ts:87-140`), pero **guarda el token en claro en el patch**; (b) **montar el MCP como *child plugin*** desde un plugin Host CidIA y llamar a `fiber.update(config, true)`, que valida y reinicia solo esa fibra (`docs/cordis-api/fiber.md` «fiber.update»); (c) `!!js` + `inject` de un servicio propio [I]. | **Sí**, se desmonta y se reconecta. |

Propuesta (b) [I, no ejecutada]. Va en una fila Host del bundle CidIA, que debe declarar en `peerDependencies` `@deepseek-ai/dsh-mcp-client` y `@deepseek-ai/dsh-credentials` con la versión fijada `0.2.0-rc.2`:

```js
import * as mcpClient from '@deepseek-ai/dsh-mcp-client'
import { credentialRef } from '@deepseek-ai/dsh-credentials'

export const name = 'cidia-sesion'
export const inject = ['credentials', 'tools']
const REF = 'CIDIA_GATEWAY_TOKEN'

export function apply(ctx) {
  let fiber
  const mount = async () => {
    const token = (await ctx.credentials.resolve(credentialRef(REF)))?.value
    const config = {
      transport: 'streamable-http', serverName: 'cidia', url: process.env.CIDIA_MCP_URL,
      headers: token ? { Authorization: `Bearer ${token}` } : {}, failOnStartupError: false,
    }
    if (fiber === undefined) fiber = ctx.plugin(mcpClient, config)
    else fiber.update(config, true)
  }
  void mount()
  ctx.on('credentials/reference-updated', (ref) => { if (ref === REF) void mount() })
}
```

Por qué debería funcionar:
- La comprobación de compatibilidad acepta *prereleases* (`app-boot/src/plugin-compatibility.ts:61-88`). Fijar la versión exacta hace que el plugin se **salte con un aviso** si un día cambia el runtime. *Verificación:* cada *peer* `@deepseek-ai/dsh-*` se compara con la versión de **`dsh-app-boot`** (`getDshRuntimeVersion`, líneas 44-49), que en la rc.2 instalada es `0.2.0-rc.2`. Los *peers* de otros ámbitos (`@deepseek-ai/cordis`, `schemastery`) no se comprueban (línea 75).
- Los paquetes `@deepseek-ai/*` se resuelven desde la instalación, por la capa de resolución del perfil (`profile.ts:441-473`). Los plugins enlazados por *junction* entran como `linkedRoots` (`profile.ts:295-341`). Que esto funciona lo demuestra `cidia-proveedores/suscripcion/index.js`, que importa `@deepseek-ai/schemastery` desde una carpeta enlazada en la rc.2.
- `credentialRef` lo exporta `@deepseek-ai/dsh-credentials`; lo importa igual `settings-controller/src/credentials.ts:9`. `fiber.update(config, noSave)` valida antes de reiniciar (`docs/cordis-api/fiber.md`, sección `fiber.update`).

Hay que probarlo **[P]**.

---

## 6. Preinstalar plugins en un perfil sin la CLI

Lo que hicimos en `~/.dsh/profiles/desktop` (solo lectura):
- `package.json` con `dependencies: { "cidia-proveedores": "link:C:/…/03_MVP/plugins/cidia-proveedores" }`;
- `dsh.profile.bundles` = `@deepseek-ai/dsh-base`, `@deepseek-ai/dsh-web-app`, `@deepseek-ai/dsh-experimental-voice-input-bundle` y `cidia-proveedores`;
- `node_modules/cidia-proveedores` es una **Junction** a la carpeta del plugin (lo comprobé con `Get-Item`);
- `pnpm-workspace.yaml` con `nodeLinker: hoisted` y `autoInstallPeers: false`.

Por qué es fiable para un instalador [V]:
1. **El escritorio no reescribe nada que ya exista.** `applyRelease()` solo hace `initProfile` (escribe los ficheros que faltan) y `removeLinkProjections` (solo toca `.dsh-module-fallback`). Ni ejecuta pnpm ni instala nada (`project-manager.ts:80-91`; `profile.ts:254-293`). *Precisión de la verificación:* `applyRelease` hace además dos cosas, igual en la rc.2:
   - `readDesktopRuntime`, que solo valida;
   - `migrateProfileSettings`, que reescribe `pnpm-workspace.yaml` **solo si es idéntico** a una plantilla antigua con `strictDepBuilds` (`project-manager.ts:51-58`).

   Por su parte, `loadProfileDirectory` reescribe `package.json` solo si lista un bundle retirado (`dropRetiredBundles`, `profile.ts:667-674`). Con los ficheros de CidIA no se cumple ninguna de las dos condiciones.
2. **Resolución de bundles.** Primero el ancla de la instalación y después `<perfil>/node_modules` (`profile.ts:706-717`). Un bundle sin `dsh.bundle` o con *peers* `@deepseek-ai/dsh-*` incompatibles **se salta** con un aviso por stderr, no por la interfaz (`profile.ts:732-766`, `118-122`).
3. **La lista de bundles debe incluir `@deepseek-ai/dsh-base` y `@deepseek-ai/dsh-web-app`.** Si no, la app arranca vacía.
4. **Riesgo: el diálogo de fallo «Desactivar plugins de terceros».** `sanitizeProfile` renombra el `cordis.patch.yml` del perfil a `.bak-<ts>` y deja los bundles en la plantilla web, sin CidIA (`profile-sanitize.ts:18-33`; `main.ts:97-101`). La capa *home* no se toca. **El lanzador debe autorrepararse:** comprobar en cada arranque que `package.json` incluye el bundle CidIA y restaurarlo si no.
   - Es una opción que el usuario elige en el diálogo de error (`fatal-recovery.ts:95`, `response === 2`); no se ejecuta sola.
   - *Consecuencia que añade la verificación:* tras la recuperación, la capa *home* sigue desactivando los cuatro presets y fija `default: cidia`, pero `preset-cidia` venía en el bundle que se acaba de quitar. Crear una sesión falla entonces con `agent-preset/not-found` (`packages/preset/agent-preset-registry/src/index.ts:205-207, 233-236`; el README del registro lo confirma: «rejects a missing definition»). Hay dos salidas: la autorreparación del lanzador, o poner también el `insert` de `preset-cidia` en la capa *home* [I], porque un `insert` sin `id` es válido en cualquier capa (`vendor/include/src/index.ts:79-101`).

Pasos del instalador, sin red ni pnpm:

```text
<INSTDIR>\plugins\cidia-app\                (bundle CidIA: package.json con dsh.bundle.patch y dsh.client)
%LOCALAPPDATA%\CidIA\datos\                 (= DSH_HOME)
  .env                                      CIDIA_LLM_URL, CIDIA_MCP_URL, CIDIA_GATEWAY_TOKEN (nunca DSH_*)
  cordis.patch.yml                          capa home de bloqueo (§8)
  profiles\desktop\package.json             ver abajo
  profiles\desktop\cordis.patch.yml         "[]" (capa de usuario)
  profiles\desktop\pnpm-workspace.yaml      packages: [.] / nodeLinker: hoisted / autoInstallPeers: false
  profiles\desktop\node_modules\cidia-app   -> junction a <INSTDIR>\plugins\cidia-app  (mklink /J, sin admin)
```

```json
{
  "name": "dsh-profile-desktop",
  "private": true,
  "dependencies": { "cidia-app": "link:C:/Users/<usuario>/AppData/Local/Programs/CidIA/plugins/cidia-app" },
  "dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "cidia-app"] } }
}
```

---

## 7. Instalador oficial de escritorio

Todo lo de esta sección es [V].

- **Descarga.** `https://www.deepseek.com/download` enlaza:
  - Windows x64: `https://download.deepseek.com/desktop/dsh-latest-windows-x64.exe`, un alias móvil;
  - macOS arm64: `…/dsh-latest-macos-arm64.dmg`.
  
  **No hay Linux.** El feed `https://download.deepseek.com/dsh-desk/feeds/win-x64/nightly.yml` da:
  - `version: 0.2.0-rc.2`;
  - URL versionada `https://download.deepseek.com/dsh-desk/bin/win-x64/deepseek-harness-0.2.0-rc.2-win-x64.exe`;
  - `size: 289313640` y `sha512`;
  - `releaseDate 2026-09-29`.
  
  `curl -I` de los dos `.exe`: `Content-Length: 289313640` y la **misma ETag**. Los feeds `linux-x64` y `win-arm64` dan 404. La política, además, rechaza Windows que no sea x64 (`mandatory-update-policy.ts:153-154`). **Conclusión:** fijar la URL versionada y comprobar el `sha512` y la firma Authenticode (Hangzhou DeepSeek Artificial Intelligence Co., Ltd., según `app-update.yml`).
- **Tipo.** NSIS de electron-builder: `win.target: ['nsis']` en `apps/desktop/scripts/electron-builder-config.mjs:223-247`. El desinstalador instalado contiene «Nullsoft Install System v3.04». Tiene páginas propias (`apps/desktop/installer/*.nsh`) y extracción con 7-Zip.
- **Ámbito: solo por usuario.**
  - `perMachine: false`, `allowElevation: false` y `oneClick: false` (`electron-builder-config.mjs:237-246`);
  - `customInit` **sale con código 2** si es *all-users* o si hay instalación en HKLM (`scripts/installer.nsh:32-46`);
  - entrada de desinstalación en `HKCU\…\Uninstall\1bf39983-50d0-5fe0-9ef4-cece76f67c5e` (GUID derivado del `appId` `com.deepseek.dsh`). *Verificación:* el GUID es el UUIDv5 de `com.deepseek.dsh` en el espacio de nombres de electron-builder `50e065bc-3134-11e6-9bab-38c9862bdaf3` (recalculado: coincide). El registro tiene `DisplayVersion 0.2.0-rc.2` y no hay entrada en HKLM.
  - `productName: 'DeepSeek Harness'` está en `electron-builder-config.mjs:109`; da nombre al ejecutable y a la carpeta de instalación. El desinstalador también borra `%APPDATA%\DeepSeek Harness`, aunque en este PC esa carpeta no existe. `productName` no llega al `package.json` empaquetado, así que el `userData` de Electron usa `name` (§1.3).
- **Ruta.** `%LOCALAPPDATA%\Programs\DeepSeek Harness` (lo leí en el registro, `InstallLocation`). Una instalación nueva exige una carpeta **vacía** (`installer/path.nsh:120-140`).
- **Banderas.**
  - `/S` es silenciosa: en ese modo hace la comprobación previa y sale con código 2 si hay error (`installer.nsh:70-76`).
  - `/THEME=light|dark|auto` (líneas 49-61).
  - `/D=<ruta>` no está garantizada: `customInit` ejecuta `setInstallModePerUser`, que puede reescribir `$INSTDIR` [I] **[P en una máquina virtual]**. *Verificación:* la plantilla de electron-builder (`app-builder-lib/templates/nsis`) no está en el clon. Que `setInstallModePerUser` respete `/D` en esa versión sigue **sin confirmar**. Consta además `allowToChangeInstallationDirectory: false` (`electron-builder-config.mjs:244`).
  - Si la app está abierta, sale con código 2 (líneas 167-196).
  - Desinstalación silenciosa: `"…\Uninstall DeepSeek Harness.exe" /currentuser /S` (`QuietUninstallString` en el registro). `/KEEP_APP_DATA` conserva el `userData`.
  - El desinstalador borra `%APPDATA%\DeepSeek Harness`, `%APPDATA%\@deepseek-ai\dsh-desktop` y `%LOCALAPPDATA%\@deepseek-aidsh-desktop-updater`, y **nunca** `DSH_HOME`/`~/.dsh` (`installer/uninstall.nsh:1-35`).
- **No se pueden tener dos instalaciones a la vez.** Instalar en otra carpeta ejecuta el desinstalador de la anterior (`scripts/windows-directory-installer.mjs:27-37`). Por eso **usar el instalador oficial en este PC sustituiría la DeepSeek Harness del usuario**. Ocupa 1,1 GB instalada (medido), más unos 289 MB por cada `DSH_HOME`.
- **Cómo meter la app base en `CidIA-Setup.exe`:**
  - **(A)** Ejecutar el oficial con `/S`, borrar `resources\app-update.yml` y los accesos directos «DeepSeek Harness», y crear los de CidIA. Así sigue apareciendo «DeepSeek Harness» en Aplicaciones.
  - **(B, a evaluar)** Extraer la carga útil (`app-64.7z` dentro del NSIS) [I] en `%LOCALAPPDATA%\Programs\CidIA\app`, sin registro de DeepSeek y con desinstalador propio de CidIA. Hay que comprobar **[P]** que la app funciona portable y desde otra ruta. Con el ejecutable renombrado no hay que asumirlo. La extracción la hace un 7-Zip fijado (`installer/extract.h:1`; en la instalación hay `7zip-installer-LICENSE.txt`).
- **Licencias de lo que se redistribuye** (*añadido en la verificación*, para la tabla de licencias del proyecto):
  - DSH es MIT (`LICENSE`, «Copyright (c) 2026 DeepSeek»).
  - La rc.2 instalada incluye **`@deepseek-ai/libreoffice-kit-win32-x64` 0.1.2 con licencia MPL-2.0**, unos 184 MB en `resources/app.asar.unpacked/dsh/node_modules/@deepseek-ai/`. Es *copyleft* débil por fichero y queda fuera de la lista permisiva del proyecto; el propio repositorio lo marca como excepción (`THIRD_PARTY_NOTICES.md:175-180`).
  - Llevan además 7-Zip (LGPL, solo en el instalador, como programa externo) y el `ffmpeg.dll` de Electron (LGPL, biblioteca dinámica).
  - `THIRD_PARTY_NOTICES.md:157-173` de la alpha.1 menciona que se distribuyen los ejecutables **propietarios** de Claude Code (`@anthropic-ai/claude-agent-sdk-*`) para el subagente `claude-code`. **En la rc.2 instalada no están:** 0 entradas `claude-agent-sdk`/`subagent-claude-code` en el `app.asar` y ninguna en `app.asar.unpacked` ni en `runtime`. Antes de pasar a otra versión hay que comprobarlo de nuevo.
  - Marca: `BRAND_GUIDELINES.md` dice que «DeepSeek Harness» es marca registrada. Pide no usarla en el nombre de un proyecto derivado (recomienda «DSH») y no usar material oficial de forma que sugiera respaldo. Esto apoya el rebrand completo y pesa en la elección entre A y B.

---

## 8. Idioma y textos fijos

- **Interfaz web: sí admite castellano por plugin [V-rc2].** Un plugin Cliente registra el idioma con `ctx.effect(() => ctx.locale.addLanguage({ id: 'es', label: 'Español', fallback: 'en' }))` y cada diccionario con `ctx.locale.register('<ns>', 'es', {…})`. Lo que falte cae en inglés (`packages/client/locale/README.md`, «Registering a language pack»).
  - El idioma se fuerza con la fila `locale` → `config: { preference: es }`. Mientras el paquete no se haya registrado, la preferencia espera; no cambia a otro idioma.
  - Si va en la capa *home*, el selector de idioma no puede cambiarlo.
  - Hay unos 64 ficheros de diccionario con **unas 2 400 claves en inglés**. La cifra es aproximada, contada con expresiones regulares.
  - **Marca en la web:** 26 cadenas en inglés mencionan DeepSeek o Harness, muchas en páginas que vamos a desactivar. La marca se sustituye desactivando `ui-brand-official` y ocupando los *slots* `sidebar.brand.mark`, `sidebar.brand.name` y `conversation.hero.brand.mark` (`packages/client/ui-brand-official/README.md`).
  - El título de la página `<title>` se fija en el *build* (`DSH_CLIENT_TITLE`, `apps/web/vite.config.ts:23-27`). Un plugin podría cambiar `document.title` en tiempo de ejecución [I].
- **Textos fijos hasta la fase 4 [V].**
  - Están en el proceso Electron, `apps/desktop/src/locale.ts`, con solo `en` y `zh-CN` (líneas 344-368). Con `preference: es` se usa el idioma del sistema; si no es chino, inglés.
  - Afecta a: menús, «Acerca de DeepSeek Harness», el *tooltip* de la bandeja, la confirmación de salida, los diálogos de actualización, la ventana de bienvenida (inicio de sesión de DeepSeek o clave API), el diálogo de recuperación tras un fallo y la ventana de actualización obligatoria.
  - Fuera del proceso Electron, también:
    - el nombre del ejecutable y del proceso;
    - las carpetas `%APPDATA%`;
    - el protocolo `dsh://` (`main.ts:1228`);
    - el instalador y el desinstalador oficiales (`installer/strings.nsh`, solo en_US/zh_CN).

---

## 9. Capa *home* de bloqueo (consolidada)

Va en `$DSH_HOME/cordis.patch.yml`. Un patch con `config` **reemplaza** toda la config de la fila (`base/cordis.patch.yml:5-10`).

```yaml
# Telemetría y analítica de producto
- id: session-telemetry-otel
  disabled: true
- id: desktop-product-telemetry
  disabled: true
- id: product-analytics
  disabled: true
# Servicios de DeepSeek
- id: llm-deepseek
  disabled: true
- id: llm-deepseek-account
  disabled: true
- id: web-search-deepseek
  disabled: true
# Modos de agente con herramientas locales (preset-cidia lo inserta el bundle CidIA)
- id: preset-standard
  disabled: true
- id: preset-ptc
  disabled: true
- id: preset-minimal
  disabled: true
- id: preset-cordis
  disabled: true
- id: agent-preset-registry
  config:
    default: cidia
# Paneles que actúan sobre el PC
- id: terminal-controller
  disabled: true
- id: ui-sidebar-terminal
  disabled: true
- id: ui-sidebar-files
  disabled: true
- id: ui-sidebar-browser
  disabled: true
- id: open-in-app
  disabled: true
- id: ui-open-in-app
  disabled: true
- id: cordis-host-runner
  disabled: true
- id: cordis-inspect-providers
  disabled: true
- id: ui-cordis
  disabled: true
# Ajustes que permitirían reconfigurar
- id: ui-plugin-manager
  disabled: true
- id: ui-settings-plugins
  disabled: true
- id: ui-settings-plugin-inventory
  disabled: true
- id: ui-settings-shell
  disabled: true
- id: ui-settings-models
  disabled: true
- id: ui-settings-account
  disabled: true
# Marca e idioma
- id: ui-brand-official
  disabled: true
- id: locale
  config:
    preference: es
# Modelo por defecto (más la fila llm-pi-ai de §4.2 si la lista de modelos es fija)
- id: agent-default-model
  config:
    provider: cidia
    model: ministral-3-8b
```

Además, `DSH_TELEMETRY_DISABLED=1` en el lanzador, como doble seguro, y `resources\app-update.yml` borrado en la instalación de CidIA.

*Verificación:* existen en los patches de la rc.2 (`base`, `web-app` y los cuatro presets) los 29 identificadores de fila de este bloque y las 5 filas que hay que mantener o usar: `llm-pi-ai`, `deepseek-account`, `account-controller`, `credentials` y `plugin-manager`. Comparadas las listas completas de identificadores, la alpha.1 solo añade `schedule`, `time-context`, `tool-schedule` y `ui-schedule`. Opcional: `- id: plugin-package-inventory-deepseek` / `disabled: true`. Esa fila solo adjunta la lista de plugins a las peticiones a la API oficial de DeepSeek (`packages/llm/plugin-package-inventory-deepseek/README.md`), así que con `llm-deepseek` desactivada no hace nada.

---

## 10. Pruebas propuestas (fase siguiente; ninguna toca `~/.dsh` ni la instalación)

1. **Aislamiento.**
   - Salir de DeepSeek Harness desde la bandeja.
   - Preparar `C:\CidIA-pruebas\home` con los ficheros de §6 y §9 (incluido `.env` con un token de prueba, para que no salga la bienvenida).
   - Lanzar:

     ```powershell
     $env:DSH_HOME='C:\CidIA-pruebas\home'; $env:DSH_TELEMETRY_DISABLED='1'
     & "$env:LOCALAPPDATA\Programs\DeepSeek Harness\DeepSeek Harness.exe" --user-data-dir=C:\CidIA-pruebas\ud
     ```

   - Esperado:
     - se crea `home\dsh-runtimes`;
     - la fecha de modificación de `~/.dsh` no cambia;
     - si aparece `C:\CidIA-pruebas\ud\lockfile`, `--user-data-dir` funciona y se puede abrir la oficial a la vez.
   - La comprobación de actualización se hará igualmente, porque el `app-update.yml` del usuario sigue ahí. Hoy no hay versión nueva en el feed.
2. **Composición.** Comprobar que no aparecen la terminal, los ficheros, el navegador, Plugins, Modelos ni Cuenta, y que solo existe el modo CidIA. En DevTools (F12): `remote.pluginManager.listPlugins()` para ver qué filas están activas.
3. **Red.** Con `Get-NetTCPConnection -OwningProcess <pid>` o el Monitor de recursos, confirmar que no hay conexiones a `deepseeksvc.com`. Solo debería quedar la de `harness.deepseek.com` (política).
4. **Token.** Ejecutar `remote.credentials.set('CIDIA_GATEWAY_TOKEN', '<prueba>')`. La siguiente petición al LLM lleva la nueva cabecera y el MCP se reconecta (child plugin). [I] En DevTools, `remote` no tiene por qué ser una variable global; lo más fiable es lanzarlo desde el plugin cliente CidIA (`ctx.remote.credentials`).
6. *(Añadido en la verificación)* **Herramientas visibles.** Comprobar que el agente de `preset-cidia` ve `load_workspace_dependencies`, y que con el `tools.guard` de §3.1 su ejecución se deniega.
7. *(Añadido en la verificación)* **Arranque con el gateway caído.** Medir cuánto tarda en abrirse la ventana con `failOnStartupError: false` y la URL MCP inaccesible (§5.1).
5. **Instalador oficial en una máquina virtual o Windows Sandbox** (no en este PC): `/S`, `/D=` y extracción del 7z.

## 11. Riesgos

- La **política obligatoria** de DeepSeek puede bloquear a distancia la versión fijada. No se desactiva por configuración (§2.2).
- **La instancia única es compartida** con la DeepSeek Harness oficial (§1.3), y el instalador oficial **sustituye** una instalación existente del mismo usuario (§7).
- **`DSH_TELEMETRY_DISABLED` no cubre la analítica de producto**, que está activada por defecto (§2.1).
- **F12/DevTools** sigue disponible. La seguridad debe estar en el gateway (§3.2).
- La **recuperación tras un fallo** quita los bundles CidIA del perfil. Hace falta un lanzador que se autorrepare (§6).
- El **token de sesión** se guarda en claro en `$DSH_HOME/.credentials.yaml`. Hay que usar tokens de vida corta y hacer `unset` al cerrar sesión.
- Los **textos y la marca del proceso Electron** siguen siendo de DeepSeek y en inglés hasta la fase 4.
- **Versión alfa:** los identificadores de fila cambian entre versiones (por ejemplo `schedule`). Hay que fijar la 0.2.0-rc.2 y los `peerDependencies` exactos.
- **Disco:** 1,1 GB de instalación, más unos 289 MB por cada `DSH_HOME` **si el agente llega a llamar a `load_workspace_dependencies`** (§1.1).
- *(Añadido en la verificación)* **`load_workspace_dependencies`** es una herramienta global que monta el Host de escritorio y que no se quita por patch (§3.1). Se neutraliza con un `tools.guard` de un plugin CidIA.
- *(Añadido en la verificación)* **Licencia MPL-2.0** de `libreoffice-kit`, que viene dentro de la rc.2 (§7). Hay que declararla en la tabla de licencias o justificarla como excepción.
- *(Añadido en la verificación)* **Recuperación tras un fallo con la capa *home* activa:** sin el bundle CidIA, el preset por defecto `cidia` no existe y no se pueden crear sesiones (§6).

---

## Verificación

Hecha el 2026-10-09 en revisión escéptica, solo con lecturas:
- el clon `dsh-v0.2.1-alpha.1` (commit `5badb15`);
- la 0.2.0-rc.2 instalada: lectura del `app.asar` sin extraerlo, del registro HKCU y de `%APPDATA%\@deepseek-ai\dsh-desktop`;
- el perfil `~/.dsh/profiles/desktop`, sin abrir `.credentials.yaml`;
- el feed público de actualizaciones, con `curl` GET/HEAD y sin descargar el instalador.

No se tocó el servidor Oracle: este informe no hace afirmaciones sobre él.

### Confirmado

**Directorio de datos e instancia única**
- `DSH_HOME` se resuelve en `home-paths/src/index.ts:87-91`. El escritorio lo usa en `apps/desktop/src/paths.ts:17-21` y `main.ts:320`, y el Host en `desktop-host/src/index.ts:10,98`. En Windows no se lee el *login shell* (`login-shell-environment.ts:176`).
- El argumento `--updated` es el único que lee `main.ts` (línea 346).
- Un `.env` con variables `DSH_*` aborta el arranque (`app-boot/src/index.ts:157,207-220`).
- La instancia única la gestiona `requestSingleInstanceLock` (`single-instance.ts:20`; está también en la rc.2). Existe `%APPDATA%\@deepseek-ai\dsh-desktop\lockfile`. El `package.json` empaquetado de la rc.2 tiene `name @deepseek-ai/dsh-desktop` y no tiene `productName`.

**Telemetría y actualizaciones**
- `DSH_TELEMETRY_DISABLED` solo genera el patch de `session-telemetry-otel` (`profile-context.ts:39-55`). Se aplica también en el escritorio, después de la capa *home* (`profile-context.ts:63-75`, igual en la rc.2).
- `desktop-product-telemetry` y `product-analytics` están activas por defecto en el perfil `desktop` (`web-app/cordis.patch.yml:45-62`, igual en la rc.2). Su *endpoint* por defecto es `dsh-otel-collector.deepseeksvc.com` (`product-telemetry-otel/src/index.ts:47`).
- Los eventos llevan `device_id`, `user_id`, `app_version` y `os_version` (`product-analytics/src/index.ts:81-100`). Desactivarlas es seguro: `main.ts:456` y `account-backend.ts:115-118` lo toleran, y la interfaz usa `ctx.get('productAnalytics')?.…`.
- El comprobador de actualizaciones depende de `app-update.yml` (`update-coordinator.ts:54`, también en la rc.2), con `autoDownload=false` (líneas 67-72). El `app-update.yml` instalado apunta al feed `win-x64` y al canal `nightly`, y lo firma la entidad Hangzhou DeepSeek.
- La política obligatoria está en el `app.asar` de la rc.2, consulta `check_client_update` y bloquea con `40005` (`mandatory-update-policy.ts:112-125`). `DSH_DESKTOP_MANDATORY_UPDATE_CONFIG` solo vale sin empaquetar (`main.ts:1286`).

**Herramientas, presets e interfaz**
- Las herramientas están desactivadas en la raíz (`web-app/cordis.patch.yml:465-575`) y `default: standard` (580-583).
- La rc.2 tiene cuatro presets. La terminal PTY solo está en `preset-minimal`.
- Los presets no se pueden parchear por hijo (`vendor/include/src/index.ts:66-73`).
- `dsh-persona` falla en la raíz (`packages/preset/persona/README.md:28`).
- Las filas de §3.2 son hojas en el grafo `dsh.client.inject` (grafo regenerado). El único consumidor del *remote* `terminal` es `ui-sidebar-terminal`.
- F12/DevTools existe también en la versión empaquetada (`main.ts:972-980`; `accelerator: "F12"` en la rc.2).

**Proveedor, ajustes y credenciales**
- El esquema de `llm-pi-ai` (`config.ts:326-353`) admite `displayName`, `api` (`openai-completions`), `baseURL`, `apiKeyEnv`, `models[].{id,name,contextWindow,input:[text,image]}`, `compat.supportsDeveloperRole` y `compat.maxTokensField: max_tokens`. `providers` es *volatile* (línea 353).
- `agent-default-model.{provider,model}` también son *volatile* (`core/agent-default-model`).
- La bienvenida depende de `loggedIn`/`hasApiKey` (`welcome-api.ts:73-75`; `welcome-backend.ts:72-121`, igual en la rc.2). Si `account/getState`, `llm/listConfigurableProviders` o `credentials/describe` fallan, el arranque es fatal (`main.ts:567-580,1197-1211`).
- La capa *home* se aplica después del perfil, y una escritura anulada por ella se rechaza (`config-editor/src/index.ts:136-140`).
- Las credenciales se resuelven en cada petición y `set`/`unset` emiten `credentials/reference-updated` (`credentials/src/index.ts:175-183,258-268`; `credentials-local` 609-631 y 733-765). El *remote* `credentials.set(ref, value)` está en `settings-controller/src/credentials.ts:99-105`.

**MCP y plugins del perfil**
- El esquema de `mcp-client` (`streamable-http`, `url`, `headers`, `failOnStartupError` false, `serverName` `[A-Za-z0-9_-]{1,32}`, 10 reintentos) coincide en la alpha.1 (`index.ts:119-142`, `connection.ts:41-46`) y en la rc.2 (`lib/index.js`).
- `fiber.update(config, noSave)` existe (`docs/cordis-api/fiber.md`).
- Patrón de perfil: `package.json` con `link:` y bundles, *junction* (`Get-Item` → `Junction`) y `pnpm-workspace.yaml` igual a la plantilla (`profile.ts:240-245`). `initProfile` no sobrescribe (`profile.ts:254-273`).
- Un bundle con *peers* incompatibles se salta (`profile.ts:752-753`).
- `sanitizeProfile` funciona como se describe (`profile-sanitize.ts:18-33`).

**Instalador oficial**
- El feed `nightly.yml` sigue en `0.2.0-rc.2` (`size 289313640`, `releaseDate 2026-09-29T10:35:27Z`). El alias y la URL versionada tienen el mismo `Content-Length` y la misma ETag. Los feeds `linux-x64`, `win-arm64` y `linux-arm64` devuelven 404.
- Es NSIS v3.04, por usuario, sin elevación (`electron-builder-config.mjs:237-246`).
- Lo confirmado de `customInit`, `/THEME`, `/S` y app abierta → código 2 está en `apps/desktop/scripts/installer.nsh:32-76,167-196`.
- Instalar en otra ruta desinstala la previa (`windows-directory-installer.mjs:27-37`).
- El desinstalador respeta `DSH_HOME` (`uninstall.nsh:23-35`). En el registro: `QuietUninstallString` … `/currentuser /S`.
- Tamaño medido: 1,1 GB instalada; `~/.dsh/dsh-runtimes` ocupa 289 MB.

**Idioma, marca y versiones**
- Paquete de idioma: `addLanguage` existe en la rc.2 y `locale.preference` es *volatile* (`client/locale/src/index.ts:24`).
- El proceso Electron solo tiene `en` y `zh-CN` (`locale.ts:344-369`).
- Marca: `ui-brand-official` y sus *slots*; `DSH_CLIENT_TITLE` (`apps/web/vite.config.ts:21-28`).
- La alpha.1 solo añade `schedule`, `time-context`, `tool-schedule` y `ui-schedule` respecto a la rc.2; diferencia completa de identificadores en `base`, `web-app` y los presets.

### Corregido en el texto

1. **Política obligatoria (§2.2):**
   - el JSON de la rc.2 incluye `allowedPageOrigins`, que es obligatorio;
   - un bloqueo ya recibido se mantiene si después falla la red, mientras dure el proceso;
   - la ruta del *script* es `apps/desktop/scripts/desktop-policy-environment.mjs`;
   - Linux y Windows ARM solo arrancarían compilados sin política (`main.ts:1297`; `mandatory-update-policy.ts:153-154`).
2. **`dsh-runtimes` (§1.1, §11):** la copia de unos 289 MB no se hace al arrancar. Ocurre la primera vez que el agente llama a `load_workspace_dependencies`.
3. **Herramienta local que no se quita por patch (§3.1, resumen, §11):** el Host de escritorio monta por código, en la rc.2 también, `dsh-tool-workspace-dependencies` (`load_workspace_dependencies`, global) y las *skills* de Office. Se propone `ctx.tools.guard` como mitigación.
4. **`ui-settings-account` (§4.2):** además de `settings.models.sign-in`, ocupa `shell.overlay`, `shell.quota-notice`, `settings.launcher` y `settings.section`.
5. **`deepseek-account` (§2.1):** las líneas citadas (53-56) solo eran los valores por defecto. La conclusión se mantiene, ahora con las líneas correctas.
6. **`applyRelease` (§6):** también llama a `migrateProfileSettings`, y `loadProfileDirectory` puede reescribir `package.json` con `dropRetiredBundles`. Ninguno afecta a los ficheros de CidIA.
7. **Lanzador (§1.2):** la ruta del `Exec` es la de la opción B. No debe fijar `CIDIA_GATEWAY_TOKEN`, porque el entorno heredado tapa el almacén y `set` lo rechaza (`credentials-local` 774-781). `app.relaunch()` probablemente hereda ya el entorno [I].
8. **MCP (§5.1):** la fila estática y el *child plugin* con el mismo `serverName` chocan (`mcp-client/src/index.ts:162-176`). Hay que usar uno.
9. **Recuperación (§6, §11):** con la capa *home* activa y sin el bundle, el preset `cidia` no existe y las sesiones fallan con `agent-preset/not-found`.
10. **`ui-plugin-manager` (§3.2):** también lo inyecta la interfaz de voz experimental de DSH.
11. **Licencias y marca (§7):**
    - la rc.2 redistribuye `libreoffice-kit-win32-x64` con licencia MPL-2.0, 7-Zip (LGPL) y el `ffmpeg.dll` de Electron (LGPL);
    - los ejecutables propietarios de Claude Code que cita `THIRD_PARTY_NOTICES.md` de la alpha.1 no están en la rc.2 instalada;
    - `BRAND_GUIDELINES.md` protege la marca «DeepSeek Harness».
12. **Documentación de DSH contradictoria:** `client/locale/README.md:12` dice que la preferencia de idioma se guarda en `$DSH_HOME/cordis.patch.yml`, pero el código escribe en el patch del **perfil** (`config-editor/src/index.ts:34`). El informe sigue el código.

### Sigue sin confirmar (requiere ejecución; ver §10)

- `--user-data-dir` en este Electron 44: si separa `userData` y el bloqueo de instancia única.
- `/D=` con el NSIS de DSH. La plantilla `multiUser.nsh` de electron-builder no está en el clon. Tampoco la extracción portable de `app-64.7z` (opción B).
- Que la interfaz arranque sin errores con `terminal-controller` desactivado.
- Que las filas cliente que inyectan `ui-plugin-manager` simplemente queden sin montar.
- El *child plugin* `cidia-sesion`: importar `@deepseek-ai/dsh-mcp-client` desde un plugin enlazado, el `fiber.update` y que las herramientas lleguen a la capa global.
- El `tools.guard` contra `load_workspace_dependencies`.
- Cuánto retrasa el arranque un gateway MCP caído.
- `app.relaunch()` y el reinicio tras actualizar: si heredan `DSH_HOME` del lanzador.
- Qué responde hoy `check_client_update` con las cabeceras completas del escritorio. No se volvió a consultar.
- Las cifras de unas 2 400 claves en inglés y 26 cadenas con la marca: no se recontaron.
