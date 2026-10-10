// Tipos de la API de instrucciones (/api/instrucciones) y utilidades compartidas.

export type EstadoInstruccion = 'borrador' | 'en_revision' | 'publicada' | 'obsoleta'

export interface Persona {
  id: number
  nombre: string
}

export interface Paso {
  id: number | null
  orden: number
  titulo: string
  texto: string
  es_critico: boolean
  es_seguridad: boolean
  criterio_aceptacion: string
  imagen_url: string | null
  clip_url: string | null
  t_inicio: number | null
  t_fin: number | null
}

export interface TareaResumen {
  id: number
  codigo: string | null
  nombre: string
  puesto: string | null
  departamento_id: number | null
  departamento: string | null
  nivel_minimo: number
  criticidad: number
}

export interface Instruccion {
  id: number
  tarea_id: number
  tarea: TareaResumen
  codigo: string | null
  version: number
  estado: EstadoInstruccion
  titulo: string
  resumen: string
  riesgos: string
  epis: string
  herramientas: string
  autor: Persona | null
  revisor: Persona | null
  captura_id: number | null
  video_url: string | null
  documento_id: number | null
  creada: string | null
  publicada_en: string | null
  n_pasos: number
  pasos_criticos: number
  pasos_seguridad: number
  miniatura_url: string | null
  pasos?: Paso[]
  // Solo en el detalle
  vigente?: { id: number; version: number } | null
  borrador_existente?: { id: number; version: number } | null
  n_versiones?: number
  editable?: boolean
  reevaluaciones?: number
  ya_existia?: boolean
  /** Lo que dijo el experto en el vídeo de la captura (solo en el detalle). */
  transcripcion?: Segmento[] | null
}

export interface Segmento {
  inicio: number
  fin: number
  texto: string
}

export interface TareaGestionable extends TareaResumen {
  publicada: { id: number; version: number } | null
  borrador: { id: number; version: number } | null
  versiones: number
}

export interface Version {
  id: number
  version: number
  estado: EstadoInstruccion
  codigo: string | null
  titulo: string
  autor: Persona | null
  revisor: Persona | null
  n_pasos: number
  creada: string | null
  publicada_en: string | null
  actual: boolean
}

export interface CambioCampo {
  campo: string
  nombre: string
  antes: string | null
  despues: string | null
}

export interface CambioPaso {
  tipo: 'nuevo' | 'eliminado' | 'modificado' | 'movido'
  orden_antes: number | null
  orden_despues: number | null
  titulo: string
  campos: CambioCampo[]
}

export interface Diferencias {
  de: { id: number; version: number; estado: EstadoInstruccion } | null
  a: { id: number; version: number; estado: EstadoInstruccion }
  generales: CambioCampo[]
  pasos: CambioPaso[]
  sin_cambios: boolean
  sin_anterior?: boolean
}

export const ESTADOS: Record<EstadoInstruccion, { texto: string; tono: 'amarilla' | 'verde' | 'oscura' | 'azul' }> = {
  borrador: { texto: 'Borrador', tono: 'amarilla' },
  en_revision: { texto: 'En revisión', tono: 'azul' },
  publicada: { texto: 'Publicada', tono: 'verde' },
  obsoleta: { texto: 'Obsoleta', tono: 'oscura' },
}

/** «IT-023 · Montaje de la brida B» */
export function textoTarea(t: { codigo: string | null; nombre: string }): string {
  return t.codigo ? `${t.codigo} · ${t.nombre}` : t.nombre
}

/** 75 → «1:15» */
export function mmss(segundos?: number | null): string {
  if (segundos === null || segundos === undefined || Number.isNaN(segundos)) return ''
  const s = Math.max(0, Math.round(segundos))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
