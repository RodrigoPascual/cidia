// Utilidades compartidas por el modo planta y la formación: respuestas del copiloto en
// streaming, transcripción de voz y formato de tiempos.

import { enviarFormulario, flujo } from '../../api'

/** Fuente citada por el copiloto (formato de servicios/consulta.py, leído con tolerancia). */
export interface Fuente {
  n?: number
  titulo?: string
  fragmento?: string
  texto?: string
  documento_id?: number
  paso?: number | null
  codigo?: string | null
  version?: number | null
  pagina?: number | null
  autor?: string | null
  validador?: string | null
  url?: string | null
  /** false: el documento ya no existe o quien mira no puede abrirlo (el servidor lo vacía). */
  disponible?: boolean
  metadatos?: Record<string, unknown>
}

export interface Respuesta {
  texto: string
  fuentes: Fuente[]
  terminado: boolean
  error?: string
  conRespaldo?: boolean
  consultaId?: number | null
  /** La respuesta existe, pero quien mira no puede verla (material de otro departamento). */
  oculta?: boolean
  /** El servidor no aceptó la pregunta (error HTTP o sin conexión): no se ha contado. */
  rechazada?: boolean
}

export const RESPUESTA_VACIA: Respuesta = { texto: '', fuentes: [], terminado: false }

/**
 * Consume una respuesta SSE del copiloto (eventos fuentes, token, fin y error) y llama a
 * `alCambiar` con el estado acumulado tras cada evento. Nunca lanza: los fallos se devuelven en `error`.
 */
export async function consumirRespuesta(
  ruta: string,
  cuerpo: unknown,
  alCambiar: (r: Respuesta) => void,
  senal?: AbortSignal,
): Promise<Respuesta> {
  let r: Respuesta = { ...RESPUESTA_VACIA }
  let eventos = 0
  try {
    for await (const { evento, datos } of flujo(ruta, cuerpo, senal)) {
      eventos += 1
      const tipo = evento !== 'message' ? evento : datos?.tipo
      if (tipo === 'fuentes') {
        r = { ...r, fuentes: Array.isArray(datos) ? datos : datos?.fuentes ?? [] }
      } else if (tipo === 'token') {
        r = { ...r, texto: r.texto + (typeof datos === 'string' ? datos : datos?.texto ?? '') }
      } else if (tipo === 'fin') {
        r = { ...r, terminado: true, conRespaldo: datos?.con_respaldo, consultaId: datos?.consulta_id ?? null }
      } else if (tipo === 'error') {
        r = { ...r, terminado: true, error: typeof datos === 'string' ? datos : datos?.mensaje ?? 'El copiloto no ha podido responder.' }
      } else {
        continue
      }
      alCambiar(r)
    }
  } catch (e) {
    if ((e as Error)?.name !== 'AbortError') {
      r = { ...r, error: (e as Error)?.message ?? 'Sin conexión con el copiloto.', rechazada: eventos === 0 }
    }
  }
  r = { ...r, terminado: true }
  alCambiar(r)
  return r
}

/** Transcribe una nota de voz en el servidor. Devuelve el texto (vacío si no se ha entendido nada). */
export async function transcribir(audio: Blob): Promise<string> {
  const fd = new FormData()
  const ext = audio.type.includes('ogg') ? 'ogg' : audio.type.includes('mp4') ? 'm4a' : 'webm'
  fd.append('audio', audio, `pregunta.${ext}`)
  const r = await enviarFormulario<{ texto?: string; text?: string }>('/api/voz/transcribir', fd)
  return (r?.texto ?? r?.text ?? '').trim()
}

/** Texto corto de una fuente: «IT-023 v1 · paso 3» o su título. */
export function etiquetaFuente(f: Fuente): string {
  const m = (f.metadatos ?? {}) as Record<string, unknown>
  const paso = f.paso ?? (typeof m.paso === 'number' ? m.paso : undefined)
  const codigo = f.codigo ?? (typeof m.codigo === 'string' ? m.codigo : undefined)
  const version = f.version ?? (typeof m.version === 'number' ? m.version : undefined)
  const partes: string[] = []
  if (codigo) partes.push(version ? `${codigo} v${version}` : codigo)
  else if (f.titulo) partes.push(f.titulo)
  if (paso) partes.push(`paso ${paso}`)
  return partes.join(' · ') || 'Fuente'
}

/** 754 → «12:34» (y «1:02:03» a partir de una hora). */
export function reloj(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  const dos = (n: number) => String(n).padStart(2, '0')
  return h ? `${h}:${dos(m)}:${dos(r)}` : `${m}:${dos(r)}`
}

/** 754 → «12 min 34 s». */
export function duracion(segundos: number): string {
  const s = Math.max(0, Math.round(segundos))
  if (s < 60) return `${s} s`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h) return `${h} h ${m} min`
  const r = s % 60
  return r ? `${m} min ${r} s` : `${m} min`
}

let contador = 0
/** Identificador local para mensajes (crypto.randomUUID no existe fuera de contextos seguros). */
export function idLocal(): string {
  contador += 1
  return `m${Date.now().toString(36)}${contador}`
}
