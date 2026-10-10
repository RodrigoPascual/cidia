// Visor para revisar la interfaz sin abrir ventanas: Edge o Chrome sin cabeza controlado por CDP.
//
//   node qa/visor.mjs --url http://127.0.0.1:18700/app/planta --salida planta.png \
//        [--token <jwt>] [--ancho 1440] [--alto 900] [--movil] [--esperar 2500] [--pasos pasos.json]
//
// --token     inicia sesión pasando el token en el hash (#token=...), como hace la app.
// --movil     390x844 con pantalla táctil.
// --pasos     JSON con una lista de pasos que se ejecutan tras cargar:
//               {"clic": "selector CSS"}            {"clicTexto": "texto visible del botón o enlace"}
//               {"escribir": ["selector", "texto"]}  {"tecla": "Enter"}
//               {"esperar": 1500}                    {"captura": "fichero.png"}
//               {"eval": "expresión JS"}             {"ir": "/app/otra-ruta"}
// Al terminar imprime un JSON con los errores de consola, las excepciones y las peticiones
// fallidas (4xx/5xx): sirve para detectar fallos además de para mirar las capturas.

import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const args = process.argv.slice(2)
const opt = (n, d) => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : d }
const flag = (n) => args.includes('--' + n)

const NAVEGADORES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
]
const navegador = opt('navegador') ?? NAVEGADORES.find((p) => existsSync(p))
if (!navegador) { console.error('No encuentro Edge ni Chrome'); process.exit(2) }

const movil = flag('movil')
const ancho = Number(opt('ancho', movil ? 390 : 1440))
const alto = Number(opt('alto', movil ? 844 : 900))
const esperar = Number(opt('esperar', 2500))
let url = opt('url')
const token = opt('token')
if (!url) { console.error('Falta --url'); process.exit(2) }
if (token) url += (url.includes('#') ? '&' : '#') + 'token=' + encodeURIComponent(token)
const pasos = opt('pasos') ? JSON.parse(readFileSync(opt('pasos'), 'utf8')) : []
const salida = opt('salida')

const puertoLibre = () => new Promise((ok) => { const s = createServer(); s.listen(0, () => { const p = s.address().port; s.close(() => ok(p)) }) })
const dormir = (ms) => new Promise((r) => setTimeout(r, ms))

const puerto = await puertoLibre()
const perfil = mkdtempSync(join(tmpdir(), 'cidia-visor-'))
const proc = spawn(navegador, [
  '--headless=new', `--remote-debugging-port=${puerto}`, `--user-data-dir=${perfil}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars',
  '--disable-component-update', '--disable-background-networking', '--disable-sync', '--disk-cache-size=1',
  '--disable-extensions', '--no-pings', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required',
  `--window-size=${ancho},${alto}`, 'about:blank',
], { stdio: 'ignore' })

const informe = { url: url.replace(/token=[^&]+/, 'token=***'), consola: [], excepciones: [], peticiones_fallidas: [], capturas: [] }
let ws
try {
  let destino
  for (let i = 0; i < 60 && !destino; i++) {
    try { destino = (await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json()).find((d) => d.type === 'page') } catch { /* arrancando */ }
    if (!destino) await dormir(250)
  }
  if (!destino) throw new Error('El navegador no arranca')
  ws = new WebSocket(destino.webSocketDebuggerUrl)
  await new Promise((ok, mal) => { ws.onopen = ok; ws.onerror = mal })
  let n = 0
  const pend = new Map()
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data)
    if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); return }
    if (d.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(d.params.type)) {
      informe.consola.push(`${d.params.type}: ` + d.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 300))
    }
    if (d.method === 'Runtime.exceptionThrown') informe.excepciones.push((d.params.exceptionDetails.exception?.description ?? d.params.exceptionDetails.text).slice(0, 400))
    if (d.method === 'Network.responseReceived' && d.params.response.status >= 400) {
      informe.peticiones_fallidas.push(`${d.params.response.status} ${d.params.response.url.replace(/token=[^&]+/, 'token=***').slice(0, 200)}`)
    }
  }
  const cdp = (method, params = {}) => new Promise((ok) => { const i = ++n; pend.set(i, ok); ws.send(JSON.stringify({ id: i, method, params })) })
  await cdp('Runtime.enable'); await cdp('Network.enable'); await cdp('Page.enable')
  await cdp('Emulation.setDeviceMetricsOverride', { width: ancho, height: alto, deviceScaleFactor: 1, mobile: movil })
  if (movil) await cdp('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 })
  const evaluar = async (expr) => (await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value
  const capturar = async (fichero) => {
    const r = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: flag('completa') })
    writeFileSync(fichero, Buffer.from(r.result.data, 'base64'))
    informe.capturas.push(fichero)
  }
  await cdp('Page.navigate', { url })
  await dormir(esperar)
  const base = new URL(url).origin
  for (const p of pasos) {
    if (p.esperar) await dormir(p.esperar)
    else if (p.clic) informe[`clic ${p.clic}`] = await evaluar(`(() => { const e = document.querySelector(${JSON.stringify(p.clic)}); if (!e) return 'no encontrado'; e.scrollIntoView({block:'center'}); e.click(); return 'ok' })()`)
    else if (p.clicTexto) informe[`clic «${p.clicTexto}»`] = await evaluar(`(() => { const t = ${JSON.stringify(p.clicTexto)}; const e = [...document.querySelectorAll('button, a, [role=button], [role=tab], label, .tarjeta')].find(x => x.innerText && x.innerText.trim().includes(t)); if (!e) return 'no encontrado'; e.scrollIntoView({block:'center'}); e.click(); return 'ok' })()`)
    else if (p.escribir) informe[`escribir ${p.escribir[0]}`] = await evaluar(`(() => { const e = document.querySelector(${JSON.stringify(p.escribir[0])}); if (!e) return 'no encontrado'; const set = Object.getOwnPropertyDescriptor(e.__proto__, 'value').set; set.call(e, ${JSON.stringify(p.escribir[1])}); e.dispatchEvent(new Event('input', {bubbles:true})); return 'ok' })()`)
    else if (p.tecla) { await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: p.tecla, code: p.tecla, windowsVirtualKeyCode: p.tecla === 'Enter' ? 13 : 0 }); await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: p.tecla, code: p.tecla }) }
    else if (p.ir) { await cdp('Page.navigate', { url: base + p.ir }); await dormir(esperar) }
    else if (p.eval) informe[`eval`] = await evaluar(p.eval)
    else if (p.captura) await capturar(p.captura)
    await dormir(p.pausa ?? 400)
  }
  if (salida) await capturar(salida)
  informe.titulo = await evaluar('document.title')
  informe.texto_visible = (await evaluar('document.body.innerText'))?.slice(0, 1500)
} catch (e) {
  informe.error = String(e)
} finally {
  try { ws?.close() } catch { /* nada */ }
  // Cerrar el navegador entero: Browser.close por CDP y, por si acaso, el árbol de procesos
  // (Edge lanza muchos procesos hijos que sobreviven a matar solo el primero).
  try {
    const v = await (await fetch(`http://127.0.0.1:${puerto}/json/version`)).json()
    const wb = new WebSocket(v.webSocketDebuggerUrl)
    await new Promise((ok) => { wb.onopen = ok; wb.onerror = ok; setTimeout(ok, 1500) })
    try { wb.send(JSON.stringify({ id: 1, method: 'Browser.close' })) } catch { /* ya cerrado */ }
    await dormir(800)
  } catch { /* ya cerrado */ }
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { stdio: 'ignore' })
  else proc.kill('SIGKILL')
  for (let i = 0; i < 10; i++) {
    try { rmSync(perfil, { recursive: true, force: true }); break } catch { await dormir(500) }
  }
}
console.log(JSON.stringify(informe, null, 2))
