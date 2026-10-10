// Tipos del copiloto (respuestas de /api/consulta).

export type Modo = 'normal' | 'socratico' | 'planta'

/** Fuente citada en una respuesta: [n] en el texto apunta a la fuente con ese n. */
export interface Fuente {
  n: number
  documento_id: number | null
  titulo: string
  tipo?: string | null
  version?: number | null
  paso?: number | null
  paso_id?: number | null
  codigo?: string | null
  pagina?: number | null
  hoja?: string | null
  diapositiva?: number | null
  autor?: string | null
  validador?: string | null
  origen?: string | null
  origen_id?: number | null
  /** Tarea de la instrucción citada (para abrirla en formación o en el modo planta). */
  tarea_id?: number | null
  fragmento: string
  similitud?: number | null
  url?: string | null
  /** false: en el historial, documento que ya no puedes ver (o que se ha borrado) */
  disponible?: boolean
  /** en el historial, versión de una instrucción que ya se ha sustituido por otra más reciente */
  obsoleta?: boolean
}

export interface Mensaje {
  id: string
  rol: 'usuario' | 'asistente'
  texto: string
  /** buscando: aún no hay texto · escribiendo: llegan tokens · listo · error */
  estado: 'buscando' | 'escribiendo' | 'listo' | 'error'
  fuentes?: Fuente[]
  con_respaldo?: boolean
  /** sin respaldo y era una pregunta de verdad (no un saludo): se muestra el aviso */
  aviso_sin_respaldo?: boolean
  laguna_id?: number | null
  consulta_id?: number
  citadas?: number[]
  valoracion?: 1 | -1 | null
  error?: string
  /** el error no se arregla reintentando (límite de uso, permiso o pregunta no válida) */
  sinReintento?: boolean
  modo?: Modo
  voz?: boolean
  duracion_ms?: number
  /** pregunta que originó la respuesta (para reintentar) */
  pregunta?: string
}

/** Consulta guardada (GET /api/consulta/historial). */
export interface ConsultaGuardada {
  id: number
  pregunta: string
  respuesta: string | null
  modo: Modo
  fuentes: Fuente[]
  con_respaldo: boolean
  aviso_sin_respaldo?: boolean
  laguna_id: number | null
  citadas: number[]
  valoracion: 1 | -1 | null
  duracion_ms: number | null
  creada: string
}

export interface PaginaHistorial {
  elementos: ConsultaGuardada[]
  total: number
  pagina: number
  por_pagina: number
  paginas: number
}

const NOMBRE_TIPO: Record<string, string> = {
  pdf: 'PDF',
  office: 'Office',
  texto: 'Texto',
  audio: 'Nota de voz',
  imagen: 'Imagen',
  instruccion: 'Instrucción',
  faq: 'Solución validada',
  ficha: 'Ficha',
}

export function nombreTipo(tipo?: string | null): string {
  return (tipo && NOMBRE_TIPO[tipo]) || 'Documento'
}

/**
 * Título de la fuente para mostrar junto a su versión. El de una instrucción indexada acaba en «(v1)»
 * («IT-023 · Montaje de la brida B (v1)»): si la versión ya se enseña aparte, no se repite («(v1) v1»).
 */
export function tituloFuente(f: { titulo?: string | null; version?: number | null }): string {
  const t = f.titulo ?? ''
  return f.version ? t.replace(new RegExp(`\\s*\\(v${f.version}\\)$`), '') : t
}

/** «v2 · paso 3 · pág. 4»: dónde está el dato dentro del documento (el código solo si el título no lo lleva ya). */
export function ubicacion(f: Fuente): string {
  const partes: string[] = []
  if (f.codigo && !f.titulo?.includes(f.codigo)) partes.push(f.codigo)
  if (f.version) partes.push(`v${f.version}`)
  // El «paso 0» de una instrucción es su cabecera: resumen, riesgos, EPI y herramientas.
  if (f.paso === 0) partes.push('datos generales')
  else if (f.paso !== null && f.paso !== undefined) partes.push(`paso ${f.paso}`)
  if (f.pagina) partes.push(`pág. ${f.pagina}`)
  if (f.hoja) partes.push(`hoja ${f.hoja}`)
  if (f.diapositiva) partes.push(`diapositiva ${f.diapositiva}`)
  return partes.join(' · ')
}
