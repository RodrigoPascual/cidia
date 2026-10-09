// Tipos de la API de progreso (/api/progreso/*) y utilidades de texto compartidas.

export interface Requisito {
  clave: 'inicio' | 'cuestionario' | 'ejecuciones' | 'observacion' | 'sin_criticos' | 'formador'
  nivel: number
  cumplido: boolean
  texto: string
  falta: string
}

export interface PuntoCurva {
  n: number
  ejecucion_id: number
  fecha: string | null
  consultas: number
  consultas_criticos: number
}

export interface EvidenciasTarea {
  cuestionarios: {
    id: number; fecha: string; puntuacion: number; aciertos: number; total: number
    aprobado: boolean; version: number | null; vigente: boolean
  }[]
  ejecuciones: {
    id: number; inicio: string; fin: string | null; estado: string; consultas: number; consultas_criticos: number
  }[]
  observaciones: {
    id: number; fecha: string; aprobada: boolean; evaluador: string | null; comentario: string | null
    pasos: number; pasos_ok: number
  }[]
  aportaciones: { id: number; titulo: string; fecha: string }[]
  microlecciones: { vistas: number; total: number }
  formador: { por_id: number | null; por?: string; fecha: string | null } | null
}

export interface EntradaHistorial {
  tipo: 'subida' | 'caducidad' | 'reevaluacion' | 'reevaluado' | 'ajuste'
  fecha: string
  nivel?: number
  nivel_anterior?: number
  por?: string
  motivo?: string
}

export interface TareaResumen {
  id: number
  codigo: string | null
  nombre: string
  criticidad: number
  puesto: string | null
  departamento?: string | null
}

export interface TareaProgreso {
  tarea: TareaResumen
  nivel: number
  letra: string
  nombre_nivel: string
  porcentaje: number
  desde: string | null
  caduca: string | null
  dias_para_caducar: number | null
  caducado: boolean
  caduca_pronto: boolean
  requiere_reevaluacion: boolean
  formador_validado: boolean
  instruccion: { id: number; codigo: string | null; titulo: string; version: number } | null
  cuestionario_disponible: boolean
  cuestionario_aprobado: boolean
  siguiente: { nivel: number; letra: string; texto: string | null } | null
  requisitos: Requisito[]
  evidencias: EvidenciasTarea
  historial: EntradaHistorial[]
  curva: PuntoCurva[]
}

export interface PersonaProgreso {
  id: number
  nombre: string
  iniciales: string
  puesto: string | null
  departamento?: string | null
  formaciones: { departamento: string; puesto: string | null }[]
}

export interface Progreso {
  persona: PersonaProgreso
  resumen: {
    tareas: number
    por_nivel: Record<'I' | 'L' | 'U' | 'O', number>
    sin_iniciar: number
    autonomas: number
    reevaluaciones: number
    caducan_pronto: number
  }
  tareas: TareaProgreso[]
}

export interface DetalleCelda extends TareaProgreso {
  persona: PersonaProgreso
  acciones: { observar: boolean; ajustar: boolean; validar_formador: boolean }
}

export interface Celda {
  usuario_id: number
  tarea_id: number
  nivel: number
  letra: string
  caduca: string | null
  caducado: boolean
  requiere_reevaluacion: boolean
  formador_validado: boolean
}

export interface AvisoNivel {
  usuario_id: number
  nombre: string
  tarea_id: number
  codigo: string | null
  tarea: string
  nivel: number
  letra: string
  caduca?: string
  caducado?: boolean
  dias?: number
}

export interface Indicadores {
  personas: number
  tareas: number
  celdas_l_o_mas: number
  polivalencia: number
  tareas_con_riesgo: number
  personas_por_tarea: { tarea_id: number; codigo: string | null; tarea: string; criticidad: number; i: number; l_o_mas: number; u_o_mas: number; o: number }[]
  caducidades_proximas: AvisoNivel[]
  reevaluaciones_pendientes: AvisoNivel[]
  tiempo_medio_primera_correcta: { dias: number | null; muestras: number }
}

export interface Matriz {
  departamento: { id: number; nombre: string } | null
  departamentos: { id: number; nombre: string }[]
  tareas: TareaResumen[]
  personas: { id: number; nombre: string; iniciales: string; puesto: string | null; rol: string; en_formacion: boolean }[]
  celdas: Celda[]
  indicadores: Indicadores | null
  puede_evaluar: boolean
}

export interface Planta {
  indicadores: Indicadores
  departamentos: {
    id: number; nombre: string; personas: number; tareas: number; celdas_l_o_mas: number; polivalencia: number
    tareas_con_riesgo: number; reevaluaciones: number; caducidades: number; tiempo_medio_dias: number | null
  }[]
}

/** «noviembre de 2027» */
export function mesAnio(iso?: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' })
}

/** «3,5 días», «5 h»… para el tiempo medio hasta la primera ejecución correcta. */
export function duracionDias(dias: number | null | undefined): string {
  if (dias === null || dias === undefined) return 'Sin datos'
  if (dias < 1) return `${Math.max(1, Math.round(dias * 24))} h`
  return `${dias.toLocaleString('es-ES', { maximumFractionDigits: 1 })} ${dias === 1 ? 'día' : 'días'}`
}

/** Texto de estado de una fila del pasaporte: validez o lo siguiente que falta. */
export function textoEstado(t: TareaProgreso): string {
  if (t.caducado) return 'Nivel caducado: hay que renovarlo'
  if (t.requiere_reevaluacion) return 'Versión nueva de la instrucción: falta la reevaluación'
  if (t.nivel >= 3 && t.caduca) return `Válido hasta ${mesAnio(t.caduca)}${t.nivel === 4 ? ' · puede formar a otros' : ''}`
  if (t.siguiente?.texto) return t.siguiente.texto
  return t.nivel > 0 && t.caduca ? `Válido hasta ${mesAnio(t.caduca)}` : 'Sin iniciar'
}
