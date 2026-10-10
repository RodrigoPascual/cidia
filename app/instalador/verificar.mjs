// Verificación de una instalación de CidIA sin interfaz gráfica, por el protocolo CDP.
//
//   "%LOCALAPPDATA%\Programs\CidIA\CidIA.exe" --remote-debugging-port=9333
//   node app/instalador/verificar.mjs [--puerto 9333] [--captura captura.png] [--datos <DSH_HOME>]
//                                     [--instalacion <carpeta>] [--sin-marca] [--red 15 | --sin-red]
//
// Comprueba: destino dsh-app://app/, título y marca CidIA, secciones de CidIA en la barra
// lateral, proxy al servidor (cidia/gw/salud), sesión del Host (cidia/estado), interfaz web
// embebida en el iframe con la base del proxy y que la credencial del modelo es el token de la
// sesión (por huellas SHA-256). Node 22 (WebSocket nativo), sin dependencias.
// Castellano de la app base: la barra de menús de la ventana dice «Aplicación · Edición» (falla si
// vuelve a salir «Application · Edit») y el app.asar instalado lleva el diccionario 'es' y el menú
// sin «Buscar actualizaciones» ni «Gestionar la orden dsh» (traducir-app.mjs, comprobarApp).
// Red: durante --red segundos (15 por defecto) mira las conexiones TCP de los procesos de la
// instalación y falla si alguna va fuera del equipo y del servidor CidIA. --sin-red lo omite.
// En Windows, además, la marca en el sistema (verificar-marca.ps1): ejecutable app\CidIA.exe con
// el icono y los datos de versión de CidIA, icono de la bandeja, accesos directos y AppUserModelID
// de la ventana en la barra de tareas (no se agrupa con DeepSeek Harness). --sin-marca lo omite;
// --instalacion cambia la carpeta de la instalación.
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { lookup } from 'node:dns/promises'
import { isIP } from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { comprobarApp } from './traducir-app.mjs'

const args = process.argv.slice(2)
const opcion = (nombre, porDefecto) => {
  const i = args.indexOf(nombre)
  return i >= 0 ? args[i + 1] : porDefecto
}
const puerto = opcion('--puerto', '9333')
const captura = opcion('--captura', null)
const datos = opcion('--datos', join(process.env.LOCALAPPDATA ?? '', 'CidIA', 'datos'))
const instalacion = opcion('--instalacion', join(process.env.LOCALAPPDATA ?? '', 'Programs', 'CidIA'))
const conMarca = process.platform === 'win32' && !args.includes('--sin-marca')
const segundosRed = process.platform === 'win32' && !args.includes('--sin-red') ? Number(opcion('--red', '15')) : 0

let fallos = 0
const comprobar = (ok, texto, detalle = '') => {
  console.log(`${ok ? 'OK  ' : 'FALLO'} ${texto}${detalle ? ` · ${detalle}` : ''}`)
  if (!ok) fallos += 1
}

const lista = await fetch(`http://127.0.0.1:${puerto}/json/list`).then(r => r.json()).catch(() => null)
if (!lista) {
  console.error(`No responde el puerto de depuración ${puerto}. Abre CidIA con --remote-debugging-port=${puerto}.`)
  process.exit(2)
}
const destino = lista.find(d => d.type === 'page' && d.url.startsWith('dsh-app://app/'))
comprobar(Boolean(destino), 'ventana principal de la app', destino?.url)
if (!destino) process.exit(1)

const ws = new WebSocket(destino.webSocketDebuggerUrl)
await new Promise((ok, mal) => { ws.onopen = ok; ws.onerror = mal })
let n = 0
const pendientes = new Map()
ws.onmessage = (m) => {
  const d = JSON.parse(m.data)
  if (d.id && pendientes.has(d.id)) { pendientes.get(d.id)(d); pendientes.delete(d.id) }
}
const enviar = (method, params = {}) => new Promise((ok) => { const id = ++n; pendientes.set(id, ok); ws.send(JSON.stringify({ id, method, params })) })
const evaluar = async (expresion) => {
  const r = await enviar('Runtime.evaluate', { expression: expresion, awaitPromise: true, returnByValue: true })
  return r.result?.result?.value
}

const estado = await evaluar(`(async () => {
  const espera = ms => new Promise(r => setTimeout(r, ms))
  for (let i = 0; i < 40 && !document.querySelector('[data-cidia-panel]'); i++) await espera(500)
  const marco = document.querySelector('iframe')
  for (let i = 0; i < 40 && marco && marco.contentDocument?.readyState !== 'complete'; i++) await espera(500)
  const salud = await fetch('cidia/gw/salud').then(r => r.json()).catch(e => ({ error: String(e) }))
  const host = await fetch('cidia/estado').then(r => r.json()).catch(e => ({ error: String(e) }))
  const doc = marco?.contentDocument
  // Solo la huella del token de la interfaz: el token no sale del renderer.
  const token = localStorage.getItem('cidia.token')
  const huella = token ? [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token)))]
    .map(b => b.toString(16).padStart(2, '0')).join('') : null
  // Barra de menús de la ventana en Windows (la pinta el preload de la app base en un shadow DOM).
  const raizMenu = document.querySelector('[data-windows-menu]')?.shadowRoot
  return {
    huella,
    menu: raizMenu ? { botones: [...raizMenu.querySelectorAll('button')].map(b => b.textContent), nombre: raizMenu.querySelector('[role=menubar]')?.getAttribute('aria-label') ?? null } : null,
    titulo: document.title,
    idioma: document.documentElement.lang,
    marca: Boolean(document.querySelector('svg rect[fill="#F2C200"]')),
    barra: document.body.innerText.slice(0, 400),
    panel: document.querySelector('[data-cidia-panel]')?.dataset.cidiaPanel ?? null,
    salud, host,
    iframe: marco ? { src: marco.src, base: doc?.querySelector('base')?.getAttribute('href') ?? null, texto: doc?.body?.innerText.slice(0, 80) ?? '' } : null,
  }
})()`)

comprobar(estado?.titulo === 'CidIA' || / · CidIA$/.test(estado?.titulo ?? ''), 'título de la ventana', estado?.titulo)
comprobar(estado?.marca, 'logo de CidIA en la barra lateral')
comprobar(estado?.idioma === 'es', 'idioma de la app', estado?.idioma)
comprobar(/Acceso|Inicio/.test(estado?.barra ?? '') && /Copiloto/.test(estado?.barra ?? ''), 'secciones de CidIA en la barra lateral')
comprobar(estado?.salud?.estado === 'ok', 'proxy al servidor CidIA (cidia/gw/salud)', JSON.stringify(estado?.salud))
comprobar(estado?.host?.conectado === true, 'sesión del Host', `${estado?.host?.modo} · ${estado?.host?.servidor}`)
comprobar(estado?.iframe?.base === '/cidia/gw/app/', 'interfaz web embebida por el proxy', estado?.iframe?.src)

// La credencial del proveedor de modelos (CIDIA_GATEWAY_TOKEN en $DSH_HOME/.credentials.yaml)
// debe ser el mismo token que usa la interfaz. Se comparan huellas, nunca los tokens.
let huellaHost = null
try {
  const texto = readFileSync(join(datos, '.credentials.yaml'), 'utf8')
  const valor = texto.match(/^\s*CIDIA_GATEWAY_TOKEN:\s*(\S+)\s*$/m)?.[1]?.replace(/^["']|["']$/g, '')
  if (valor) huellaHost = createHash('sha256').update(valor).digest('hex')
} catch { /* sin fichero de credenciales */ }
comprobar(Boolean(huellaHost) && huellaHost === estado?.huella, 'credencial del modelo = token de la sesión',
  `${estado?.host?.modo ?? '?'}${huellaHost ? '' : ' · sin CIDIA_GATEWAY_TOKEN en ' + datos}`)

// Castellano de la app base: lo que se ve (barra de menús) y lo que lleva el app.asar instalado
// (menús que se abren, bandeja y cuadros de diálogo, que no se pueden leer por CDP).
if (process.platform === 'win32') {
  const botones = estado?.menu?.botones ?? []
  comprobar(botones.join(' · ') === 'Aplicación · Edición' && estado?.menu?.nombre === 'Menú de la aplicación',
    'barra de menús en castellano', estado?.menu ? `${botones.join(' · ')} (${estado.menu.nombre})` : 'no se encuentra la barra de menús')
}
const asarInstalado = join(instalacion, 'app', 'resources', 'app.asar')
if (existsSync(asarInstalado)) {
  for (const r of comprobarApp(asarInstalado)) comprobar(r.ok, r.texto, r.detalle)
} else {
  comprobar(false, 'castellano de la app base', `no existe ${asarInstalado}`)
}

// Red: conexiones TCP de los procesos de la instalación durante unos segundos. Solo pueden ir al
// propio equipo y al servidor CidIA (la consulta de actualización de la app base la corta el
// lanzador con su proxy sumidero; ver app/README.md §4).
if (segundosRed > 0) {
  const permitidas = new Set(['127.0.0.1', '::1', '0.0.0.0', '::'])
  let servidor = null
  try {
    servidor = new URL(estado?.host?.servidor ?? '').hostname.replace(/^\[|\]$/g, '')
    if (isIP(servidor)) permitidas.add(servidor)
    else for (const d of await lookup(servidor, { all: true })) permitidas.add(d.address)
  } catch { /* sin servidor conocido: solo el equipo */ }
  const guion = `
    $raiz = $env:CIDIA_INSTALACION.TrimEnd('\\') + '\\'
    $fin = (Get-Date).AddSeconds([int]$env:CIDIA_SEGUNDOS)
    $vistas = @{}
    $procesos = 0
    do {
      $ids = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($raiz, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { $_.Id })
      if ($ids.Count -gt $procesos) { $procesos = $ids.Count }
      if ($ids.Count) {
        Get-NetTCPConnection -OwningProcess $ids -ErrorAction SilentlyContinue | Where-Object { $_.State -ne 'Listen' -and $_.State -ne 'Bound' } |
          ForEach-Object { $vistas["$($_.RemoteAddress)|$($_.RemotePort)"] = 1 }
      }
      Start-Sleep -Milliseconds 700
    } while ((Get-Date) -lt $fin)
    "PROCESOS $procesos"
    $vistas.Keys`
  let salida = ''
  try {
    salida = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', guion], {
      encoding: 'utf8', windowsHide: true, env: { ...process.env, CIDIA_INSTALACION: instalacion, CIDIA_SEGUNDOS: String(segundosRed) },
    })
  } catch (error) {
    salida = String(error.stdout ?? '')
  }
  const lineas = salida.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
  const procesos = Number(lineas.find(l => l.startsWith('PROCESOS '))?.slice(9) ?? 0)
  const destinos = lineas.filter(l => l.includes('|')).map(l => { const [a, p] = l.split('|'); return { a: a.replace(/^::ffff:/, ''), p } })
  const fuera = destinos.filter(d => !permitidas.has(d.a))
  comprobar(procesos > 0 && fuera.length === 0, `red: solo el equipo y el servidor CidIA (${segundosRed} s)`,
    procesos === 0 ? 'no hay procesos de CidIA abiertos'
      : fuera.length ? 'fuera: ' + fuera.map(d => `${d.a}:${d.p}`).join(', ')
        : `${procesos} procesos · ${destinos.length} destinos: ${[...new Set(destinos.map(d => `${d.a}:${d.p}`))].slice(0, 6).join(', ') || 'ninguno'}`)
}

if (conMarca) {
  // Una línea «OK …», «FALLO …» o «AVISO …» por comprobación; el código de salida es el número de fallos.
  let salida
  try {
    salida = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
      join(dirname(fileURLToPath(import.meta.url)), 'verificar-marca.ps1'), '-Instalacion', instalacion], { encoding: 'utf8', windowsHide: true })
  } catch (error) {
    salida = String(error.stdout ?? '')
    if (!/^FALLO/m.test(salida)) comprobar(false, 'marca de CidIA en Windows (verificar-marca.ps1)', String(error.stderr ?? error.message).trim().slice(0, 300))
  }
  for (const linea of salida.split(/\r?\n/).filter(Boolean)) {
    const ok = linea.startsWith('OK')
    if (!ok && !linea.startsWith('FALLO')) { console.log(linea); continue }
    const [texto, ...detalle] = linea.replace(/^(OK|FALLO)\s+/, '').split(' · ')
    comprobar(ok, texto, detalle.join(' · '))
  }
}

if (captura) {
  const r = await enviar('Page.captureScreenshot', { format: 'png' })
  writeFileSync(captura, Buffer.from(r.result.data, 'base64'))
  console.log(`Captura guardada en ${captura}`)
}
ws.close()
console.log(fallos === 0 ? '\nCidIA verificada.' : `\n${fallos} comprobación(es) fallida(s).`)
process.exit(fallos === 0 ? 0 : 1)
