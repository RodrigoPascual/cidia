// Host del plugin CidIA (proceso Node de la app de escritorio).
//
// Publica en el servidor web local de la app las rutas /cidia/*, que el renderer llama en el
// mismo origen (dsh-app://app), sin CORS:
//   /cidia/gw/*      proxy en streaming al gateway CidIA (API, interfaz web, subidas, descargas,
//                    SSE y rangos para vídeo). Añade x-forwarded-prefix para que el gateway sirva
//                    la interfaz con la base correcta y, si el renderer no envía Authorization,
//                    pone el token de la sesión del Host.
//   /cidia/sesion    estado de la sesión (GET), adopción del token con el que el usuario ha
//                    iniciado sesión en la interfaz (POST) y cierre de sesión (DELETE).
//   /cidia/estado    diagnóstico: servidor, conexión y herramientas MCP.
//   /cidia/idioma/*  diccionarios en castellano para la interfaz de la app.
//
// Con el token de la sesión (de usuario o de invitado) el Host:
//   1. fija la credencial CIDIA_GATEWAY_TOKEN, que el proveedor de modelos 'cidia' resuelve en
//      cada petición (no hace falta recargar nada);
//   2. reconecta el cliente MCP del gateway (/mcp) con la nueva cabecera Authorization: el
//      cliente MCP es un plugin hijo y se reinicia con fiber.update;
//   3. sin sesión de usuario, obtiene un token de invitado y lo renueva antes de que caduque.
// Además deniega a los agentes la única herramienta local que la app monta por código y que
// ningún patch puede quitar (load_workspace_dependencies, docs/investigacion/02 §3.1).

import http from 'node:http'
import https from 'node:https'
import { readFile } from 'node:fs/promises'
import { pipeline } from 'node:stream'
import z from '@deepseek-ai/schemastery'

export const name = 'cidia'
export const inject = ['webServer', 'connection', 'credentials']

export const Config = z.object({
  gatewayUrl: z.string().default('http://127.0.0.1:18700')
    .description('Dirección del servidor CidIA de la empresa. La escribe el instalador.'),
  mcp: z.boolean().default(true)
    .description('Conectar al agente las herramientas MCP del servidor CidIA.'),
  timeoutMs: z.number().default(15000)
    .description('Tiempo máximo de las llamadas internas al servidor (milisegundos).'),
})

const PREFIJO = '/cidia'
const PREFIJO_GW = '/cidia/gw'
/** Referencia de la credencial que usa la ruta de modelos 'cidia' (apiKeyEnv). */
export const REF_TOKEN = 'CIDIA_GATEWAY_TOKEN'
/** Cada cuánto se comprueba que la sesión sigue viva en el servidor. */
const VALIDAR_CADA_MS = 5 * 60_000
/** Margen con el que se renueva el token de invitado antes de que caduque. */
const MARGEN_RENOVACION_MS = 10 * 60_000
const MAX_CUERPO_SESION = 64 * 1024
/** Tope de las respuestas que el Host lee enteras (sesión, perfil, invitado): un servidor que
 *  respondiera sin fin no puede llenar la memoria del Host. */
const MAX_RESPUESTA_INTERNA = 1024 * 1024
/** Herramientas locales que el Host de escritorio registra por código (desktop-office) y que la
 *  capa home no puede desactivar: load_workspace_dependencies devuelve rutas del Python y el
 *  Node de la app y, la primera vez, copia unos 289 MB en DSH_HOME. CidIA no las usa. */
export const HERRAMIENTAS_DENEGADAS = new Set(['load_workspace_dependencies'])

// Cabeceras que no se reenvían al gateway: las de conexión, la cookie de la app (autentica al
// renderer ante el Host, nunca debe salir del equipo) y las que el proxy fija por su cuenta.
const QUITAR_PETICION = new Set([
  'host', 'cookie', 'origin', 'referer', 'connection', 'keep-alive', 'proxy-connection', 'transfer-encoding',
  'te', 'trailer', 'upgrade', 'proxy-authorization', 'accept-encoding', 'x-forwarded-prefix', 'x-forwarded-for',
  'x-forwarded-host', 'x-forwarded-proto', 'forwarded',
])
// Cabeceras de la respuesta que no vuelven al renderer: las de conexión y las que tocarían el
// estado del origen de la app (dsh-app://app), como su cookie de sesión con el Host.
const QUITAR_RESPUESTA = new Set([
  'connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'proxy-authenticate', 'set-cookie',
  'clear-site-data',
])

/** Cabeceras que la propia cabecera Connection declara de salto a salto (RFC 9110 §7.6.1):
 *  tampoco se reenvían. */
function deConexion(cabeceras) {
  return new Set(String(cabeceras.connection ?? '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean))
}

function enviarJson(res, estado, cuerpo) {
  if (res.headersSent) { res.end(); return }
  res.writeHead(estado, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(cuerpo))
}

async function leerJson(req) {
  const trozos = []
  let total = 0
  for await (const trozo of req) {
    total += trozo.length
    if (total > MAX_CUERPO_SESION) throw Object.assign(new Error('Petición demasiado grande.'), { estado: 413 })
    trozos.push(trozo)
  }
  const texto = Buffer.concat(trozos).toString('utf8')
  if (texto.trim() === '') return {}
  try { return JSON.parse(texto) } catch { throw Object.assign(new Error('El cuerpo no es JSON válido.'), { estado: 400 }) }
}

/** Normaliza la dirección del gateway: sin barra final y solo http(s). */
export function normalizarBase(url) {
  const texto = String(url ?? '').trim().replace(/\/+$/, '')
  try {
    const u = new URL(texto)
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null
    return texto
  } catch {
    return null
  }
}

export function apply(ctx, config) {
  const base = normalizarBase(config.gatewayUrl)
  const urlBase = base === null ? null : new URL(base + '/')
  const timeoutMs = Number(config.timeoutMs) > 0 ? Number(config.timeoutMs) : 15000
  const agenteHttp = new http.Agent({ keepAlive: true, maxSockets: 32 })
  const agenteHttps = new https.Agent({ keepAlive: true, maxSockets: 32 })
  const log = ctx.logger ?? console
  const aviso = (...args) => { try { log.warn(...args) } catch { /* sin logger */ } }
  const info = (...args) => { try { log.info(...args) } catch { /* sin logger */ } }

  let vivo = true
  /** Sesión del Host: la que usan el proveedor de modelos y el MCP. */
  let sesion = { modo: 'sin_conexion', token: null, perfil: null, expira: 0 }
  let conectado = false
  let ultimoError = null
  let temporizador = null
  let reintentos = 0
  // Operaciones de sesión en serie: el renderer, los temporizadores y el proxy no se pisan.
  let cola = Promise.resolve()
  const enCola = (op) => {
    const r = cola.then(op, op)
    cola = r.catch(() => undefined)
    return r
  }

  if (base === null) aviso('cidia: la dirección del servidor no es válida: %s', config.gatewayUrl)

  // ------------------------------------------------------------------ llamadas al gateway

  /** Petición HTTP sin proxy corporativo (el gateway está en la red de la empresa). La ruta
   *  siempre se resuelve dentro del gateway: «./» impide que una ruta como «http://otro» salga
   *  a otro servidor con el token de la sesión, y tampoco puede subir por encima de la ruta
   *  base del gateway (si se publica en una subcarpeta de otro servidor). */
  function abrir(ruta, opciones) {
    const destino = new URL('./' + ruta.replace(/^\/+/, ''), urlBase)
    if (destino.origin !== urlBase.origin || !destino.pathname.startsWith(urlBase.pathname)) {
      throw Object.assign(new Error('Ruta fuera del servidor CidIA.'), { estado: 400 })
    }
    const seguro = destino.protocol === 'https:'
    return (seguro ? https : http).request(destino, { ...opciones, agent: seguro ? agenteHttps : agenteHttp })
  }

  /** Llamada JSON corta al gateway. Devuelve { estado, datos }. */
  function llamar(metodo, ruta, { token, cuerpo } = {}) {
    return new Promise((resolver, rechazar) => {
      if (urlBase === null) { rechazar(new Error('La dirección del servidor CidIA no es válida.')); return }
      const datos = cuerpo === undefined ? null : Buffer.from(JSON.stringify(cuerpo))
      const cabeceras = { accept: 'application/json', 'x-cidia-cliente': 'app-escritorio' }
      if (token) cabeceras.authorization = `Bearer ${token}`
      if (datos) { cabeceras['content-type'] = 'application/json'; cabeceras['content-length'] = String(datos.length) }
      const peticion = abrir(ruta, { method: metodo, headers: cabeceras })
      peticion.setTimeout(timeoutMs, () => peticion.destroy(new Error('El servidor CidIA no responde.')))
      peticion.on('error', rechazar)
      peticion.on('response', (resp) => {
        const trozos = []
        let total = 0
        resp.on('data', (t) => {
          total += t.length
          if (total <= MAX_RESPUESTA_INTERNA) { trozos.push(t); return }
          rechazar(new Error('El servidor CidIA ha enviado una respuesta demasiado grande.'))
          resp.destroy()
        })
        resp.on('error', rechazar)
        resp.on('end', () => {
          const texto = Buffer.concat(trozos).toString('utf8')
          let json = null
          try { json = texto ? JSON.parse(texto) : null } catch { json = null }
          resolver({ estado: resp.statusCode ?? 0, datos: json })
        })
      })
      peticion.end(datos ?? undefined)
    })
  }

  // ------------------------------------------------------------------ credencial y MCP

  let credencialAplicada
  async function aplicarCredencial(token) {
    // Con el plugin ya descargado no se escribe: una sesión que llegue tarde no debe dejar su
    // token en disco después de que la limpieza lo haya retirado.
    if (!vivo || token === credencialAplicada) return
    try {
      if (token) await ctx.credentials.set(REF_TOKEN, token)
      else await ctx.credentials.unset(REF_TOKEN)
      credencialAplicada = token
    } catch (error) {
      aviso('cidia: no se pudo fijar la credencial %s: %s', REF_TOKEN, error?.message ?? error)
    }
  }

  let moduloMcp = null
  let fibraMcp = null
  let tokenMcp = null
  const urlMcp = () => process.env.CIDIA_MCP_URL || (base === null ? '' : base + '/mcp')

  /** Monta (o reinicia con la nueva cabecera) el cliente MCP del gateway como plugin hijo. */
  async function conectarMcp(token) {
    if (!config.mcp || !token || token === tokenMcp || urlMcp() === '') return
    tokenMcp = token
    try {
      moduloMcp ??= import('@deepseek-ai/dsh-mcp-client')
      const modulo = await moduloMcp
      if (!vivo || token !== tokenMcp) return
      const ajustes = {
        transport: 'streamable-http',
        serverName: 'cidia',
        url: urlMcp(),
        headers: { Authorization: `Bearer ${token}` },
        failOnStartupError: false,
      }
      if (fibraMcp === null) fibraMcp = ctx.plugin(modulo, ajustes)
      else fibraMcp.update(ajustes, true)
    } catch (error) {
      tokenMcp = null
      aviso('cidia: no se pudieron conectar las herramientas MCP: %s', error?.message ?? error)
    }
  }

  /** Quita del cliente MCP la identidad de la persona (cierre de sesión sin servidor): se queda
   *  sin cabecera hasta que llegue el siguiente token de invitado. */
  function soltarMcp() {
    if (fibraMcp === null || tokenMcp === null) return
    tokenMcp = null
    try {
      fibraMcp.update({ transport: 'streamable-http', serverName: 'cidia', url: urlMcp(), headers: {}, failOnStartupError: false }, true)
    } catch (error) {
      aviso('cidia: no se pudo reiniciar el cliente MCP: %s', error?.message ?? error)
    }
  }

  // ------------------------------------------------------------------ sesión del Host

  function programar(ms, tarea) {
    if (temporizador !== null) clearTimeout(temporizador)
    temporizador = vivo ? setTimeout(() => { temporizador = null; void enCola(tarea) }, Math.max(1000, ms)) : null
    temporizador?.unref?.()
  }

  /** Programa la siguiente comprobación según el estado de la sesión. */
  function programarSiguiente() {
    if (sesion.modo === 'sin_conexion') {
      reintentos += 1
      programar(Math.min(60_000, 5000 * 2 ** Math.min(reintentos - 1, 4)), invitado)
      return
    }
    reintentos = 0
    let espera = VALIDAR_CADA_MS
    if (sesion.modo === 'invitado' && sesion.expira > 0) {
      espera = Math.min(espera, sesion.expira - Date.now() - MARGEN_RENOVACION_MS)
    }
    programar(espera, validar)
  }

  async function fijar(nueva) {
    sesion = nueva
    await aplicarCredencial(nueva.token)
    void conectarMcp(nueva.token)
    programarSiguiente()
  }

  /** Token de una sesión cerrada en este equipo que el servidor aún no ha revocado (se cerró sin
   *  conexión): se revoca en cuanto vuelva el servidor y no se puede volver a adoptar. */
  let revocarPendiente = null

  /** Revoca un token de usuario en el servidor. true si ya no vale (revocado o caducado). */
  async function revocar(token) {
    try {
      const r = await llamar('POST', '/api/auth/salir', { token, cuerpo: {} })
      return (r.estado >= 200 && r.estado < 300) || r.estado === 401
    } catch {
      return false
    }
  }

  /** Obtiene un token de invitado nuevo (servicios básicos sin sesión). */
  async function invitado() {
    try {
      const r = await llamar('POST', '/api/auth/invitado', { cuerpo: {} })
      if (r.estado !== 200 || typeof r.datos?.token !== 'string') {
        throw new Error(r.datos?.detail ?? `El servidor CidIA respondió ${r.estado}.`)
      }
      conectado = true
      ultimoError = null
      if (revocarPendiente !== null && await revocar(revocarPendiente)) revocarPendiente = null
      const expira = Date.parse(r.datos.expira ?? '')
      await fijar({ modo: 'invitado', token: r.datos.token, perfil: r.datos.perfil ?? null, expira: Number.isFinite(expira) ? expira : 0 })
      info('cidia: sesión de invitado lista')
    } catch (error) {
      conectado = false
      ultimoError = String(error?.message ?? error)
      // Sin servidor se reintenta más tarde. Un token de invitado se conserva; uno de usuario no
      // (se acaba de cerrar su sesión): la credencial vuelve al token de arranque del .env.
      const conservar = sesion.modo === 'invitado' ? sesion.token : null
      if (sesion.modo === 'usuario') {
        await aplicarCredencial(null)
        soltarMcp()
      }
      sesion = { modo: 'sin_conexion', token: conservar, perfil: null, expira: 0 }
      programarSiguiente()
    }
    return estadoPublico()
  }

  /** Comprueba en el servidor que la sesión actual sigue siendo válida. */
  async function validar() {
    if (!sesion.token) return invitado()
    if (sesion.modo === 'invitado' && sesion.expira > 0 && sesion.expira - Date.now() <= MARGEN_RENOVACION_MS) {
      return invitado()
    }
    try {
      const r = await llamar('GET', '/api/auth/yo', { token: sesion.token })
      conectado = true
      if (r.estado === 401) return invitado()
      if (r.estado === 200 && r.datos) sesion = { ...sesion, perfil: r.datos }
    } catch (error) {
      conectado = false
      ultimoError = String(error?.message ?? error)
    }
    programarSiguiente()
    return estadoPublico()
  }

  /** Adopta el token con el que el usuario ha entrado en la interfaz (o uno de invitado). */
  async function adoptar(token) {
    if (typeof token !== 'string' || token.length < 8 || token.length > 8192) {
      throw Object.assign(new Error('Token de sesión no válido.'), { estado: 400 })
    }
    if (token === sesion.token && sesion.perfil) return estadoPublico()
    // Una sesión que se cerró aquí sin conexión no vuelve aunque algún marco aún tenga el token.
    if (token === revocarPendiente) {
      throw Object.assign(new Error('La sesión se cerró en este equipo. Vuelve a iniciar sesión.'), { estado: 401 })
    }
    let r
    try {
      r = await llamar('GET', '/api/auth/yo', { token })
    } catch (error) {
      conectado = false
      ultimoError = String(error?.message ?? error)
      throw Object.assign(new Error('No hay conexión con el servidor CidIA.'), { estado: 502 })
    }
    conectado = true
    if (r.estado === 401) throw Object.assign(new Error('La sesión ha caducado. Vuelve a iniciar sesión.'), { estado: 401 })
    if (r.estado !== 200 || !r.datos) {
      throw Object.assign(new Error(r.datos?.detail ?? `El servidor CidIA respondió ${r.estado}.`), { estado: 502 })
    }
    const perfil = r.datos
    await fijar({ modo: perfil.invitado ? 'invitado' : 'usuario', token, perfil, expira: 0 })
    return estadoPublico()
  }

  /** Cierra la sesión de usuario (la revoca en el servidor) y vuelve al modo invitado. Sin
   *  sesión de usuario solo comprueba que el token de invitado sigue valiendo. */
  async function salir() {
    if (sesion.modo === 'usuario' && sesion.token) {
      // Sin conexión no se puede revocar ya: queda pendiente para cuando vuelva el servidor.
      if (!await revocar(sesion.token)) revocarPendiente = sesion.token
      return invitado()
    }
    return sesion.modo === 'invitado' ? validar() : invitado()
  }

  /** Lo que ve el renderer. El token solo se entrega en modo invitado (la interfaz lo necesita
   *  para el copiloto sin sesión); el de usuario ya lo tiene la interfaz. */
  function estadoPublico() {
    return {
      modo: sesion.modo,
      perfil: sesion.perfil,
      token: sesion.modo === 'invitado' ? sesion.token : null,
      conectado,
      servidor: base,
      error: conectado ? null : ultimoError,
    }
  }

  // ------------------------------------------------------------------ proxy /cidia/gw

  /** Reescribe un Location del gateway para que siga pasando por el proxy. */
  function reescribirLocation(valor) {
    if (typeof valor !== 'string') return valor
    if (valor.startsWith('/') && !valor.startsWith('//')) return PREFIJO_GW + valor
    try {
      const u = new URL(valor)
      if (urlBase !== null && u.origin === urlBase.origin) return PREFIJO_GW + u.pathname + u.search + u.hash
    } catch { /* relativa: se queda igual */ }
    return valor
  }

  let validacionPendiente = false
  function proxy(req, res, ruta) {
    if (urlBase === null) {
      enviarJson(res, 503, { detail: 'La dirección del servidor CidIA no es válida. Revisa la instalación.' })
      return
    }
    const cabeceras = {}
    const saltoPeticion = deConexion(req.headers)
    for (const [clave, valor] of Object.entries(req.headers)) {
      if (QUITAR_PETICION.has(clave) || saltoPeticion.has(clave) || clave.startsWith('sec-fetch-')) continue
      cabeceras[clave] = valor
    }
    const tokenDelHost = !cabeceras.authorization && sesion.token
    if (tokenDelHost) cabeceras.authorization = `Bearer ${sesion.token}`
    cabeceras['x-forwarded-prefix'] = PREFIJO_GW
    cabeceras['accept-encoding'] = 'identity' // sin compresión: rangos y longitudes exactos
    cabeceras['x-cidia-cliente'] = 'app-escritorio'

    const salida = abrir(ruta, { method: req.method, headers: cabeceras })
    // Solo se limita el tiempo de conexión: las respuestas SSE y las subidas pueden durar mucho.
    salida.on('socket', (socket) => {
      if (socket.connecting === false) return
      socket.setTimeout(timeoutMs, () => salida.destroy(new Error('El servidor CidIA no responde.')))
      socket.once('connect', () => socket.setTimeout(0))
    })
    salida.on('response', (resp) => {
      const fuera = {}
      const saltoRespuesta = deConexion(resp.headers)
      for (const [clave, valor] of Object.entries(resp.headers)) {
        if (!QUITAR_RESPUESTA.has(clave) && !saltoRespuesta.has(clave)) fuera[clave] = valor
      }
      if (fuera.location !== undefined) fuera.location = reescribirLocation(fuera.location)
      res.writeHead(resp.statusCode ?? 502, fuera)
      // pipeline y no pipe: si el servidor corta a mitad de respuesta (reinicio, red), se corta
      // también la del renderer, que ve el error en lugar de esperar para siempre.
      pipeline(resp, res, () => undefined)
      // El token del Host ya no vale (caducado o revocado): se comprueba y se renueva.
      if (resp.statusCode === 401 && tokenDelHost && !validacionPendiente) {
        validacionPendiente = true
        void enCola(validar).finally(() => { validacionPendiente = false })
      }
    })
    salida.on('error', (error) => {
      conectado = false
      ultimoError = String(error?.message ?? error)
      if (!res.headersSent) enviarJson(res, 502, { detail: 'No hay conexión con el servidor CidIA.' })
      else res.destroy()
    })
    // Si el renderer cancela (cierra el panel o corta el streaming), se corta también arriba.
    res.on('close', () => { if (!res.writableFinished) salida.destroy() })
    req.on('aborted', () => salida.destroy())
    req.pipe(salida)
  }

  // ------------------------------------------------------------------ rutas /cidia

  const idioma = new Map()
  async function servirIdioma(res, codigo) {
    if (!/^[a-z]{2}(-[A-Za-z]{2})?$/.test(codigo)) { enviarJson(res, 404, { detail: 'Idioma no disponible.' }); return }
    try {
      if (!idioma.has(codigo)) {
        idioma.set(codigo, await readFile(new URL(`./idioma/${codigo}.json`, import.meta.url), 'utf8'))
      }
      res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-cache' })
      res.end(idioma.get(codigo))
    } catch {
      enviarJson(res, 404, { detail: 'Idioma no disponible.' })
    }
  }

  async function manejarSesion(req, res) {
    // GET espera a las operaciones en curso (p. ej. el token de invitado del arranque).
    if (req.method === 'GET') { enviarJson(res, 200, await enCola(estadoPublico)); return }
    if (req.method === 'DELETE') { enviarJson(res, 200, await enCola(salir)); return }
    if (req.method !== 'POST') { enviarJson(res, 405, { detail: 'Método no permitido.' }); return }
    const cuerpo = await leerJson(req)
    if (cuerpo === null || typeof cuerpo !== 'object' || Array.isArray(cuerpo)) {
      enviarJson(res, 400, { detail: 'El cuerpo debe ser un objeto JSON con el token de la sesión.' })
      return
    }
    const { token } = cuerpo
    // Sin token: la interfaz ha cerrado la sesión o ha caducado; el Host vuelve a invitado.
    if (token === null || token === undefined || token === '') { enviarJson(res, 200, await enCola(salir)); return }
    enviarJson(res, 200, await enCola(() => adoptar(token)))
  }

  async function manejador(req, res) {
    // Misma valla que /api de la app: Host de loopback, Origin y cookie del navegador de la app.
    const rechazo = ctx.connection.requestRejection(req)
    if (rechazo !== undefined) { res.writeHead(rechazo); res.end(); return }
    const url = new URL(req.url ?? '/', 'http://local')
    const sub = url.pathname.slice(PREFIJO.length)
    try {
      if (sub.startsWith('/gw/') || sub === '/gw') { proxy(req, res, (sub.slice(3) || '/') + url.search); return }
      if (sub === '/sesion') { await manejarSesion(req, res); return }
      if (sub === '/estado' && req.method === 'GET') {
        enviarJson(res, 200, { ...estadoPublico(), token: undefined, mcp: { activo: Boolean(config.mcp && fibraMcp), url: urlMcp() } })
        return
      }
      if (sub.startsWith('/idioma/') && req.method === 'GET') { await servirIdioma(res, sub.slice(8).replace(/\.json$/, '')); return }
      enviarJson(res, 404, { detail: 'Ruta de CidIA desconocida.' })
    } catch (error) {
      const estado = Number(error?.estado) || 502
      if (estado >= 500) aviso('cidia: %s', error?.message ?? error)
      if (!res.headersSent) enviarJson(res, estado, { detail: String(error?.message ?? 'Error interno de CidIA.') })
      else res.destroy()
    }
  }

  // Herramientas locales que ningún patch quita: un guard en un contexto sin ámbito de agente se
  // aplica a todos los agentes (siguen en el catálogo, pero su ejecución se deniega). El
  // servicio tools es opcional: sin él, el plugin funciona igual.
  if (typeof ctx.inject === 'function') {
    ctx.inject(['tools'], (c) => {
      c.tools.guard(e => (HERRAMIENTAS_DENEGADAS.has(e?.name) ? 'Esta herramienta no está disponible en CidIA.' : undefined))
    })
  }

  // ctx.webServer.register no se ata solo al ciclo de vida del plugin: se envuelve en ctx.effect.
  ctx.effect(() => ctx.webServer.register({ kind: 'prefix', path: PREFIJO, handler: manejador }), 'cidia: rutas /cidia')
  ctx.effect(() => () => {
    vivo = false
    if (temporizador !== null) clearTimeout(temporizador)
    agenteHttp.destroy()
    agenteHttps.destroy()
    // El token de la sesión no se queda en disco al cerrar la app (vuelve el de arranque del .env).
    if (credencialAplicada) {
      try { void Promise.resolve(ctx.credentials.unset(REF_TOKEN)).catch(() => undefined) } catch { /* servicio ya cerrado */ }
    }
  }, 'cidia: temporizadores, conexiones y credencial')

  // Primera sesión: invitado. Si la interfaz tiene una sesión guardada, la adoptará enseguida.
  void enCola(invitado)
}
