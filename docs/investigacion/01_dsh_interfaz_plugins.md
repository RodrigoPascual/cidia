# 01 · Interfaz de CidIA dentro de DeepSeek Harness 0.2.x mediante plugins

Investigación técnica: cómo construir los paneles de CidIA dentro de la app de escritorio, con qué piezas de dsh y qué arquitectura recomendamos.

- **Fecha:** 2026-10-09
- **Versiones analizadas:**
  - código fuente `dsh-v0.2.1-alpha.1`, en el clon del scratchpad (`.../deepseek-harness`);
  - app instalada `0.2.0-rc.2`, con Electron 44.0.0. Su `app.asar` se ha leído con un lector propio de solo lectura (`scratchpad/asar.mjs`). Ni la app ni `~/.dsh` se han modificado.
- **Convenciones:**
  - Las rutas `apps/…`, `packages/…` y `docs/…` son relativas al clon de dsh.
  - Las rutas `rc2:…` se refieren a ficheros de la 0.2.0-rc.2 instalada, extraídos de `resources/app.asar`.
  - **[inferencia]** marca lo que no se ha comprobado en código ni en ejecución.

---

## 0. Resumen ejecutivo

1. **Un plugin de cliente ya puede crear secciones completas de la app.** Necesita dos registros con el mismo id:
   - un icono con etiqueta en la barra lateral (`sidebar.panellist`);
   - una vista a pantalla completa en el área central (slot `main`, de tipo `keyed`).

   Es el mismo patrón que usan las secciones oficiales «Plugins» y «Tareas». Las APIs usadas son idénticas en la 0.2.0-rc.2 y en la 0.2.1-alpha.1.
2. **Para el plugin hay React 18 y la librería oficial de componentes.** Vienen con `require()` en la tabla de módulos base: `react`, `react-dom`, `@deepseek-ai/dsh-client-ui-primitives` con `Button`, `Input`, `Modal`, `Switch`, `Tag`, `MarkdownText`, iconos…, y además `cordis`, `client-store` y `ui-slots`. Los estilos propios se cargan y descargan con el plugin.
3. **Canal cliente↔Host propio del plugin (el hallazgo principal):** el módulo Host de un plugin puede publicar rutas HTTP en el servidor web local de dsh.
   - Mecanismos: `ctx.webServer.register` o `ctx.connection.rpc.handle`. La autenticación es la misma que la de `/api`, con `ctx.connection.requestRejection`.
   - El renderer las llama con `fetch('cidia/…')` en el **mismo origen** `dsh-app://app`. Electron reenvía la petición al Host con la cookie de sesión.
   - Esto **sustituye al truco de `cidia-proveedores`**, que usaba Ajustes como buzón con sondeo cada 1,5 s.
4. **El Host del plugin puede hacer `fetch()` saliente al gateway.** Usa el `fetch` global de Node 24, y la política de proxy de dsh se aplica sola.
5. **Ni `iframe` ni `<webview>` son buenas bases para la interfaz:**
   - **Iframe:** el documento principal no tiene CSP y no hay bloqueo de contenido mixto, así que un `<iframe>` a `http://servidor:puerto` **funciona técnicamente**. Pero no comparte tema ni sesión: las cookies son `SameSite` y en HTTP no puede haber `SameSite=None` porque exige `Secure`. Además, la interfaz web de WeKnora envía `X-Frame-Options: SAMEORIGIN`.
   - **`<webview>`:** Electron lo bloquea salvo que se use el navegador lateral oficial.
6. **`fetch()` directo del renderer a otro origen es posible**, pero exige CORS en el gateway para el origen `dsh-app://app` y deja el token en el renderer. No lo recomendamos.
7. **Recomendación: opción (a).** Paneles React en el cliente del plugin, que llaman a rutas `/cidia/*` del Host del mismo plugin; el Host hace de proxy autenticado hacia el gateway y guarda el token de sesión. Para casos puntuales sirve la pestaña «Navegador» del panel derecho (por ejemplo, la administración de WeKnora o un vídeo del servidor).
   - Hay un **esqueleto probado** (Host + cliente) en el §8, con dos bancos de pruebas superados.

---

## 1. Cómo se cargan los módulos de cliente de un plugin

### 1.1 Flujo verificado

1. **Declaración en el paquete.** El `package.json` declara `dsh.client.platform: "web"` y exporta `./client`. El registro de módulos del Host los escanea (`docs/subsystems/client-modules.md:80`).
2. **Servicio por HTTP.** Los sirve combinados en `GET /plugins/??<paquete>/client.js,…&rev=…` (`client-modules.md:88`).
3. **Inyección en el documento.** El índice inyecta, en este orden, `window.__ModuleLoader__`, los scripts y el grafo `window.__DSH_BOOT__` (`packages/client/modules/README.md:80`).
4. **Registro del bundle.** Cada `client.js` llama a `window.__ModuleLoader__.load({ id, factory })`. El `id` es el nombre del paquete y `factory(require)` devuelve los `exports` (`packages/client/modules/src/client/manifest.ts:316-327`).
5. **Materialización.** El factory se ejecuta una sola vez y queda en caché (`.../client/system.ts:306-312`). Lo que devuelve es el plugin Cordis: `{ inject, apply }`.
6. **Resolución de `require`.** Busca primero en la tabla base, luego en los módulos ya registrados y por último en las filas del grafo. Si no encuentra el módulo, lanza error (`modules/README.md`, sección «Lazy-CJS model»).

### 1.2 Tabla de módulos base (lo que `require()` resuelve sin declarar nada)

`packages/client/web/src/platform.ts:8-14`:

```ts
'react', 'react/jsx-runtime', 'react-dom', 'react-dom/client', '@deepseek-ai/cordis',
'@deepseek-ai/dsh-client-store', '@deepseek-ai/dsh-client-ui-slots',
'@deepseek-ai/dsh-client-ui-primitives', '@deepseek-ai/dsh-client-ui-dockkit',
```

- **En la rc.2 instalada:** la misma tabla aparece literalmente en `rc2:dsh-web-frontend/dist/assets/index-5SrrfWpU.js`, en la función que devuelve `{react:…, "react/jsx-runtime":…, …, "@deepseek-ai/dsh-client-ui-dockkit":…}`.
- **Versión de React:** dsh declara `react ^18.2.0` (`packages/client/ui-schedule/package.json`). En la app es React 18 **[inferencia: 18.3.x]**.

### 1.3 Componentes reutilizables (ui-primitives)

**Lo que exporta la rc.2:** se ha comprobado en `rc2:dsh-client-ui-primitives/lib/index.js`, en la lista final de exports:

- **Controles:** `Button` (`variant`: primary/ghost/outline/toolbar; `size`: md/sm; `icon`), `Input`, `Switch`, `Checkbox`, `SegmentedControl`, `SegmentedTabs`, `Pill`, `Tag`, `StateDot`, `Menu`/`MenuItemButton`, `Tooltip`, `HoverCard`, `Toast`.
- **Ventanas:** `Modal`, con props `open`, `onClose`, `title`, `closeLabel`, `footer`… (`rc2:…/lib/index.js:5210`). `RiskConfirmation`.
- **Contenido:** `MarkdownText` (GFM no confiable, KaTeX), `CodeBlock`, `JsonTree`, `ImageLightbox`, `SettingsForm` y campos.
- **Iconos:** `Icon*Regular` y `Icon*Medium`, por ejemplo `IconUserOutlineRegular`, `IconGaugeOutlineRegular`, `IconUsersOutlineRegular`, `IconDatabaseOutlineRegular`, `IconPlayOutlineRegular`, `IconMicrophoneOutlineRegular`, `IconChecklistOutlineRegular`.
- **Marca:** `FishLogo` y `BrandWordmark` son la marca de DeepSeek y **no deben usarse en CidIA**.

**Cuándo usar cada uno:** el catálogo de `packages/client/ui-primitives/README.md:41-75` lo explica.

**Estilo:** se usan los tokens de tema `--dsw-alias-*`, los mismos que la app (`docs/web-styling.md:9,18`). Ejemplos: `--dsw-alias-bg-base`, `--dsw-alias-bg-layer-1`, `--dsw-alias-label-primary`, `--dsw-alias-label-tertiary`, `--dsw-alias-state-error-primary`, `--dsw-alias-border-l2`. Con ellos los paneles siguen solos el modo claro u oscuro.

**CSS propio sin bundler:** un `<style>` creado **dentro del factory** queda etiquetado con `data-plugin=<id>`, y el cargador lo elimina al desactivar el plugin. Esto se ha verificado en `packages/client/modules/src/client/system.ts:67-86` (`untaggedStyles` y `claimStyles`) y en `entry-lifecycle.ts:23-28` (`removeOwnedStyles`).

### 1.4 Comparación con `cidia-proveedores` (el plugin que ya funciona)

| Aspecto | `cidia-proveedores` (0.5.0) | Lo que recomendamos para `cidia-ui` |
|---|---|---|
| Formato del cliente | `window.__ModuleLoader__.load({ id, factory(require) { … return { inject, apply } } })` en JS plano con `React.createElement` | Igual. En producción, mejor escribir en TSX y compilar con el mismo envoltorio que dsh (ver abajo). |
| `dsh.client.immediately` | `true` | Omitirlo. Según `packages/client/AGENTS.md:144`, solo es para filas de infraestructura de «stage one». |
| `dsh.client.inject` | `["@deepseek-ai/dsh-client-ui-settings-models"]` | Es informativo. No ordena la activación; la ordena el `inject` de servicios Cordis (`AGENTS.md:144`). |
| Servicios cliente | `slots`, `remote.settings`, `remote.pluginManager` | `slots` y, si hace falta, `layout`, `sidebarRight` o `sidebarRightTabs`. |
| Canal cliente→Host | Escribe en Ajustes (`remote.settings.mutate('cidia-suscripcion', …)`) y el Host lo lee con `setInterval` cada 1,5 s (`suscripcion/index.js:76-79`) | **Rutas HTTP del propio Host del plugin** (§5), con respuesta inmediata, streaming y sin sondeo. |
| Host | `index.js` vacío. `suscripcion/index.js` con `inject: ['settings', 'authorization']` | `index.js` con `inject: ['webServer', 'connection']`, que publica `/cidia/*`. |
| Instalación | `~/.dsh/profiles/desktop/package.json`: dependencia `link:` y entrada en `dsh.profile.bundles`. `cordis.patch.yml` del paquete con `insert` | Igual; lo hará el instalador CidIA-Setup. |

**Envoltorio de compilación de dsh** (`packages/client/tsdown.client.ts:616-622`). Sirve para cualquier salida CJS de un bundler, con `react` y las primitivas como `external`:

```js
// banner + intro (antes del código CJS)
window.__ModuleLoader__.load({ id: "cidia-ui", factory: (require) => {
var module = { exports: {} }; var exports = module.exports;
// …código CJS del bundle (require('react') etc. se resuelven con la tabla base)…
// footer
return module.exports; } });
```

---

## 2. Slots de cliente disponibles

### 2.1 Árbol de slots

Árbol de declaraciones que se distribuye con dsh (`docs/subsystems/slots.md:115-192`). El mismo árbol está en la rc.2: se ha comprobado en `rc2:dsh-client-ui-sidebar/lib/client.js:490-519` y `rc2:dsh-client-ui-layout/lib/client.js:604-612`.

```text
root
├─ sidebar
│  ├─ sidebar.brand.mark        ├─ sidebar.brand.name      ├─ sidebar.toggle.badge
│  ├─ sidebar.panellist         ├─ sidebar.footer.action
│  ├─ sidebar.workspaces (…)    └─ sidebar.settings (settings.section, settings.general.item, settings.plugins.tab, …)
├─ main  (keyed: 'conversation' | 'plugins' | 'schedules' | …claves propias)
│  └─ main.conversation → conversation.* (chat, composer, header, hero…)
├─ rightbar → rightbar.session → sidebar.right.pane.tab / .title / sidebar.right.tab.menu.item / guide
├─ shell.bottom   ├─ shell.leading   └─ shell.overlay
```

### 2.2 Tipos de slot y props

Cada slot tiene un tipo (*kind*) y un ámbito (*scope*):

- `single`: una sola entrada; gana la de menor `priority`.
- `list`: varias entradas, cada una con `id` y ordenadas por `order`.
- `keyed`: una entrada por `key`.
- `chain`: varias entradas en cadena.

El ámbito es `root`, `session-maybe` o `session` (`slots.md:48-62`).

**Opciones de registro:** `name`, `key` o `id`, `order`, `label` (texto o función: `ui-slots/src/index.ts:758`), `priority`, `locale`, `inject` y `children` (`ui-slots/src/index.ts:771-779`).

**Datos para los componentes:** se pasan con `inject: () => ({ …, hooks: { x: {getSnapshot, subscribe} } })`. El renderizador convierte cada clave de `hooks` en la prop `useX(selector)` (`slots.md:105`; nombre generado por `standardHookPropName`, `ui-slots/src/renderer.ts:42-44`). Los componentes no reciben `ctx` (`slots.md:79`).

### 2.3 Slots útiles para CidIA

| Slot | Tipo y ámbito | Props del dueño | Uso en CidIA | Evidencia |
|---|---|---|---|---|
| `sidebar.panellist` | list · root | `{ size: number, active: boolean }` | Icono y fila de cada servicio (Inicio, Mi formación, Captura, Progreso, Administración…) | `ui-sidebar/src/client/contract/slots.ts:31-35,69-75` |
| `main` | keyed · root | ninguna; `usePanelInfo` estándar | Vista a pantalla completa de cada servicio. La clave es la misma que el `id` de la fila. | `ui-layout/src/client/index.ts:69-73,183` |
| `sidebar.brand.mark` | single · root | `{ size }` | Logo de CidIA | `contract/slots.ts:20-25,57-61` |
| `sidebar.brand.name` | single · root | ninguna (el ocupante decide) | Texto «CidIA» | `contract/slots.ts:26-30` |
| `sidebar.footer.action` | list · root | `{ wide: boolean }` | Botón de sesión («Iniciar sesión» o el nombre del usuario) junto a Ajustes | `contract/slots.ts:49-53,107-111` |
| `conversation.hero.brand.mark` | single · root | `HeroBrandMarkOwnerProps` | Logo del estado vacío del chat, para el rebrand | lista de `SlotMap` en `ui-conversation` |
| `sidebar.right.pane.tab` (+ `.title`) | keyed · session | `useTabInfo()` | Pestaña lateral junto al chat, por ejemplo «Instrucción paso a paso» o «Evidencias» | `ui-sidebar-right/src/client/contract/slots.ts:59-78` |
| `shell.overlay` | list · root | ninguna; capa que deja pasar los clics | Avisos, toasts y banners globales | `ui-layout/src/client/index.ts:96-105` |
| `settings.section` / `settings.plugins.tab` | list · root | `SettingsSectionOwnerProps` | Ajustes técnicos de CidIA (URL del gateway). La administración funcional va mejor en `main`. | lista de `SlotMap` |

### 2.4 Cómo funciona `sidebar.panellist` con `main`

**Ejemplos de referencia:**

- **Tareas:** `TaskManagerIcon` con `TaskManagerPage`, en `packages/client/ui-schedule/src/client/index.ts:168-184`:

  ```ts
  ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: PANEL_ID, locale: MANAGER_NS, inject: () => ({…}) }, TaskManagerPage))
  ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
    name: 'sidebar.panellist', id: PANEL_ID, order: 10, locale: MANAGER_NS, label: () => t('panel'),
  }, TaskManagerIcon))
  ```

  El icono solo pinta el glifo: `TaskManagerIcon({ size }) => <IconClockOutlineRegular size={size} />` (`TaskManagerIcon.tsx:14-16`). `PluginsPanelIcon` hace lo mismo (`ui-plugin-manager/src/client/PluginsPanelIcon.tsx:13-15`; registro en `ui-plugin-manager/src/client/index.ts:110-147`).

**Cómo lo pinta la barra lateral:**

- **Lista de filas.** Recorre `entriesOfSlot('sidebar.panellist')` y toma `{ id, order, label }`; la etiqueta se calcula con `resolveSlotLabel` (`ui-sidebar/src/client/index.ts:48-62`). Reacciona a altas y bajas en vivo con `ctx.slots.subscribe`.
- **Cada fila** es un botón suyo. El icono del plugin se pinta con `renderSlot('sidebar.panellist', { size: wide ? 16 : 18, active }, { only: id })`, y el clic llama a `selectPanel(id)` (`SidebarRoot.tsx:59-71, 279-288`).

**Qué hace `ctx.layout.selectPanel(id)`:**

- **Panel sin registrar:** si no existe un `main` con esa clave, **lanza error** (`ui-layout/src/client/service.ts:72-77`; también en `rc2:dsh-client-ui-layout/lib/client.js:462-465`). Por eso siempre hay que registrar `main` antes que la fila.
- **Panel retirado:** si se retira el panel que está activo, se vuelve al chat (`ui-layout/src/client/stores.ts:97-101`).
- **Navegar desde código:** con `inject: ['layout']` se llama a `ctx.layout.selectPanel('cidia.formacion')`; `selectPanel(null)` vuelve a la conversación (`service.ts:32-36`).

**Paneles según permisos.** Como la barra lateral se suscribe a los cambios del slot, se pueden **registrar y retirar paneles en vivo** al iniciar o cerrar sesión. El esqueleto del §8 lo hace y está probado. `ctx.slots.register` se envuelve solo en `ctx.effect` y devuelve un disposer (`ui-renderer/src/client/registry.ts:740-746`). `ctx.slots.inject(key, cb)` acepta que el callback devuelva un disposer o un iterable de disposers (`registry.ts:117, 194-209`).

**Cabecera de los paneles.** Los paneles oficiales ponen `padding-top: calc(28px + var(--dsh-frame-top-clearance, 0px))` y el atributo `data-window-drag` en la cabecera, para que se pueda arrastrar la ventana con la barra de título oculta de Windows (`ui-plugin-manager/src/client/PluginManagerPage.tsx:1420`, `PluginManagerPage.module.css:39`). El esqueleto hace lo mismo.

### 2.5 Panel derecho (`sidebar.right.pane.tab`)

Una pestaña lateral necesita dos registros que comparten `id` (`docs/subsystems/sidebar-right.md`, «Tab-type registration»; ejemplo real en `ui-schedule/src/client/index.ts:155-167`):

```js
ctx.effect(() => ctx.sidebarRightTabs.register({ id: 'cidia-ui/paso-a-paso', kind: 'cidia.pasos', title: () => 'Paso a paso',
  guide: [{ id: 'pasos', order: 50, title: () => 'Paso a paso' }] }), 'cidia: tipo de pestaña')
ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab', key: 'cidia-ui/paso-a-paso' }, PasosBody))
// abrir: ctx.sidebarRight.openTab('cidia.pasos', { params: {...} })
```

**Limitación:** el ámbito es `session`, así que estas pestañas solo existen con una conversación abierta (`sidebar-right.md`, «All tabs require a foreground Session»). Sirven para acompañar al chat («qué paso toca», «evidencias»), no para las vistas principales.

### 2.6 Marca (logo)

- **Logo oficial:** `ui-brand-official` registra `sidebar.brand.mark` y `sidebar.brand.name` con prioridad 0 (`packages/client/ui-brand-official/src/client/index.ts:16-23`). En la rc.2 se registra siempre: `rc2:dsh-client-ui-brand-official/lib/client.js:36-37`.
- **Cómo imponer el de CidIA:** registrar con `priority: -10` en los slots `single`; gana la prioridad más baja (`ui-slots/src/index.ts:771`). Sin ningún ocupante, la barra lateral pinta el pez `FishLogo` (`SidebarRoot.tsx:189, 225`).
- **Título de la ventana:** viene de la compilación (`ui-layout/src/client/DocumentTitle.tsx`, prop `productTitle`) y del `<title>DeepSeek Harness</title>` de `dsh-web-frontend/dist/index.html`. **Un plugin no lo cambia**; se cubre en el rebrand compilado de la fase 4.

### 2.7 Otras formas de ocupar toda la pantalla

| Forma | Qué ocupa | Evidencia |
|---|---|---|
| `main` + `selectPanel` (recomendada) | Todo el área central, con la barra lateral visible | §2.4 |
| `Modal` de ui-primitives | Diálogo centrado sobre la app, con máscara (va en un portal a `body`) | `ui-primitives/src/Modal.tsx:9-60` |
| `shell.overlay` | Capa flotante sobre las tres columnas; cada entrada activa sus propios eventos de puntero | `ui-layout/src/client/index.ts:96-105` |
| Sustituir `sidebar` o `root` | Todo. **No se recomienda:** el `root` lo ocupa `AppFrame` y sustituirlo rompe la app (`ui-layout/src/client/index.ts:59-68`) | — |

---

## 3. ¿Se puede incrustar un `<iframe>` o un `<webview>` hacia `http://<servidor>:<puerto>`?

### 3.1 Content-Security-Policy

- **Documento principal sin CSP:**
  - `apps/web/index.html:1-15` no tiene `<meta http-equiv="Content-Security-Policy">`;
  - en la rc.2, `rc2:dsh-web-frontend/dist/index.html` tampoco;
  - Electron sirve el índice con `serveWebDocument`, que solo pone `content-type` (`apps/desktop/src/web-document.ts:18-35`);
  - en `rc2:lib/main.js` no aparece ninguna cabecera CSP (búsqueda de `content-security-policy` sin resultados).

  En consecuencia, no hay `frame-src`, `connect-src` ni `default-src` que restrinjan.
- **CSP que sí existen en el código, ninguna afecta a CidIA:**
  - ventanas internas de Electron: `apps/desktop/renderer/*.html:6`;
  - vista previa de HTML del panel derecho, con un `frame-src 'none'` que se aplica **dentro de su iframe**: `ui-sidebar-documentpreview/src/client/html/basic-document.ts:18-19`;
  - respuestas de medios: `api/session-controller/src/media-references.ts:19`.
- **`session.webRequest` del `defaultSession`:** solo reescribe las cabeceras de `ws://127.0.0.1/*` hacia el Host (`apps/desktop/src/main.ts:710-721`). No añade CSP ni bloquea otros orígenes.

### 3.2 Políticas de Electron que influyen

**Ventana principal** (`apps/desktop/src/main.ts:229-237`):

- `webPreferences`: `contextIsolation: true`, `sandbox: true`, `webSecurity: true` (CORS activo) y `webviewTag: primary`.
- **Origen de la app:** la app se carga desde `dsh-app://app/` (`main.ts:399`). El esquema se registra como `standard`, `secure`, `supportFetchAPI`, `corsEnabled` y `stream` (`main.ts:132-143`; `rc2:lib/main.js:11019`).
- **Navegación del marco principal:** `will-navigate` solo actúa sobre el marco principal. Una navegación a `http(s)` de otro origen se cancela y se abre en el navegador del sistema (`main.ts:303-311`). No hay `will-frame-navigate` en la ventana principal, así que **los iframes pueden navegar**.
- **Ventanas nuevas:** `setWindowOpenHandler` abre los `http(s)` en el navegador externo y deniega la ventana (`main.ts:239-242`). Un enlace con `target=_blank` en un panel abre el navegador del sistema.

**Contenido mixto:**

- **Nuestro caso:** **no se aplica**, porque `dsh-app:` no es `https:`. Chromium solo restringe el contenido mixto cuando el origen es `https`:
  - `SchemeRegistry::ShouldTreatURLSchemeAsRestrictingMixedContent` devuelve `scheme == "https"` (chromium/src `third_party/blink/renderer/platform/weborigin/scheme_registry.cc`);
  - `CalculateHttpsState` solo da `kModern` cuando el protocolo es `https` (`…/platform/loader/fetch/https_state.cc`);
  - `MixedContentChecker::IsMixedContent` depende de ambos (`…/core/loader/mixed_content_checker.cc`).
- **[inferencia]** Lo anterior se ha comprobado en la rama `main` de Chromium, no en la versión exacta de Electron 44.

### 3.3 Veredicto por técnica

| Técnica | ¿Funciona? | Detalle |
|---|---|---|
| `<iframe src="http://srv:8080/…">` en un panel del plugin | **Sí, técnicamente** [inferencia: no probado en la app] | Sin CSP y sin contenido mixto. Pero: (1) el destino no debe enviar `X-Frame-Options` ni `frame-ancestors` restrictivos (el frontal de WeKnora envía `X-Frame-Options "SAMEORIGIN"`, `WeKnora/frontend/nginx.conf:33`); (2) las cookies del servidor son de terceros en el iframe: con `SameSite=Lax` (el valor por defecto) no se envían, y `SameSite=None` exige `Secure`, o sea HTTPS; (3) no hereda tema, fuente ni atajos, y obliga a un segundo inicio de sesión. |
| `<webview>` propio | **No** | `webviewTag` está activo, pero `will-attach-webview` cancela cualquier `webview` sin un *lease* que se pide por IPC al puente interno `dshDesktop.browser` (`apps/desktop/src/browser-guests.ts:72-93`). Usar ese puente desde un plugin es usar una API interna no documentada. |
| Pestaña «Navegador» oficial del panel derecho | **Sí** | `ctx.sidebarRight.openTab('browser', { params: { url } })`: el tipo `browser` admite `params.url` (`ui-sidebar-browser/src/client/index.ts:33-36`; `definition.tsx:9`; `rc2:dsh-client-ui-sidebar-browser/lib/client.js:1430`). En escritorio usa un `webview` aislado: partición propia, permisos denegados, sin descargas, y solo bloquea el puerto del Host local (`browser-guests.ts:141-169`). Muestra la barra de direcciones y requiere una conversación abierta. Sirve para abrir la administración de WeKnora o un vídeo, no como interfaz principal. |
| Navegar toda la ventana a la SPA | **No** | `will-navigate` lo impide y lo abre fuera (`main.ts:303-311`). |

---

## 4. ¿Puede el renderer hacer `fetch()` a otro origen?

- **CSP:** no hay `connect-src` (§3.1), así que la CSP no lo impide.
- **CORS:** sí se aplica, porque `webSecurity: true` (`main.ts:234`).
  - El origen de la página es `dsh-app://app`. `forwardWebRequest` así lo espera (`web-document.ts:79-80`; `rc2:lib/main.js`: `origin !== "dsh-app://app"` → 403).
  - El gateway tendría que responder `Access-Control-Allow-Origin: dsh-app://app` y atender los *preflight* de `POST` JSON.
- **Permisos de Chromium:** el `defaultSession` concede todos los permisos que no son de medios: `if (permission !== 'media') { callback(true) }` (`apps/desktop/src/microphone-permissions.ts:23-24`).
  - **[inferencia]** Si Electron 44 pidiera permiso de *Local Network Access* para IPs privadas, se concedería sin preguntar.
  - Hay un indicio de que funciona: la app ya abre su WebSocket desde `dsh-app://app` contra `ws://127.0.0.1` (`main.ts:689, 710-721`).
- **Conclusión:** es posible, pero hay que configurar CORS para un origen no estándar y **el token del gateway quedaría en el renderer**. Además se duplicaría la lógica de URL y reconexión. **No lo recomendamos** si el Host del plugin puede hacer de proxy (§5 y §6).

---

## 5. Comunicación cliente↔Host propia de un plugin

### 5.1 Recorrido real de una petición en escritorio (verificado)

```text
renderer  fetch('cidia/gw/x')  ──►  dsh-app://app/cidia/gw/x
Electron  protocol.handle('dsh-app')  (main.ts:662-675; rc2:lib/main.js:11542)
          ├─ '/', '/index.html', '/assets/*', favicon, manifest → ficheros de dsh-web-frontend
          └─ cualquier otra ruta → forwardWebRequest(request, hostUrl, hostCookie)
                 (web-document.ts:77-93: copia método, cuerpo en streaming con duplex 'half',
                  pone la cookie de sesión del Host y quita host/origin/sec-fetch-site;
                  la respuesta vuelve en streaming sin set-cookie)
Host      http://127.0.0.1:<puerto aleatorio>  (apps/desktop-host/src/index.ts:30,103: '--port 0')
          dsh-host-webserver → tabla exacta, luego el prefijo más largo, luego el fallback
```

- **Lo mismo hace dsh con su propio RPC:** usa rutas relativas al documento, del tipo `api/<ns>/<método>` (`packages/client/connection/src/client/rpc.ts:46-57`). En escritorio no se sobrescribe el `fetch` del transporte: `__DSH_TRANSPORT__ = { ownsHost: true, streamBaseUrl }` (`apps/web/src/main.ts:24-26`).
- **Documentación desfasada:** `docs/subsystems/web-server.md:5` dice que Electron usa `file://` y un puente IPC. **El código de 0.2.0-rc.2 y 0.2.1-alpha.1 hace lo descrito arriba**, con esquema `dsh-app` y reenvío HTTP.

### 5.2 Mecanismos disponibles para el Host de un plugin

| Mecanismo | API (Host) | Llamada (cliente) | Autenticación | Formato | Evidencia |
|---|---|---|---|---|---|
| **Ruta HTTP propia** (recomendada) | `ctx.webServer.register({ kind: 'prefix', path: '/cidia', handler(req, res) })` | `fetch('cidia/…')` | La comprueba el plugin con `ctx.connection.requestRejection(req)` (Host de loopback, Origin y cookie) | Cualquier método, streaming, subidas, descargas, SSE | `packages/host/webserver` (`web-server.md:111-124`); `rc2:dsh-host-webserver/lib/index.js:177-187`; `rc2:dsh-client-connection/lib/index.js:586-589`; valla en `api-request-trust.ts:91-121` |
| **Canal RPC propio** | `ctx.connection.rpc.handle('/cidia-rpc', async (endpoint, payload, signal) => ({ ok: true, value }))` | `ctx.connection.rpc.call('/cidia-rpc', 'endpoint', payload, signal)` → `{ ok, value }` o `{ ok:false, error }` | La hace Connection (`admit`) | Solo `POST` JSON, con búfer | `packages/client/connection/src/rpc-host.ts:84-90, 170-195`; cliente en `client/rpc.ts:34-70`; `rc2:…/lib/index.js:573-578, 641-657` y `rc2:…/lib/client.js:1212-1224` |
| Ruta Fetch exacta bajo `/api` | `ctx.connection.fetch.register({ path: '/api/cidia/x', methods: ['GET','POST'], requestBody: 'buffered', fetch: async (request) => Response })` | `fetch('api/cidia/x')` | La hace Connection | Ruta **exacta**, sin prefijo | `rpc.ts:137-163`; `rpc-host.ts:96-101, 152-168`; `rc2:…/lib/index.js:581-584, 625-639` |
| `ctx.remote.<ns>` (`@Remote` / Typert) | Exige generar código en tiempo de compilación | — | — | — | **No sirve para plugins de terceros**: el cliente solo monta lo que incluye `@deepseek-ai/dsh-api-remotes` (`docs/api-gateway.md:78`; `docs/cookbook/adding-a-remote-api.md:92, 105`). |
| Ajustes como buzón (el truco actual) | `ctx.settings.update` + sondeo | `remote.settings.mutate` | — | Valores en `cordis.patch.yml` de `~/.dsh` | `cidia-proveedores/suscripcion/index.js:6-11, 76-79`. Funciona, pero escribe en el perfil y tiene latencia. |

**Detalles verificados:**

- **Registro de rutas:** `ctx.webServer.register` **no** se ata solo al ciclo de vida del plugin (`rc2:dsh-host-webserver/lib/index.js:177-187` devuelve un disposer sin más). Hay que envolverlo en `ctx.effect(...)`. `rpc.handle` y `fetch.register` sí usan `owner.effect` internamente (`rc2:…/connection/lib/index.js:625-657`).
- **Interceptor de `/api`:** `ctx.connection.rpc.intercept('/api', …)` **no está disponible**. Solo admite un interceptor por canal y lo ocupa el gateway Typert (`rpc-host.ts:197-217`).
- **Rutas con nombre:** las rutas `exact` y `prefix` tienen prioridad sobre el fallback de la SPA (`web-server.md:27`). `/cidia` no choca con nada de dsh.

### 5.3 Ejemplo mínimo verificado (ruta HTTP)

**Host** (`index.js` del plugin; versión completa en el §8):

```js
export const name = 'cidia-ui'
export const inject = ['webServer', 'connection']
export function apply(ctx) {
  ctx.effect(() => ctx.webServer.register({
    kind: 'prefix', path: '/cidia',
    handler(req, res) {
      const rejection = ctx.connection.requestRejection(req)          // 401/403 o undefined
      if (rejection !== undefined) { res.writeHead(rejection); res.end(); return }
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ pong: true, ruta: req.url }))
    },
  }), 'cidia-ui: /cidia')
}
```

**Cliente:**

```js
const r = await fetch('cidia/ping')   // relativa al documento, como 'api/…' de dsh
const data = await r.json()            // { pong: true, ruta: '/cidia/ping' }
```

**Variante RPC.** Se ha verificado contra el código y la rc.2, pero **no se ha ejecutado**:

```js
// Host
export const inject = ['connection']
export function apply(ctx) {
  ctx.connection.rpc.handle('/cidia-rpc', async (endpoint, payload, signal) =>
    endpoint === 'ping' ? { ok: true, value: { pong: payload?.n ?? 0 } }
      : { ok: false, error: { code: 'cidia/unknown-endpoint', message: endpoint, details: {} } })
}
// Cliente (inject: ['connection'])
const result = await ctx.connection.rpc.call('/cidia-rpc', 'ping', { n: 1 })   // { ok: true, value: { pong: 1 } }
```

---

## 6. ¿Puede el Host del plugin hacer peticiones HTTP salientes al gateway?

**Sí.**

- **Entorno de ejecución:** el Host corre en el Node 24 de la app (`resources/runtime/primary-runtime/runtime.json`: `"node": "24.21.0"`), que trae `fetch`, `AbortSignal.timeout`, `Readable.fromWeb` y `toWeb`. `cidia-proveedores/suscripcion` ya ejecuta código de red en el Host a través de `ctx.authorization`.
- **Proxy corporativo:** dsh instala una política global para el `fetch` de Node a partir de `HTTP(S)_PROXY` y `NO_PROXY`. El tráfico de loopback va directo (`packages/util/http-proxy/README.md:12, 32`; `src/policy.ts:33`).
  - **Consecuencia:** en una empresa con proxy, el instalador debe añadir el host del gateway a `NO_PROXY`.
- **Probado (§8.4):** la versión completa del proxy, con JSON, cuerpo `POST`, SSE en streaming, propagación de cancelación, 401 y gateway caído.

---

## 7. Recomendación argumentada

### 7.1 Comparación de opciones

| Criterio | (a) Paneles React + rutas Host como proxy | (b) iframe a una SPA del gateway | (c) `fetch` directo del renderer al gateway |
|---|---|---|---|
| Aspecto | El de la app: primitivas, tokens de tema, claro y oscuro, cabecera arrastrable | Ajeno; habría que copiar el tema a mano | El de la app |
| Integración con la barra lateral, el chat y el panel derecho | Total. Paneles por permisos, `selectPanel`, pestañas laterales, cards en el chat | Mínima: necesita igualmente un plugin cliente que lo envuelva | Total |
| Sesión y token | En el Host; el renderer nunca ve el token | Cookies de terceros problemáticas en HTTP (§3.3) | El token queda en el renderer |
| Red | Mismo origen: sin CORS, LNA ni contenido mixto. Proxy corporativo gestionado | Depende de `X-Frame-Options` del destino (WeKnora: `SAMEORIGIN`) | Exige CORS para `dsh-app://app` |
| Subidas y streaming (vídeo, audio, progreso SSE) | Sí. Probado SSE; el reenvío de Electron también es streaming (`web-document.ts:68-93`) | Sí, dentro del iframe | Sí |
| Funciona con `dsh web` (navegador) | Sí, la ruta relativa vale igual | Sí | CORS adicional por cada origen |
| Coste | Escribir los paneles en React; la API REST del gateway ya está prevista en el plan | Una SPA aparte y doble login | Como (a), con menos seguridad |
| Riesgo de versión | APIs idénticas en rc.2 y 0.2.1-alpha.1; son contratos documentados (`slots.md`, `web-server.md`) | Bajo | Bajo |

**Decisión: (a).** Cumple «interfaces claras, bonitas y muy fluidas» porque usa los componentes y el tema de la propia app. Encaja con «cada servicio es un plugin de la app» y «la administración va dentro de la misma app». Y mantiene el gateway como única fuente de verdad sin exponer tokens.

**Complemento (c′).** Para pantallas de terceros que ya existen y solo usa un administrador, como la consola de WeKnora, basta abrir la pestaña oficial del navegador del panel derecho: `ctx.sidebarRight.openTab('browser', { params: { url } })`. No hace falta un iframe propio.

### 7.2 Arquitectura propuesta

```text
┌─────────────────────────── App CidIA (dsh 0.2.x, Electron) ───────────────────────────┐
│ Renderer dsh-app://app                                                                  │
│  cidia-ui/client.js                                                                     │
│   ├ sidebar.brand.mark/name (priority -10) ← logo CidIA                                  │
│   ├ sidebar.footer.action  ← botón sesión + Modal de login                               │
│   ├ sidebar.panellist + main[key]  ← Inicio · Mi formación · Captura · Progreso · Admin   │
│   │     (se registran o retiran en vivo según permisos)                                  │
│   └ sidebar.right.pane.tab ← «Paso a paso» junto al chat (opcional)                      │
│        │ fetch('cidia/session' | 'cidia/gw/<ruta REST>')  (mismo origen)                 │
│ Electron main: protocol.handle → forwardWebRequest (+cookie Host)                       │
│ Host Node (127.0.0.1:aleatorio)                                                          │
│  cidia-ui/index.js  inject: webServer, connection                                       │
│   ├ /cidia/session  → login/logout; guarda el token CidIA (memoria)                      │
│   └ /cidia/gw/*     → proxy con Bearer → gateway (fetch Node, streaming, timeouts)       │
└──────────────────────────────────────────┬──────────────────────────────────────────────┘
                                           │ HTTP(S) LAN
                     Gateway CidIA (FastAPI): API REST de paneles · MCP + OpenAI-compatible para el agente
```

Cada servicio de las bases (formación, captura, evaluación, progreso, administración) puede ser un subpaquete del mismo plugin, como `cidia-proveedores/suscripcion`, con su propia entrada en `cordis.patch.yml`. Así se activa o desactiva por separado desde Ajustes → Plugins. El Host de proxy se comparte.

---

## 8. Esqueleto mínimo del enfoque recomendado (probado)

Ficheros probados en `scratchpad/test-cidia-ui/plugin/`. Las rutas del gateway, como `/api/v1/auth/login` y `/api/v1/formacion/mia`, son **ejemplos**: las fija el equipo del gateway.

### 8.1 `package.json`

```json
{
  "name": "cidia-ui",
  "version": "0.1.0",
  "description": "Interfaz de CidIA: paneles de servicios, sesión y marca.",
  "type": "module",
  "main": "index.js",
  "exports": {
    ".": "./index.js",
    "./client": "./client.js",
    "./package.json": "./package.json"
  },
  "files": ["index.js", "client.js", "cordis.patch.yml"],
  "dsh": {
    "bundle": { "patch": "./cordis.patch.yml" },
    "client": {
      "platform": "web",
      "inject": ["@deepseek-ai/dsh-client-ui-sidebar", "@deepseek-ai/dsh-client-ui-layout"]
    }
  },
  "peerDependencies": { "@deepseek-ai/schemastery": "*" }
}
```

### 8.2 `cordis.patch.yml`

Las inserciones con `config` siguen el patrón de `packages/bundle/base/cordis.patch.yml:29-33`.

```yaml
- insert:
    - id: cidia-ui
      name: cidia-ui
      config:
        gatewayUrl: http://192.168.1.50:8000   # la escribe el instalador
```

**Instalación en el perfil:** igual que `cidia-proveedores`. En `~/.dsh/profiles/desktop/package.json` se añade `"cidia-ui": "link:<ruta>"` (o la versión empaquetada) y `"cidia-ui"` en `dsh.profile.bundles`.

### 8.3 `index.js` (Host: proxy autenticado)

```js
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import z from '@deepseek-ai/schemastery'

export const name = 'cidia-ui'
export const inject = ['webServer', 'connection']

export const Config = z.object({
  gatewayUrl: z.string().default('http://127.0.0.1:8000').description('URL base del gateway CidIA (API REST de paneles).'),
  timeoutMs: z.natural().default(15000).description('Tiempo máximo de espera de las peticiones al gateway (ms).'),
})

const PREFIX = '/cidia'
// Cabeceras que no se reenvían en ninguno de los dos sentidos.
const DROP = new Set([
  'host', 'cookie', 'origin', 'referer', 'connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer',
  'upgrade', 'proxy-authorization', 'proxy-authenticate', 'content-length', 'accept-encoding',
  'content-encoding', 'set-cookie', 'authorization',
])

function sendJson(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(body))
}

async function readJson(req) {
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  const text = Buffer.concat(chunks).toString('utf8')
  return text === '' ? {} : JSON.parse(text)
}

export function apply(ctx, config) {
  /** Sesión CidIA del trabajador en este equipo (en memoria del Host). */
  let session = null // { token, usuario, permisos }
  const base = () => String(config.gatewayUrl).replace(/\/+$/, '')

  async function gateway(path, init = {}) {
    const headers = { ...init.headers }
    if (session !== null) headers.authorization = `Bearer ${session.token}`
    return fetch(base() + path, { ...init, headers, redirect: 'manual', signal: init.signal ?? AbortSignal.timeout(config.timeoutMs) })
  }

  // --- /cidia/session: inicio y cierre de sesión contra el gateway -----------------
  async function handleSession(req, res) {
    if (req.method === 'GET') {
      sendJson(res, 200, session === null ? { conectado: false } : { conectado: true, usuario: session.usuario, permisos: session.permisos })
      return
    }
    if (req.method === 'DELETE') {
      session = null
      sendJson(res, 200, { conectado: false })
      return
    }
    if (req.method !== 'POST') { sendJson(res, 405, { error: 'method_not_allowed' }); return }
    const { usuario, clave } = await readJson(req)
    // RUTA DE EJEMPLO: la define el equipo del gateway.
    const upstream = await gateway('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ usuario, clave }),
    })
    const body = await upstream.json().catch(() => ({}))
    if (!upstream.ok) { sendJson(res, upstream.status, { error: body.error ?? 'login_failed' }); return }
    session = { token: body.token, usuario: body.usuario, permisos: body.permisos ?? [] }
    sendJson(res, 200, { conectado: true, usuario: session.usuario, permisos: session.permisos })
  }

  // --- /cidia/gw/<ruta>: proxy genérico (JSON, subidas, descargas y SSE) ----------
  async function handleProxy(req, res, path, search) {
    const headers = {}
    for (const [key, value] of Object.entries(req.headers)) {
      if (!DROP.has(key) && typeof value === 'string') headers[key] = value
    }
    const abort = new AbortController()
    // Si el renderer cancela (cierra el panel), se corta también la petición al gateway.
    res.on('close', () => { if (!res.writableFinished) abort.abort() })
    const hasBody = req.method !== 'GET' && req.method !== 'HEAD'
    const upstream = await gateway(path + search, {
      method: req.method,
      headers,
      ...(hasBody ? { body: Readable.toWeb(req), duplex: 'half' } : {}),
      signal: abort.signal,
    })
    if (upstream.status === 401) session = null // token caducado: la interfaz vuelve a pedir sesión
    const out = {}
    for (const [key, value] of upstream.headers) if (!DROP.has(key)) out[key] = value
    res.writeHead(upstream.status, out)
    if (upstream.body === null || req.method === 'HEAD') { res.end(); return }
    await pipeline(Readable.fromWeb(upstream.body), res)
  }

  async function handler(req, res) {
    // Misma valla que /api: Host de loopback + cookie de la sesión del navegador de la app.
    const rejection = ctx.connection.requestRejection(req)
    if (rejection !== undefined) { res.writeHead(rejection); res.end(); return }
    const url = new URL(req.url ?? '/', 'http://local')
    const sub = url.pathname.slice(PREFIX.length)
    try {
      if (sub === '/session') { await handleSession(req, res); return }
      if (sub.startsWith('/gw/')) { await handleProxy(req, res, sub.slice('/gw'.length), url.search); return }
      sendJson(res, 404, { error: 'not_found' })
    } catch (error) {
      ctx.logger?.warn?.(error)
      if (!res.headersSent) sendJson(res, 502, { error: 'gateway_unreachable', message: String(error?.message ?? error) })
      else res.destroy()
    }
  }

  // ctx.webServer.register no se ata solo al ciclo de vida del plugin: se envuelve en ctx.effect.
  ctx.effect(() => ctx.webServer.register({ kind: 'prefix', path: PREFIX, handler }), 'cidia-ui: rutas /cidia')
}
```

### 8.4 `client.js` (paneles, sesión y marca)

```js
window.__ModuleLoader__.load({
  id: 'cidia-ui',
  factory(require) {
    const React = require('react')
    const { Button, Input, Modal, IconUserOutlineRegular, IconGaugeOutlineRegular, IconSettingsOutlineRegular, IconSparkleRegular } =
      require('@deepseek-ai/dsh-client-ui-primitives')
    const h = React.createElement
    const { useState, useEffect } = React

    // Estilos propios: un <style> creado durante el factory queda etiquetado (data-plugin)
    // por el cargador y se retira al desactivar el plugin. Solo tokens --dsw-alias-*.
    const style = document.createElement('style')
    style.textContent = `
      .cidia-page { height: 100%; overflow: auto; background: var(--dsw-alias-bg-base); color: var(--dsw-alias-label-primary); }
      .cidia-head { padding: calc(28px + var(--dsh-frame-top-clearance, 0px)) clamp(24px, 5vw, 48px) 16px; }
      .cidia-head h1 { margin: 0; font-size: 22px; font-weight: 600; }
      .cidia-body { max-width: 960px; padding: 0 clamp(24px, 5vw, 48px) 48px; }
      .cidia-card { padding: 16px 20px; border-radius: 16px; background: var(--dsw-alias-bg-layer-1); margin-bottom: 12px; }
      .cidia-muted { color: var(--dsw-alias-label-tertiary); font-size: 13px; }
      .cidia-error { color: var(--dsw-alias-state-error-primary); font-size: 13px; }
      .cidia-form { display: flex; flex-direction: column; gap: 10px; }
    `
    document.head.appendChild(style)

    // ---- Transporte: rutas del Host del propio plugin (mismo origen dsh-app://app) ----
    // Ruta relativa al documento, igual que el RPC de dsh ('api/...').
    async function call(path, init = {}) {
      const response = await fetch('cidia/' + path, {
        ...init,
        headers: init.body !== undefined ? { 'content-type': 'application/json', ...init.headers } : init.headers,
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw Object.assign(new Error(body.message ?? body.error ?? `HTTP ${response.status}`), { status: response.status })
      return body
    }
    const api = {
      session: () => call('session'),
      login: (usuario, clave) => call('session', { method: 'POST', body: JSON.stringify({ usuario, clave }) }),
      logout: () => call('session', { method: 'DELETE' }),
      get: path => call('gw' + path),
      post: (path, data) => call('gw' + path, { method: 'POST', body: JSON.stringify(data) }),
    }

    // ---- Estado de sesión: fuente observable {getSnapshot, subscribe} ------------------
    // El renderizador de dsh convierte inject().hooks.cidia en la prop useCidia(selector).
    let snapshot = { conectado: false, usuario: null, permisos: [] }
    const listeners = new Set()
    const sessionStore = {
      getSnapshot: () => snapshot,
      subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener) } },
      set(next) { snapshot = { conectado: !!next.conectado, usuario: next.usuario ?? null, permisos: next.permisos ?? [] }; for (const l of [...listeners]) l() },
    }
    const refreshSession = () => api.session().then(s => sessionStore.set(s), () => sessionStore.set({ conectado: false }))

    // ---- Componentes -----------------------------------------------------------
    function Page({ title, children }) {
      return h('div', { className: 'cidia-page' },
        h('header', { className: 'cidia-head', 'data-window-drag': '' }, h('h1', null, title)),
        h('div', { className: 'cidia-body' }, children))
    }

    function InicioPage({ useCidia }) {
      const usuario = useCidia(s => s.usuario)
      return h(Page, { title: usuario ? `Hola, ${usuario}` : 'CidIA' },
        h('div', { className: 'cidia-card' },
          usuario ? 'Elige un servicio en la barra lateral.' : 'Sin sesión puedes usar el chat general y los documentos públicos. Inicia sesión para ver tus servicios.'))
    }

    function FormacionPage() {
      const [data, setData] = useState(null)
      const [error, setError] = useState(null)
      useEffect(() => {
        let alive = true
        // RUTA DE EJEMPLO del gateway: la fija el equipo del gateway.
        api.get('/api/v1/formacion/mia').then(d => { if (alive) setData(d) }, e => { if (alive) setError(e.message) })
        return () => { alive = false }
      }, [])
      return h(Page, { title: 'Mi formación' },
        error ? h('div', { className: 'cidia-error' }, error)
          : data === null ? h('div', { className: 'cidia-muted' }, 'Cargando…')
            : h('div', { className: 'cidia-card' }, h('div', null, data.itinerario), h('div', { className: 'cidia-muted' }, `Nivel ILUO: ${data.nivel}`)))
    }

    function AdminPage() {
      return h(Page, { title: 'Administración' }, h('div', { className: 'cidia-card' }, 'Empresa, departamentos, puestos y permisos.'))
    }

    // Botón de sesión al pie de la barra lateral, junto a Ajustes (owner: { wide }).
    function SessionAction({ wide, useCidia }) {
      const usuario = useCidia(s => s.usuario)
      const [open, setOpen] = useState(false)
      const [form, setForm] = useState({ usuario: '', clave: '' })
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState(null)
      const submit = async (event) => {
        event.preventDefault()
        setBusy(true); setError(null)
        try { sessionStore.set(await api.login(form.usuario, form.clave)); setOpen(false); setForm({ usuario: '', clave: '' }) } catch (e) { setError(e.status === 401 ? 'Usuario o contraseña incorrectos.' : e.message) }
        setBusy(false)
      }
      const label = usuario ?? 'Iniciar sesión'
      return h(React.Fragment, null,
        h(Button, {
          variant: 'ghost', size: 'sm', icon: h(IconUserOutlineRegular, { size: 16 }), title: label, 'aria-label': label,
          onClick: () => { if (usuario) void api.logout().then(s => sessionStore.set(s)); else setOpen(true) },
        }, wide ? label : null),
        h(Modal, {
          open, onClose: () => { setOpen(false) }, title: 'Iniciar sesión en CidIA', closeLabel: 'Cerrar',
          footer: h(Button, { variant: 'primary', type: 'submit', form: 'cidia-login', disabled: busy }, busy ? 'Entrando…' : 'Entrar'),
        },
        h('form', { id: 'cidia-login', className: 'cidia-form', onSubmit: submit },
          h(Input, { 'data-modal-autofocus': '', placeholder: 'Usuario', autoComplete: 'username', value: form.usuario, onChange: e => setForm({ ...form, usuario: e.target.value }) }),
          h(Input, { type: 'password', placeholder: 'Contraseña', autoComplete: 'current-password', value: form.clave, onChange: e => setForm({ ...form, clave: e.target.value }) }),
          error ? h('div', { className: 'cidia-error', role: 'alert' }, error) : null)))
    }

    function CidiaMark({ size }) {
      return h('svg', { width: size, height: size, viewBox: '0 0 24 24', 'aria-hidden': 'true' },
        h('rect', { x: 2, y: 2, width: 20, height: 20, rx: 6, fill: 'var(--dsw-alias-brand-primary-new-colorprimary-new-color, #3b6cff)' }),
        h('text', { x: 12, y: 16.5, textAnchor: 'middle', fontSize: 11, fontWeight: 700, fill: '#fff' }, 'C'))
    }
    function CidiaName() { return h('span', { style: { fontWeight: 600 } }, 'CidIA') }

    // ---- Catálogo de paneles: un id por panel = clave 'main' + fila 'sidebar.panellist' ----
    const PANELS = [
      { id: 'cidia.inicio', label: 'Inicio', order: 1, permiso: null, icon: IconSparkleRegular, page: InicioPage },
      { id: 'cidia.formacion', label: 'Mi formación', order: 2, permiso: 'formacion', icon: IconGaugeOutlineRegular, page: FormacionPage },
      { id: 'cidia.admin', label: 'Administración', order: 9, permiso: 'admin', icon: IconSettingsOutlineRegular, page: AdminPage },
    ]

    return {
      inject: ['slots'],
      apply(ctx) {
        const injected = () => ({ hooks: { cidia: sessionStore } })
        // Marca: ocupa los slots 'single' con prioridad menor que la marca oficial (default 0).
        ctx.slots.inject('sidebar.brand.mark', () => ctx.slots.register({ name: 'sidebar.brand.mark', priority: -10 }, CidiaMark))
        ctx.slots.inject('sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name', priority: -10 }, CidiaName))
        ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
          name: 'sidebar.footer.action', id: 'cidia.sesion', order: -10, inject: injected,
        }, SessionAction))

        // Paneles según permisos: se registran y retiran en vivo al cambiar la sesión.
        // 'main' y 'sidebar.panellist' viven en declaraciones distintas (ui-layout y ui-sidebar),
        // así que se espera a ambas; la fila de la barra lateral se registra después del panel.
        ctx.slots.inject('main', () => ctx.slots.inject('sidebar.panellist', () => {
          const active = new Map() // id -> disposer
          const sync = () => {
            const { permisos } = sessionStore.getSnapshot()
            for (const panel of PANELS) {
              const allowed = panel.permiso === null || permisos.includes(panel.permiso) || permisos.includes('admin')
              if (allowed && !active.has(panel.id)) {
                const offMain = ctx.slots.register({ name: 'main', key: panel.id, inject: injected }, panel.page)
                const Icon = panel.icon
                const offRow = ctx.slots.register({ name: 'sidebar.panellist', id: panel.id, order: 100 + panel.order, label: panel.label },
                  ({ size }) => h(Icon, { size }))
                active.set(panel.id, () => { offRow(); offMain() })
              } else if (!allowed && active.has(panel.id)) {
                active.get(panel.id)()
                active.delete(panel.id)
              }
            }
          }
          sync()
          const unsubscribe = sessionStore.subscribe(sync)
          return () => { unsubscribe(); for (const dispose of active.values()) dispose(); active.clear() }
        }))

        void refreshSession()
      },
    }
  },
})
```

### 8.5 Pruebas ejecutadas

En este PC, con Node 22.23.2, sin instalar nada y sin tocar la app ni `~/.dsh`:

- **`test-host.mjs`: 10 de 10 superadas.**
  - **Entorno:** un `ctx` simulado con la forma de la rc.2 (`webServer.register` por prefijo y `connection.requestRejection`), un Host `node:http` con el enrutado por prefijo de `dsh-host-webserver` y un gateway simulado. Schemastery real, copiado del asar.
  - **Casos cubiertos:**
    - 401 sin cookie;
    - estado de sesión, login incorrecto y correcto, y comprobación de que el token **no** llega al renderer;
    - `GET` con query, con `Bearer` añadido y **sin** reenviar la cookie del Host;
    - `POST` con JSON;
    - **SSE en streaming**: el primer evento llega antes de terminar la respuesta;
    - cierre de sesión;
    - gateway caído, que devuelve 502 legible;
    - retirada de la ruta al descargar el plugin.
- **`test-client.cjs`: superada.**
  - **Entorno:** un `window.__ModuleLoader__` simulado y la tabla de módulos con React 18.3.1 real, tomado en solo lectura de otro proyecto del PC. Primitivas simuladas con la firma de la rc.2.
  - **Casos cubiertos:**
    - el factory se materializa;
    - `apply` registra marca (`priority -10`), botón de sesión e «Inicio»;
    - tras iniciar sesión con permiso `formacion` aparece «Mi formación»;
    - con permiso `admin` aparece «Administración»;
    - al cerrar sesión quedan solo los paneles públicos;
    - `renderToStaticMarkup` de todas las vistas, con `useCidia` generado como lo hace dsh, sin avisos de React.
- **No probado:** la carga dentro de la app real, porque esta fase no permite tocar `~/.dsh`. **Es el primer paso de la fase siguiente:** instalar `cidia-ui` en un perfil de pruebas como se instaló `cidia-proveedores` y comprobar `fetch('cidia/session')` con DevTools (`devTools: true`, `main.ts:236`).

---

## 9. Riesgos y puntos abiertos

1. **Las rutas `/cidia` no tienen tipado ni contrato de dsh.** Conviene versionar la API (`/cidia/v1/...`) y fijar el contrato REST del gateway con OpenAPI. FastAPI lo genera.
2. **El cambio de versión de dsh puede romper detalles internos.** Las piezas que usamos son contratos documentados: `slots.md`, `web-server.md`, el `HostConnectionHandle` de `rpc.ts:193-238` y `sidebar-right.md`. Aun así, dsh es *alpha*: hay que fijar la versión en el instalador y repetir los bancos de pruebas en cada actualización. Aviso: `web-server.md:5` ya está desfasado frente al código.
3. **El token de sesión vive en la memoria del Host.** Se pierde al reiniciar la app y el usuario vuelve a iniciar sesión. Si se quiere persistir, `ctx.credentials` (`docs/subsystems/credentials.md`, `modifyRecord` y `readRecord`) es la vía prevista, pero **[sin verificar]** para plugins de terceros.
4. **El gateway viaja por HTTP en la LAN**, incluidas las credenciales del login. Para la fase con empresa: TLS en el gateway, o al menos red aislada, y `NO_PROXY` en entornos con proxy.
5. **Subidas grandes (vídeo de captura).** Con (a) el fichero pasa por renderer → Electron → Host → gateway. Funciona en streaming, pero si el vídeo se graba en local es mejor que el Host lo suba **directamente desde disco**, en otra ruta `/cidia/subir`, con progreso por SSE.
6. **La API REST de paneles del gateway está por definir.** El esqueleto usa rutas de ejemplo.
7. **El rebrand completo no se consigue solo con plugins.** El título de la ventana (`productTitle`, `<title>` de `dsh-web-frontend`), el instalador y los textos de dsh en inglés y chino requieren el rebrand compilado (fase 4) o parches del frontal; queda fuera de este informe. Los slots de marca sí cubren el logo y el nombre de la barra lateral y del estado vacío del chat.
8. **La interfaz de dsh no tiene castellano** (`ctx.locale.register` con `zh` y `en`). Los textos de CidIA van en castellano directamente en el plugin. Hay que decidir si se aporta un diccionario `es` a los espacios de nombres de dsh.
9. **Las secciones oficiales «Plugins» y «Tareas»** seguirán en la barra lateral salvo que el patch de perfil las desactive (`disabled: true` en `ui-plugin-manager` y `ui-schedule`). Hay que decidir qué ve un trabajador frente a un administrador.
