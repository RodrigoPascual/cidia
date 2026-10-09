// Cliente de la API del gateway CidIA.
//
// La interfaz se sirve de dos formas:
//  · directamente desde el gateway:            http://servidor:18700/app/...   → API en /api
//  · dentro de la app de escritorio (plugin):  dsh-app://app/cidia/gw/app/...  → API en /cidia/gw/api
// BASE es el prefijo que hay delante de /api en cada caso.

const CLAVE_TOKEN = 'cidia.token'

export const BASE = (() => {
  const ruta = window.location.pathname
  const i = ruta.indexOf('/app/')
  const corte = i >= 0 ? i : ruta.endsWith('/app') ? ruta.length - 4 : -1
  return corte > 0 ? ruta.slice(0, corte) : ''
})()

/** Prefijo de las rutas de la interfaz (para el enrutador). */
export const BASE_APP = `${BASE}/app`

/** ¿Va dentro de la app de escritorio? (o se pide con ?embed=1) */
export const EMBEBIDA =
  new URLSearchParams(window.location.search).get('embed') === '1' || window.location.pathname.startsWith('/cidia/')

/** Convierte una ruta del servidor (/api/ficheros/...) en una URL utilizable en <img>, <video> o <a>. */
export function urlServidor(ruta?: string | null): string | undefined {
  if (!ruta) return undefined
  if (/^(https?:|data:|blob:)/.test(ruta)) return ruta
  return BASE + ruta
}

export class ErrorApi extends Error {
  estado: number
  constructor(estado: number, mensaje: string) {
    super(mensaje)
    this.estado = estado
  }
}

let tokenEnMemoria: string | null = null

export function token(): string | null {
  if (tokenEnMemoria) return tokenEnMemoria
  try {
    tokenEnMemoria = localStorage.getItem(CLAVE_TOKEN)
  } catch {
    /* almacenamiento no disponible */
  }
  return tokenEnMemoria
}

export function guardarToken(t: string | null) {
  tokenEnMemoria = t
  try {
    if (t) localStorage.setItem(CLAVE_TOKEN, t)
    else localStorage.removeItem(CLAVE_TOKEN)
  } catch {
    /* almacenamiento no disponible */
  }
}

type Escuchador = () => void
const alCaducar: Escuchador[] = []
export function siSesionCaduca(f: Escuchador) {
  alCaducar.push(f)
}

function cabeceras(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra ?? {}) }
  const t = token()
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

async function leerError(r: Response): Promise<string> {
  try {
    const j = await r.json()
    if (typeof j.detail === 'string') return j.detail
    if (Array.isArray(j.detail)) return j.detail.map((d: { msg: string }) => d.msg).join('. ')
  } catch {
    /* sin cuerpo JSON */
  }
  if (r.status === 0 || r.status >= 500) return 'El servidor CidIA no responde. Inténtalo de nuevo en unos segundos.'
  return `Error ${r.status}`
}

export async function api<T = unknown>(
  ruta: string,
  opciones: { metodo?: string; cuerpo?: unknown; formulario?: FormData; senal?: AbortSignal } = {},
): Promise<T> {
  const { metodo = 'GET', cuerpo, formulario, senal } = opciones
  let r: Response
  try {
    r = await fetch(BASE + ruta, {
      method: metodo,
      headers: cabeceras(cuerpo !== undefined ? { 'Content-Type': 'application/json' } : undefined),
      body: formulario ?? (cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined),
      signal: senal,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ErrorApi(0, 'No hay conexión con el servidor CidIA.')
  }
  if (r.status === 401) {
    const msg = await leerError(r)
    if (token()) alCaducar.forEach((f) => f())
    throw new ErrorApi(401, msg)
  }
  if (!r.ok) throw new ErrorApi(r.status, await leerError(r))
  if (r.status === 204) return undefined as T
  const tipo = r.headers.get('content-type') ?? ''
  return (tipo.includes('application/json') ? await r.json() : await r.text()) as T
}

export const get = <T = unknown>(ruta: string, senal?: AbortSignal) => api<T>(ruta, { senal })
export const post = <T = unknown>(ruta: string, cuerpo?: unknown) => api<T>(ruta, { metodo: 'POST', cuerpo: cuerpo ?? {} })
export const put = <T = unknown>(ruta: string, cuerpo?: unknown) => api<T>(ruta, { metodo: 'PUT', cuerpo: cuerpo ?? {} })
export const patch = <T = unknown>(ruta: string, cuerpo?: unknown) => api<T>(ruta, { metodo: 'PATCH', cuerpo: cuerpo ?? {} })
export const del = <T = unknown>(ruta: string) => api<T>(ruta, { metodo: 'DELETE' })
export const enviarFormulario = <T = unknown>(ruta: string, formulario: FormData, metodo = 'POST') =>
  api<T>(ruta, { metodo, formulario })

/** Subida con progreso (XMLHttpRequest), para vídeos y ficheros grandes. */
export function subir<T = unknown>(ruta: string, formulario: FormData, alProgreso?: (pct: number) => void): Promise<T> {
  return new Promise((resolver, rechazar) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', BASE + ruta)
    const t = token()
    if (t) xhr.setRequestHeader('Authorization', `Bearer ${t}`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && alProgreso) alProgreso(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      let datos: unknown = xhr.responseText
      try {
        datos = JSON.parse(xhr.responseText)
      } catch {
        /* texto */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolver(datos as T)
      else {
        const d = datos as { detail?: string }
        if (xhr.status === 401) alCaducar.forEach((f) => f())
        rechazar(new ErrorApi(xhr.status, typeof d?.detail === 'string' ? d.detail : `Error ${xhr.status}`))
      }
    }
    xhr.onerror = () => rechazar(new ErrorApi(0, 'No hay conexión con el servidor CidIA.'))
    xhr.send(formulario)
  })
}

export interface EventoSSE {
  evento: string
  datos: any
}

/** POST que devuelve Server-Sent Events (respuestas del copiloto en streaming). */
export async function* flujo(ruta: string, cuerpo: unknown, senal?: AbortSignal): AsyncGenerator<EventoSSE> {
  let r: Response
  try {
    r = await fetch(BASE + ruta, {
      method: 'POST',
      headers: cabeceras({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
      body: JSON.stringify(cuerpo),
      signal: senal,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    throw new ErrorApi(0, 'No hay conexión con el servidor CidIA.')
  }
  if (r.status === 401) {
    alCaducar.forEach((f) => f())
    throw new ErrorApi(401, await leerError(r))
  }
  if (!r.ok || !r.body) throw new ErrorApi(r.status, await leerError(r))
  const lector = r.body.getReader()
  const decod = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await lector.read()
    if (done) break
    buffer += decod.decode(value, { stream: true })
    let corte: number
    while ((corte = buffer.indexOf('\n\n')) !== -1) {
      const bloque = buffer.slice(0, corte)
      buffer = buffer.slice(corte + 2)
      let evento = 'message'
      const lineas: string[] = []
      for (const l of bloque.split('\n')) {
        if (l.startsWith('event:')) evento = l.slice(6).trim()
        else if (l.startsWith('data:')) lineas.push(l.slice(5).replace(/^ /, ''))
      }
      if (!lineas.length) continue
      const texto = lineas.join('\n')
      let datos: unknown = texto
      try {
        datos = JSON.parse(texto)
      } catch {
        /* texto plano */
      }
      yield { evento, datos }
    }
  }
}

/** Formatea fechas ISO en castellano. */
export function fecha(iso?: string | null, conHora = false): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('es-ES', conHora
    ? { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { day: 'numeric', month: 'short', year: 'numeric' })
}

/** «hace 2 h», «hace 3 días»... */
export function hace(iso?: string | null): string {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'ahora mismo'
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`
  const dias = Math.floor(s / 86400)
  return dias === 1 ? 'hace 1 día' : `hace ${dias} días`
}

export function tamano(bytes?: number | null): string {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}
