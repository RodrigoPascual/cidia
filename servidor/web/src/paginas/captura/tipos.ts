// Tipos de la API de captura (/api/captura) y utilidades compartidas por sus páginas.

export type TipoCaptura = 'video' | 'audio' | 'entrevista'
export type EstadoCaptura = 'subida' | 'procesando' | 'borrador_listo' | 'error' | 'en_curso'

export interface Mensaje {
  rol: 'copiloto' | 'experto'
  texto: string
  tema: string
  momento: string
  voz?: boolean
  saltada?: boolean
}

export interface TemaGuion {
  clave: string
  titulo: string
  estado: 'hecho' | 'actual' | 'pendiente' | 'saltado'
}

export interface Ficha {
  id: number
  titulo: string
  contenido: string
  etiquetas: string[]
  estado: string
  publicada: boolean
  departamento: string | null
  validador: string | null
}

export interface Captura {
  id: number
  tipo: TipoCaptura
  titulo: string | null
  autor: { id: number; nombre: string } | null
  tarea: { id: number; codigo: string | null; nombre: string } | null
  estado: EstadoCaptura
  fase: string | null
  fase_texto: string | null
  fases: { clave: string; texto: string }[]
  progreso: number
  mensaje: string | null
  duracion: number | null
  creada: string
  actualizada: string
  instruccion_id: number | null
  documento_id: number | null
  miniatura_url: string | null
  origen_borrador: string | null
  borrador: { tipo: 'instruccion' | 'ficha'; id: number; version?: number; estado: string } | null
  entrevista?: { temas: TemaGuion[]; tema_actual: string; terminada: boolean; respuestas: number }
  // Solo en el detalle
  original_url?: string | null
  transcripcion?: { texto: string; segmentos: { inicio: number; fin: number; texto: string }[] } | null
  escenas?: { t: number; puntuacion: number }[] | null
  conversacion?: Mensaje[]
  ficha?: Ficha | null
}

/** ¿Está la captura esperando o procesándose en el servidor? */
export const enProceso = (c: Captura) => c.estado === 'subida' || c.estado === 'procesando'

/** 75 → «1:15» */
export function mmss(segundos?: number | null): string {
  if (segundos === null || segundos === undefined || Number.isNaN(segundos)) return ''
  const s = Math.max(0, Math.round(segundos))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`
}

export const NOMBRE_TIPO: Record<TipoCaptura, string> = {
  video: 'Vídeo',
  audio: 'Nota de voz',
  entrevista: 'Entrevista guiada',
}
