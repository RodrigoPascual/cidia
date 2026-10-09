// Tipos de las respuestas de /api/planta (ver cidia/servicios/planta.py).

import type { Fuente } from './copiloto'

export interface NivelTarea {
  nivel: number
  nivel_letra: string
  requiere_reevaluacion: boolean
  caduca: string | null
  caducado: boolean
}

export interface TareaPlanta extends NivelTarea {
  id: number
  codigo: string | null
  nombre: string
  descripcion: string | null
  criticidad: number
  riesgos_prl: string | null
  puesto: string | null
  departamento: string | null
  origen: 'puesto' | 'departamento' | 'formacion' | 'admin'
  instruccion: {
    id: number
    codigo: string | null
    version: number
    titulo: string
    pasos: number
    pasos_criticos: number
    portada_url: string | null
  }
  ejecuciones_completadas: number
  ultima_ejecucion: string | null
  ejecucion_en_curso: { id: number; inicio: string; pasos_confirmados: number; misma_version: boolean } | null
}

export interface PasoEjecucion {
  id: number
  orden: number
  numero: number
  titulo: string
  texto: string | null
  es_critico: boolean
  es_seguridad: boolean
  criterio_aceptacion: string | null
  imagen_url: string | null
  clip_url: string | null
  confirmado: boolean
  confirmado_en: string | null
  critico_confirmado: boolean
  consultas: number
}

export interface Veredicto {
  estado: 'comparada' | 'sin_vision' | 'sin_referencia' | 'error'
  coincide: boolean | null
  observaciones: string
  confianza: number | null
  modelo: string | null
  revision_humana: boolean
  mensaje: string
  foto_url: string | null
  referencia_url: string | null
}

export interface ConsultaHistorial {
  id: number
  paso_id: number | null
  pregunta: string
  respuesta: string | null
  fuentes: Fuente[]
  con_respaldo: boolean
  creada: string
}

export interface EjecucionDatos {
  id: number
  estado: 'en_curso' | 'completada' | 'abandonada'
  inicio: string | null
  fin: string | null
  duracion_s: number
  consultas: number
  consultas_criticos: number
  es_mia: boolean
  /** true: quien supervisa no puede abrir la tarea (otro departamento). Llegan el avance y las
   *  métricas, pero no el texto, las imágenes ni las respuestas del copiloto. */
  contenido_restringido?: boolean
  persona: { id: number; nombre: string } | null
  tarea: { id: number; codigo: string | null; nombre: string; riesgos_prl: string | null }
  instruccion: {
    id: number
    codigo: string | null
    version: number
    titulo: string
    resumen: string | null
    riesgos: string | null
    epis: string | null
    herramientas: string | null
    video_url: string | null
  }
  pasos: PasoEjecucion[]
  total_pasos: number
  pasos_confirmados: number
  paso_actual: number
  foto: Veredicto | null
  historial: ConsultaHistorial[]
  reanudada?: boolean
}

export interface ResumenFin extends Partial<NivelTarea> {
  duracion_s: number
  consultas: number
  consultas_criticos: number
  pasos: number
  pasos_criticos: number
  ejecuciones_completadas?: number
  nivel_anterior?: number
}
