// Tipos de la API de evaluación (/api/evaluacion/*).

export interface NivelResultado {
  nivel: number
  letra: string
  nombre: string
  subio: boolean
}

export interface CuestionarioDisponible {
  tarea_id: number
  codigo: string | null
  tarea: string
  puesto: string | null
  instruccion_id: number
  titulo: string
  version: number
  preguntas: number
  aprobado: boolean
  intentos: number
  requiere_reevaluacion: boolean
  /** Lo aprobó, pero hace más de lo que dura la validez (o un jefe ajustó el nivel después). */
  aprobado_caducado: boolean
  pendiente: boolean
  nivel: number
  letra: string
  ultimo: { fecha: string; puntuacion: number; aprobado: boolean } | null
}

export interface InstruccionRevision {
  id: number
  codigo: string | null
  titulo: string
  version: number
  estado: string
  tarea_id: number
  tarea: string | null
  propuestas: number
  aprobadas: number
  descartadas: number
  generando: boolean
}

export interface ObservacionSugerida {
  usuario_id: number
  nombre: string
  tarea_id: number
  codigo: string | null
  tarea: string
  nivel: number
  letra: string
  desde: string | null
  motivo: string
}

export interface Pendientes {
  cuestionarios: CuestionarioDisponible[]
  preguntas?: InstruccionRevision[]
  observaciones?: ObservacionSugerida[]
}

export interface PasoBreve {
  orden: number
  titulo: string
  es_critico: boolean
}

export interface Cuestionario {
  tarea: { id: number; codigo: string | null; nombre: string }
  instruccion: { id: number; codigo: string | null; titulo: string; version: number }
  umbral: number
  intentos_previos: number
  // `clave` es opaca: no revela la posición original de la opción (ni, por tanto, la correcta).
  preguntas: { id: number; enunciado: string; opciones: { clave: string; texto: string }[]; paso: PasoBreve | null }[]
}

export interface Pregunta {
  id: number
  instruccion_id: number
  paso_id: number | null
  paso: (PasoBreve & { id: number }) | null
  enunciado: string
  opciones: string[]
  correcta: number
  explicacion: string | null
  estado: 'propuesta' | 'aprobada' | 'descartada'
  creada: string | null
}

export interface ResultadoCuestionario {
  intento_id: number
  aprobado: boolean
  aciertos: number
  total: number
  puntuacion: number
  umbral: number
  correccion: (Pregunta & { elegida: number | null; acierto: boolean })[]
  nivel: NivelResultado
  siguiente: string | null
}

export interface PasoInstruccion {
  id: number
  orden: number
  titulo: string
  es_critico: boolean
  es_seguridad: boolean
}

export interface ListaPreguntas {
  instruccion: { id: number; codigo: string | null; titulo: string; version: number; estado: string; tarea: string | null; pasos: PasoInstruccion[] }
  preguntas: Pregunta[]
  generando: boolean
}

export interface PasoPlantilla {
  paso_id: number
  orden: number
  titulo: string
  texto: string | null
  critico: boolean
  seguridad: boolean
  criterio: string | null
}

export interface ObservacionResumen {
  id: number
  evaluador: string | null
  aprobada: boolean
  comentario: string | null
  fecha: string
  pasos: number
  pasos_ok: number
  criticos_fallidos: number
}

export interface Plantilla {
  persona: { id: number; nombre: string; puesto: string | null }
  tarea: { id: number; codigo: string | null; nombre: string; riesgos_prl: string | null }
  instruccion: { id: number; codigo: string | null; titulo: string; version: number }
  nivel: { nivel: number; letra: string; caducado: boolean }
  lista: PasoPlantilla[]
  previas: ObservacionResumen[]
}

export interface ResultadoObservacion {
  observacion: ObservacionResumen
  nivel: NivelResultado
  siguiente: string | null
}

export const LETRAS_OPCION = ['A', 'B', 'C', 'D', 'E', 'F']

/** Estado de una instrucción en castellano para mostrarlo. */
export const NOMBRE_ESTADO_INSTRUCCION: Record<string, string> = {
  borrador: 'borrador', en_revision: 'en revisión', publicada: 'publicada', obsoleta: 'obsoleta',
}
