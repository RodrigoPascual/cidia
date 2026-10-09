// Tipos de las respuestas de /api/aportaciones y /api/lagunas, y pequeñas utilidades.

export type EstadoAportacion = 'procesando' | 'pendiente' | 'validada' | 'rechazada'
export type EstadoLaguna = 'abierta' | 'resuelta' | 'descartada'

export interface TareaRef {
  id: number
  codigo: string | null
  nombre: string
}

export interface Aportacion {
  id: number
  estado: EstadoAportacion
  creada: string
  validada_en: string | null
  titulo: string | null
  problema: string | null
  causa: string | null
  solucion: string | null
  etiquetas: string[]
  via: 'voz' | 'texto'
  texto_original: string | null
  transcripcion: string | null
  audio_url: string | null
  duracion_audio: number | null
  tarea: TareaRef | null
  laguna: { id: number; pregunta: string; frecuencia: number; estado: EstadoLaguna } | null
  motivo_rechazo: string | null
  revisada_por: string | null
  documento: { id: number; titulo: string; estado: string; tipo: string; contenido: string | null } | null
  es_mia: boolean
  // Solo para quien gestiona (jefe de su departamento o administración)
  autor?: { id: number; nombre: string; puesto: string | null; nivel: string | null } | null
  departamento?: { id: number; nombre: string | null } | null
  nivel_minimo?: number
  nivel_nombre?: string | null
}

export interface RespuestaMias {
  aportaciones: Aportacion[]
  resumen: Record<EstadoAportacion, number>
}

export interface RespuestaPendientes {
  aportaciones: Aportacion[]
  resumen: { pendientes: number; procesando: number; validadas_30d: number; rechazadas_30d: number }
}

export interface Opciones {
  tareas: (TareaRef & { puesto: string; departamento_id: number })[]
  niveles?: { orden: number; nombre: string }[]
}

/** Pregunta pendiente tal y como la ve un empleado (sin datos personales). */
export interface PreguntaPendiente {
  id: number
  pregunta: string
  frecuencia: number
  ultima_vez: string | null
  tarea: TareaRef | null
  respuestas_en_revision: number
  mi_respuesta: { id: number; estado: EstadoAportacion } | null
}

export interface Laguna {
  id: number
  pregunta: string
  frecuencia: number
  estado: EstadoLaguna
  departamento: { id: number; nombre: string | null } | null
  tarea: TareaRef | null
  ejemplos: { pregunta: string; fecha: string | null }[]
  primera_vez: string | null
  ultima_vez: string | null
  respuestas_en_revision: number
  aportacion: { id: number; titulo: string | null; estado: EstadoAportacion; documento_id: number | null } | null
}

export interface RespuestaLagunas {
  lagunas: Laguna[]
  contadores: Record<EstadoLaguna, number>
}

/** 75 → «1:15» */
export function mmss(segundos?: number | null): string {
  const s = Math.max(0, Math.round(segundos ?? 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function nombreTarea(t?: TareaRef | null): string {
  if (!t) return ''
  return t.codigo ? `${t.codigo} · ${t.nombre}` : t.nombre
}

/** «1 vez» · «3 veces» */
export function veces(n: number): string {
  return n === 1 ? '1 vez' : `${n} veces`
}

/** Copia al portapapeles (con alternativa para contextos sin permiso). */
export async function copiarTexto(texto: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(texto)
    return
  } catch {
    /* sin permiso: alternativa clásica */
  }
  const area = document.createElement('textarea')
  area.value = texto
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  area.remove()
  if (!ok) throw new Error('No se ha podido copiar. Selecciona el texto y cópialo a mano.')
}
