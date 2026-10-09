// Verificación de una instalación de CidIA sin interfaz gráfica, por el protocolo CDP.
//
//   "%LOCALAPPDATA%\Programs\CidIA\CidIA.exe" --remote-debugging-port=9333
//   node app/instalador/verificar.mjs [--puerto 9333] [--captura captura.png]
//
// Comprueba: destino dsh-app://app/, título y marca CidIA, secciones de CidIA en la barra
// lateral, proxy al servidor (cidia/gw/salud), sesión del Host (cidia/estado) e interfaz web
// embebida en el iframe con la base del proxy. Node 22 (WebSocket nativo), sin dependencias.
import { writeFileSync } from 'node:fs'

const args = process.argv.slice(2)
const opcion = (nombre, porDefecto) => {
  const i = args.indexOf(nombre)
  return i >= 0 ? args[i + 1] : porDefecto
}
const puerto = opcion('--puerto', '9333')
const captura = opcion('--captura', null)

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
  return {
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

if (captura) {
  const r = await enviar('Page.captureScreenshot', { format: 'png' })
  writeFileSync(captura, Buffer.from(r.result.data, 'base64'))
  console.log(`Captura guardada en ${captura}`)
}
ws.close()
console.log(fallos === 0 ? '\nCidIA verificada.' : `\n${fallos} comprobación(es) fallida(s).`)
process.exit(fallos === 0 ? 0 : 1)
