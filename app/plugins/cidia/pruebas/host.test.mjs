// Pruebas del Host del plugin (index.js) con un ctx simulado con la forma de la app 0.2.0-rc.2:
// ctx.webServer.register por prefijo, ctx.connection.requestRejection, ctx.credentials,
// ctx.plugin (cliente MCP hijo) y ctx.effect. Un gateway falso en node:http hace de servidor
// CidIA. No necesita la app instalada ni red.
//
//   node --test app/plugins/cidia/pruebas/

import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import { cp, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const PLUGIN = join(dirname(fileURLToPath(import.meta.url)), '..')
const COOKIE = 'dsh-host=ok'

// ------------------------------------------------------------------ gateway falso
const gw = {
  tokens: new Map(), // token -> perfil
  revocados: [],
  vistas: [], // peticiones recibidas (método, url, cabeceras)
  cerradas: 0,
  invitados: 0,
  servidor: null,
  url: '',
}
function perfilInvitado() {
  return { invitado: true, nombre: 'Invitado', iniciales: 'IN', rol: 'invitado', servicios: ['chat'] }
}
gw.tokens.set('usr-ana-12345', {
  invitado: false, id: 7, usuario: 'ana', nombre: 'Ana Martín', iniciales: 'AM', rol: 'empleado',
  servicios: ['chat', 'perfil', 'planta', 'formacion'],
})

function json(res, estado, cuerpo, extra = {}) {
  res.writeHead(estado, { 'content-type': 'application/json', ...extra })
  res.end(JSON.stringify(cuerpo))
}
function tokenDe(req) {
  const a = req.headers.authorization ?? ''
  return a.startsWith('Bearer ') ? a.slice(7) : null
}

async function arrancarGateway() {
  gw.servidor = http.createServer(async (req, res) => {
    gw.vistas.push({ metodo: req.method, url: req.url, cabeceras: { ...req.headers } })
    const url = new URL(req.url, 'http://gw')
    const trozos = []
    for await (const t of req) trozos.push(t)
    const cuerpo = Buffer.concat(trozos)
    if (url.pathname === '/api/auth/invitado' && req.method === 'POST') {
      gw.invitados += 1
      const token = `inv-${gw.invitados}`
      gw.tokens.set(token, perfilInvitado())
      json(res, 200, { token, expira: new Date(Date.now() + 4 * 3600_000).toISOString(), perfil: perfilInvitado() })
      return
    }
    if (url.pathname === '/api/auth/yo') {
      if (tokenDe(req) === 'usr-enorme-123') {
        // Un servidor que responde sin fin: el Host no debe guardarlo todo en memoria.
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(`{"relleno":"${'x'.repeat(2 * 1024 * 1024)}"}`)
        return
      }
      const p = gw.tokens.get(tokenDe(req))
      if (!p) { json(res, 401, { detail: 'Sesión no válida.' }); return }
      json(res, 200, p)
      return
    }
    if (url.pathname === '/api/auth/salir' && req.method === 'POST') {
      const t = tokenDe(req)
      gw.revocados.push(t)
      gw.tokens.delete(t)
      json(res, 200, { ok: true })
      return
    }
    if (url.pathname === '/api/protegida') {
      if (!gw.tokens.has(tokenDe(req))) { json(res, 401, { detail: 'Sesión no válida.' }); return }
      json(res, 200, { ok: true })
      return
    }
    if (url.pathname === '/api/eco') {
      json(res, 200, {
        metodo: req.method, ruta: req.url, cuerpo: cuerpo.toString('utf8'),
        authorization: req.headers.authorization ?? null, cookie: req.headers.cookie ?? null,
        prefijo: req.headers['x-forwarded-prefix'] ?? null, origin: req.headers.origin ?? null,
        pista: req.headers['x-pista'] ?? null,
      })
      return
    }
    if (url.pathname === '/api/salto') {
      // Cabecera de salto a salto declarada en Connection: no debe llegar al renderer.
      res.writeHead(200, { 'content-type': 'text/plain', connection: 'keep-alive, x-salto-interno', 'x-salto-interno': '1' })
      res.end('ok')
      return
    }
    if (url.pathname === '/api/sse') {
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
      res.write('event: token\ndata: {"texto":"Hola"}\n\n')
      setTimeout(() => { res.end('event: fin\ndata: {}\n\n') }, 400)
      return
    }
    if (url.pathname === '/api/video') {
      const total = 1000
      const m = /bytes=(\d+)-(\d+)?/.exec(req.headers.range ?? '')
      if (!m) { res.writeHead(200, { 'content-type': 'video/mp4', 'accept-ranges': 'bytes', 'content-length': total }); res.end(Buffer.alloc(total)); return }
      const ini = Number(m[1]); const fin = m[2] ? Number(m[2]) : total - 1
      res.writeHead(206, { 'content-type': 'video/mp4', 'accept-ranges': 'bytes', 'content-range': `bytes ${ini}-${fin}/${total}`, 'content-length': fin - ini + 1 })
      res.end(Buffer.alloc(fin - ini + 1))
      return
    }
    if (url.pathname === '/api/origen') {
      // Cabeceras que tocarían el estado del origen de la app (su cookie con el Host, su almacén).
      json(res, 200, { ok: true }, { 'set-cookie': 'dsh-host=robada; Path=/', 'clear-site-data': '"cookies", "storage"' })
      return
    }
    if (url.pathname === '/redir') { res.writeHead(307, { location: '/app/' }); res.end(); return }
    if (url.pathname === '/redir-abs') { res.writeHead(307, { location: `${gw.url}/api/eco?x=2` }); res.end(); return }
    if (url.pathname.startsWith('/app')) {
      const prefijo = req.headers['x-forwarded-prefix'] ?? ''
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
      res.end(`<!doctype html><html><head><base href="${prefijo}/app/" /></head><body>CidIA</body></html>`)
      return
    }
    if (url.pathname === '/api/lento') {
      req.socket.on('close', () => { gw.cerradas += 1 })
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      res.write(': esperando\n\n')
      return // nunca termina: el proxy debe cortar cuando el renderer cancele
    }
    if (url.pathname === '/api/corte') {
      // El servidor se cae a mitad de la respuesta (reinicio, red): corta la conexión.
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      res.write('event: token\ndata: {"texto":"Ho"}\n\n')
      setTimeout(() => req.socket.destroy(), 100)
      return
    }
    json(res, 404, { detail: 'No existe.' })
  })
  await new Promise(r => gw.servidor.listen(0, '127.0.0.1', r))
  gw.url = `http://127.0.0.1:${gw.servidor.address().port}`
}

// ------------------------------------------------------------------ app simulada
const rutas = [] // { kind, path, handler, quitada }
const credenciales = { valores: new Map(), escrituras: [] }
const mcp = { montajes: [], actualizaciones: [] }
const guardias = [] // tools.guard registrados por el plugin
const efectos = []
let hostApp = null
let urlApp = ''
let tmp = ''

const ctx = {
  logger: { warn() {}, info() {} },
  effect(fn) { const d = fn(); efectos.push(d); return d },
  webServer: {
    register(ruta) { const r = { ...ruta, quitada: false }; rutas.push(r); return () => { r.quitada = true } },
  },
  connection: {
    requestRejection(req) { return (req.headers.cookie ?? '').includes(COOKIE) ? undefined : 401 },
  },
  credentials: {
    async set(ref, valor) { credenciales.valores.set(ref, valor); credenciales.escrituras.push(['set', ref, valor]) },
    async unset(ref) { credenciales.valores.delete(ref); credenciales.escrituras.push(['unset', ref]) },
  },
  plugin(modulo, ajustes) {
    mcp.montajes.push({ modulo, ajustes })
    return { update(nuevos, noSave) { mcp.actualizaciones.push({ ajustes: nuevos, noSave }) } }
  },
  // Servicios opcionales (cordis ctx.inject): aquí solo 'tools', con guard como en la 0.2.0-rc.2.
  inject(servicios, callback) {
    if (!servicios.every(s => s === 'tools')) return () => {}
    callback({ tools: { guard(fn) { guardias.push(fn); return () => { guardias.splice(guardias.indexOf(fn), 1) } } } })
    return () => {}
  },
}

/** Servidor web local de la app: enruta por prefijo como dsh-host-webserver. */
async function arrancarApp() {
  hostApp = http.createServer((req, res) => {
    const ruta = rutas.find(r => !r.quitada && (req.url === r.path || req.url.startsWith(r.path + '/')))
    if (!ruta) { res.writeHead(404); res.end(); return }
    Promise.resolve(ruta.handler(req, res)).catch((e) => { res.destroy(e) })
  })
  await new Promise(r => hostApp.listen(0, '127.0.0.1', r))
  urlApp = `http://127.0.0.1:${hostApp.address().port}`
}

const pedir = (ruta, init = {}) => fetch(urlApp + ruta, {
  ...init, headers: { cookie: COOKIE, ...(init.headers ?? {}) },
})

async function esperarA(condicion, ms = 3000) {
  const fin = Date.now() + ms
  while (Date.now() < fin) {
    if (await condicion()) return
    await new Promise(r => setTimeout(r, 20))
  }
  throw new Error('tiempo agotado esperando la condición')
}

before(async () => {
  await arrancarGateway()
  await arrancarApp()
  // Copia del plugin con dependencias simuladas (schemastery y el cliente MCP de la app).
  tmp = await mkdtemp(join(tmpdir(), 'cidia-host-'))
  const destino = join(tmp, 'cidia')
  await mkdir(destino, { recursive: true })
  await cp(join(PLUGIN, 'index.js'), join(destino, 'index.js'))
  await cp(join(PLUGIN, 'package.json'), join(destino, 'package.json'))
  await cp(join(PLUGIN, 'idioma'), join(destino, 'idioma'), { recursive: true })
  const nm = join(destino, 'node_modules', '@deepseek-ai')
  await mkdir(join(nm, 'schemastery'), { recursive: true })
  await writeFile(join(nm, 'schemastery', 'package.json'), '{"name":"@deepseek-ai/schemastery","type":"module","main":"index.js"}')
  await writeFile(join(nm, 'schemastery', 'index.js'), `
    const nodo = () => { const n = { default: () => n, description: () => n, required: () => n, min: () => n, max: () => n }; return n }
    export default { object: () => nodo(), string: nodo, boolean: nodo, number: nodo, natural: nodo }`)
  await mkdir(join(nm, 'dsh-mcp-client'), { recursive: true })
  await writeFile(join(nm, 'dsh-mcp-client', 'package.json'), '{"name":"@deepseek-ai/dsh-mcp-client","type":"module","main":"index.js"}')
  await writeFile(join(nm, 'dsh-mcp-client', 'index.js'), "export const name = 'mcp-client'\nexport const inject = ['tools']\nexport function apply() {}")
  const modulo = await import(pathToFileURL(join(destino, 'index.js')).href)
  assert.equal(modulo.name, 'cidia')
  assert.deepEqual(modulo.inject, ['webServer', 'connection', 'credentials'])
  // Cordis construye con new las funciones con prototype.
  // eslint-disable-next-line new-cap
  new modulo.apply(ctx, { gatewayUrl: gw.url + '/', mcp: true, timeoutMs: 3000 })
})

after(async () => {
  for (const d of efectos) if (typeof d === 'function') d()
  await new Promise(r => hostApp.close(r))
  if (gw.servidor.listening) await new Promise(r => gw.servidor.close(r))
  await rm(tmp, { recursive: true, force: true })
})

// ------------------------------------------------------------------ casos
test('registra la ruta /cidia por prefijo y rechaza peticiones sin la cookie de la app', async () => {
  assert.equal(rutas.length, 1)
  assert.equal(rutas[0].kind, 'prefix')
  assert.equal(rutas[0].path, '/cidia')
  const r = await fetch(urlApp + '/cidia/sesion')
  assert.equal(r.status, 401)
  const p = await fetch(urlApp + '/cidia/gw/api/eco')
  assert.equal(p.status, 401)
})

test('deniega a todos los agentes la herramienta local load_workspace_dependencies', () => {
  assert.equal(guardias.length, 1)
  const [guardia] = guardias
  assert.match(guardia({ name: 'load_workspace_dependencies', input: {} }), /no está disponible en CidIA/)
  assert.equal(guardia({ name: 'mcp__cidia__buscar_conocimiento', input: {} }), undefined)
  assert.equal(guardia({ name: 'ask_user', input: {} }), undefined)
})

test('al arrancar obtiene un token de invitado, fija la credencial y monta el MCP', async () => {
  const r = await pedir('/cidia/sesion')
  assert.equal(r.status, 200)
  const s = await r.json()
  assert.equal(s.modo, 'invitado')
  assert.equal(s.token, 'inv-1')
  assert.equal(s.conectado, true)
  assert.equal(s.perfil.invitado, true)
  assert.equal(credenciales.valores.get('CIDIA_GATEWAY_TOKEN'), 'inv-1')
  await esperarA(() => mcp.montajes.length === 1)
  const { ajustes } = mcp.montajes[0]
  assert.equal(ajustes.transport, 'streamable-http')
  assert.equal(ajustes.serverName, 'cidia')
  assert.equal(ajustes.url, gw.url + '/mcp')
  assert.equal(ajustes.headers.Authorization, 'Bearer inv-1')
  assert.equal(ajustes.failOnStartupError, false)
})

test('el proxy pone el token del Host, quita la cookie y añade x-forwarded-prefix', async () => {
  const r = await pedir('/cidia/gw/api/eco?x=1&y=dos', { headers: { origin: 'dsh-app://app' } })
  assert.equal(r.status, 200)
  const eco = await r.json()
  assert.equal(eco.ruta, '/api/eco?x=1&y=dos')
  assert.equal(eco.authorization, 'Bearer inv-1')
  assert.equal(eco.cookie, null, 'la cookie de la app no sale del equipo')
  assert.equal(eco.origin, null)
  assert.equal(eco.prefijo, '/cidia/gw')
  const origen = await pedir('/cidia/gw/api/origen')
  assert.equal(origen.status, 200)
  assert.equal(origen.headers.get('set-cookie'), null, 'el servidor no toca la cookie de la app')
  assert.equal(origen.headers.get('clear-site-data'), null, 'ni borra el almacén del origen de la app')
})

test('el proxy no reenvía las cabeceras que Connection declara de salto a salto', async () => {
  // fetch no deja fijar Connection: petición directa con node:http.
  const eco = await new Promise((resolver, rechazar) => {
    const p = http.request(urlApp + '/cidia/gw/api/eco', {
      headers: { cookie: COOKIE, connection: 'keep-alive, x-pista', 'x-pista': 'solo-hasta-el-host' },
    }, (r) => {
      const trozos = []
      r.on('data', t => trozos.push(t)).on('end', () => resolver(JSON.parse(Buffer.concat(trozos).toString('utf8'))))
    })
    p.on('error', rechazar)
    p.end()
  })
  assert.equal(eco.pista, null, 'la cabecera de salto a salto no llega al servidor')
  const r = await pedir('/cidia/gw/api/salto')
  assert.equal(await r.text(), 'ok')
  assert.equal(r.headers.get('x-salto-interno'), null, 'ni vuelve al renderer')
})

test('el proxy nunca sale del servidor CidIA aunque la ruta parezca una URL', async () => {
  const otro = http.createServer((_req, res) => { res.writeHead(200); res.end('otro servidor') })
  await new Promise(r => otro.listen(0, '127.0.0.1', r))
  let llamadasOtro = 0
  otro.on('request', () => { llamadasOtro += 1 })
  const r = await pedir(`/cidia/gw/http://127.0.0.1:${otro.address().port}/robar`)
  await r.arrayBuffer()
  await new Promise(res => otro.close(res))
  assert.equal(llamadasOtro, 0, 'ninguna petición al otro servidor')
  assert.match(gw.vistas.at(-1).url, /^\/http:/)
})

test('el proxy respeta la cabecera Authorization que envía la interfaz y reenvía el cuerpo', async () => {
  const r = await pedir('/cidia/gw/api/eco', {
    method: 'POST', body: JSON.stringify({ texto: 'hola' }),
    headers: { authorization: 'Bearer de-la-interfaz', 'content-type': 'application/json' },
  })
  const eco = await r.json()
  assert.equal(eco.metodo, 'POST')
  assert.equal(eco.authorization, 'Bearer de-la-interfaz')
  assert.deepEqual(JSON.parse(eco.cuerpo), { texto: 'hola' })
})

test('la interfaz se sirve con la base del proxy y las redirecciones siguen dentro de /cidia/gw', async () => {
  const html = await (await pedir('/cidia/gw/app/copiloto?embed=1')).text()
  assert.match(html, /<base href="\/cidia\/gw\/app\/"/)
  const r = await pedir('/cidia/gw/redir', { redirect: 'manual' })
  assert.equal(r.status, 307)
  assert.equal(r.headers.get('location'), '/cidia/gw/app/')
  const a = await pedir('/cidia/gw/redir-abs', { redirect: 'manual' })
  assert.equal(a.headers.get('location'), '/cidia/gw/api/eco?x=2')
})

test('SSE en streaming: el primer evento llega antes de que termine la respuesta', async () => {
  const inicio = Date.now()
  const r = await pedir('/cidia/gw/api/sse')
  assert.equal(r.headers.get('content-type'), 'text/event-stream')
  const lector = r.body.getReader()
  const { value } = await lector.read()
  assert.match(Buffer.from(value).toString(), /event: token/)
  assert.ok(Date.now() - inicio < 350, 'el primer evento no espera al final')
  let resto = ''
  for (;;) { const t = await lector.read(); if (t.done) break; resto += Buffer.from(t.value).toString() }
  assert.match(resto, /event: fin/)
})

test('rangos para vídeo: 206 con content-range', async () => {
  const r = await pedir('/cidia/gw/api/video', { headers: { range: 'bytes=100-199' } })
  assert.equal(r.status, 206)
  assert.equal(r.headers.get('content-range'), 'bytes 100-199/1000')
  assert.equal(r.headers.get('accept-ranges'), 'bytes')
  assert.equal((await r.arrayBuffer()).byteLength, 100)
})

test('si el renderer cancela, se corta también la petición al gateway', async () => {
  const antes = gw.cerradas
  const corte = new AbortController()
  const r = await pedir('/cidia/gw/api/lento', { signal: corte.signal })
  assert.equal(r.status, 200)
  corte.abort()
  await esperarA(() => gw.cerradas > antes)
})

test('si el servidor corta a mitad de respuesta, el renderer recibe el corte en lugar de esperar siempre', async () => {
  const r = await pedir('/cidia/gw/api/corte')
  assert.equal(r.status, 200)
  const lector = r.body.getReader()
  const { value } = await lector.read()
  assert.match(Buffer.from(value).toString(), /event: token/)
  const resto = (async () => { for (;;) { const t = await lector.read(); if (t.done) return 'terminada' } })()
  let reloj
  const espera = new Promise(res => { reloj = setTimeout(() => res('colgada'), 2000) })
  const resultado = await Promise.race([resto.catch(() => 'cortada'), espera])
  clearTimeout(reloj)
  if (resultado === 'colgada') await lector.cancel().catch(() => undefined)
  assert.equal(resultado, 'cortada', 'la respuesta incompleta no debe quedarse abierta ni parecer completa')
})

test('adopta la sesión de usuario de la interfaz: credencial y MCP con su token, sin devolverlo', async () => {
  const r = await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'usr-ana-12345' }) })
  assert.equal(r.status, 200)
  const s = await r.json()
  assert.equal(s.modo, 'usuario')
  assert.equal(s.token, null, 'el token de usuario no vuelve al renderer')
  assert.equal(s.perfil.usuario, 'ana')
  assert.equal(credenciales.valores.get('CIDIA_GATEWAY_TOKEN'), 'usr-ana-12345')
  await esperarA(() => mcp.actualizaciones.length === 1)
  assert.equal(mcp.actualizaciones[0].ajustes.headers.Authorization, 'Bearer usr-ana-12345')
  assert.equal(mcp.actualizaciones[0].noSave, true)
  const eco = await (await pedir('/cidia/gw/api/eco')).json()
  assert.equal(eco.authorization, 'Bearer usr-ana-12345')
})

test('un token caducado o inventado se rechaza con un mensaje claro', async () => {
  const r = await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'token-que-no-existe' }) })
  assert.equal(r.status, 401)
  assert.match((await r.json()).detail, /sesión ha caducado/)
  const mal = await pedir('/cidia/sesion', { method: 'POST', body: '{no es json' })
  assert.equal(mal.status, 400)
  const corto = await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'x' }) })
  assert.equal(corto.status, 400)
  // JSON válido que no es un objeto: 400 con un mensaje claro, no un error interno.
  for (const cuerpo of ['null', '[1]', '"usr-ana-12345"', '7']) {
    const r2 = await pedir('/cidia/sesion', { method: 'POST', body: cuerpo })
    assert.equal(r2.status, 400, cuerpo)
    assert.match((await r2.json()).detail, /objeto JSON/)
  }
  // Una respuesta desmesurada del servidor se corta: no se adopta nada y no cae el Host.
  const enorme = await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'usr-enorme-123' }) })
  assert.equal(enorme.status, 502)
  // La sesión buena sigue intacta.
  const s = await (await pedir('/cidia/sesion')).json()
  assert.equal(s.modo, 'usuario')
})

test('cerrar sesión revoca el token en el servidor y vuelve a invitado', async () => {
  const r = await pedir('/cidia/sesion', { method: 'DELETE' })
  const s = await r.json()
  assert.ok(gw.revocados.includes('usr-ana-12345'))
  assert.equal(s.modo, 'invitado')
  assert.match(s.token, /^inv-/)
  assert.equal(credenciales.valores.get('CIDIA_GATEWAY_TOKEN'), s.token)
  gw.tokens.set('usr-ana-12345', { invitado: false, id: 7, usuario: 'ana', nombre: 'Ana Martín', rol: 'empleado', servicios: ['chat'] })
})

test('la interfaz avisa de que no hay sesión (token null): el Host sigue en invitado', async () => {
  const antes = gw.invitados
  const r = await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: null }) })
  const s = await r.json()
  assert.equal(s.modo, 'invitado')
  assert.equal(gw.invitados, antes, 'un invitado válido no se renueva sin motivo')
})

test('si el token de invitado del Host deja de valer, se renueva solo', async () => {
  const actual = (await (await pedir('/cidia/sesion')).json()).token
  gw.tokens.delete(actual) // el servidor lo da por caducado
  const r = await pedir('/cidia/gw/api/protegida')
  assert.equal(r.status, 401)
  await esperarA(async () => {
    const s = await (await pedir('/cidia/sesion')).json()
    return s.token !== actual && s.modo === 'invitado'
  })
  const nuevo = (await (await pedir('/cidia/sesion')).json()).token
  assert.equal(credenciales.valores.get('CIDIA_GATEWAY_TOKEN'), nuevo)
  assert.equal((await pedir('/cidia/gw/api/protegida')).status, 200)
})

test('diccionario en castellano, estado y rutas desconocidas', async () => {
  const es = await (await pedir('/cidia/idioma/es.json')).json()
  assert.equal(es.common.cancel, 'Cancelar')
  assert.equal((await pedir('/cidia/idioma/../../index.js')).status, 404)
  const estado = await (await pedir('/cidia/estado')).json()
  assert.equal(estado.servidor, gw.url)
  assert.equal(estado.mcp.url, gw.url + '/mcp')
  assert.equal(estado.token, undefined)
  assert.equal((await pedir('/cidia/otra')).status, 404)
  assert.equal((await pedir('/cidia/sesion', { method: 'PUT' })).status, 405)
})

test('cerrar sesión sin servidor: la identidad sale del modelo y del MCP y se revoca al volver', async () => {
  const s = await (await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'usr-ana-12345' }) })).json()
  assert.equal(s.modo, 'usuario')
  await esperarA(() => mcp.actualizaciones.at(-1)?.ajustes.headers.Authorization === 'Bearer usr-ana-12345')
  const puerto = gw.servidor.address().port
  await new Promise(r => { gw.servidor.close(r); gw.servidor.closeAllConnections?.() })

  const fuera = await (await pedir('/cidia/sesion', { method: 'DELETE' })).json()
  assert.equal(fuera.modo, 'sin_conexion')
  assert.equal(credenciales.valores.has('CIDIA_GATEWAY_TOKEN'), false, 'vuelve el token de arranque del .env')
  assert.deepEqual(mcp.actualizaciones.at(-1).ajustes.headers, {}, 'el MCP ya no habla en nombre de la persona')
  const otraVez = await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'usr-ana-12345' }) })
  assert.equal(otraVez.status, 401, 'la sesión cerrada en el equipo no se puede volver a adoptar')
  assert.equal(gw.revocados.filter(t => t === 'usr-ana-12345').length, 1, 'aún no se ha podido revocar')

  // Vuelve el servidor: en el siguiente intento se revoca y se pasa a invitado.
  await new Promise(r => gw.servidor.listen(puerto, '127.0.0.1', r))
  const vuelta = await (await pedir('/cidia/sesion', { method: 'DELETE' })).json()
  assert.equal(vuelta.modo, 'invitado')
  assert.equal(gw.revocados.filter(t => t === 'usr-ana-12345').length, 2)
  assert.equal(gw.tokens.has('usr-ana-12345'), false)
  assert.equal(credenciales.valores.get('CIDIA_GATEWAY_TOKEN'), vuelta.token)
  await esperarA(() => mcp.actualizaciones.at(-1)?.ajustes.headers.Authorization === `Bearer ${vuelta.token}`)
  gw.tokens.set('usr-ana-12345', { invitado: false, id: 7, usuario: 'ana', nombre: 'Ana Martín', rol: 'empleado', servicios: ['chat'] })
})

test('con el servidor caído el proxy responde 502 con un mensaje en castellano', async () => {
  await new Promise(r => gw.servidor.close(r))
  gw.servidor.closeAllConnections?.()
  const r = await pedir('/cidia/gw/api/eco')
  assert.equal(r.status, 502)
  assert.equal((await r.json()).detail, 'No hay conexión con el servidor CidIA.')
  const s = await (await pedir('/cidia/sesion', { method: 'POST', body: JSON.stringify({ token: 'usr-ana-12345' }) }))
  assert.equal(s.status, 502)
})

test('al descargar el plugin se retira la ruta y se borra la credencial de sesión', async () => {
  for (const d of efectos.splice(0)) if (typeof d === 'function') d()
  assert.equal(rutas[0].quitada, true)
  await esperarA(() => credenciales.escrituras.at(-1)?.[0] === 'unset')
  assert.equal(credenciales.valores.has('CIDIA_GATEWAY_TOKEN'), false)
  assert.equal((await pedir('/cidia/sesion')).status, 404)
})
