// Tipos de las respuestas de /api/formacion (ver cidia/servicios/formacion.py).

import type { NivelTarea } from '../planta/tipos'

export interface Siguiente {
  accion: 'esperar' | 'reevaluar' | 'renovar' | 'microleccion' | 'cuestionario' | 'practicar' | 'esperar_cuestionario'
    | 'observacion' | 'formador' | 'completo'
  texto: string
  ruta: string
  microleccion_id?: number
}

export interface FormacionResumen {
  id: number
  departamento: string
  puesto: string | null
  inicio: string | null
  fin_previsto: string | null
}

export interface ItemItinerario extends NivelTarea {
  tarea_id: number
  codigo: string | null
  nombre: string
  descripcion: string | null
  criticidad: number
  puesto: string | null
  departamento: string | null
  origen: 'puesto' | 'departamento' | 'formacion' | 'admin'
  formacion: FormacionResumen | null
  tiene_instruccion: boolean
  instruccion: { id: number; codigo: string | null; version: number; titulo: string; pasos: number; pasos_criticos: number } | null
  microlecciones: { total: number; vistas: number }
  cuestionario: { disponible: boolean; aprobado: boolean }
  ejecuciones: { completadas: number; objetivo: number }
  observacion_aprobada: boolean
  avance: number
  siguiente: Siguiente
}

export interface FormacionActiva extends FormacionResumen {
  otro_departamento: boolean
  tareas: number
  avance: number
}

export interface Itinerario {
  tareas: ItemItinerario[]
  formaciones: FormacionActiva[]
  resumen: { tareas: number; autonomas: number; en_curso: number; reevaluacion: number; avance_medio: number }
}

export interface Leccion {
  id: number
  orden: number
  titulo: string
  contenido: string
  punto_clave: string | null
  pregunta: { enunciado: string; opciones: string[] } | null
  vista: boolean
}

/** Corrección de la pregunta de control. El servidor solo dice cuál es la correcta (y la explica)
 *  al acertar o a partir del segundo fallo (`revelada`). */
export interface Correccion {
  correcta: boolean
  opcion_correcta: number | null
  explicacion: string
  revelada: boolean
}

export interface DetalleTarea extends Omit<ItemItinerario, 'instruccion'> {
  riesgos_prl: string | null
  instruccion: {
    id: number
    codigo: string | null
    version: number
    titulo: string
    resumen: string | null
    riesgos: string | null
    epis: string | null
    herramientas: string | null
    publicada_en: string | null
    video_url: string | null
    pasos: { id: number; numero: number; titulo: string; es_critico: boolean; es_seguridad: boolean; imagen_url: string | null }[]
  } | null
  lecciones: Leccion[]
  evaluacion: {
    disponible: boolean
    aprobado: boolean
    intentos: number
    ultimo: { puntuacion: number; aprobado: boolean; aciertos: number; total: number; creado: string } | null
  }
  puede_generar: boolean
  generacion: { trabajo_id: number; estado: string; mensaje: string | null } | null
}
