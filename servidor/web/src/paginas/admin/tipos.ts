// Tipos de las respuestas de /api/admin/* (ver servidor/gateway/cidia/rutas/admin*.py).

export interface Nivel {
  id: number
  orden: number
  nombre: string
  descripcion: string | null
  n_personas: number
}

export interface Tarea {
  id: number
  puesto_id: number
  departamento_id: number | null
  codigo: string | null
  nombre: string
  descripcion: string | null
  criticidad: number
  riesgos_prl: string | null
  nivel_minimo: number
  activa: boolean
  n_instrucciones: number
  instruccion_publicada: boolean
}

export interface Puesto {
  id: number
  departamento_id: number
  nombre: string
  descripcion: string | null
  n_personas: number
  tareas: Tarea[]
}

export interface Departamento {
  id: number
  nombre: string
  codigo: string | null
  descripcion: string | null
  color: string | null
  n_personas: number
  puestos: Puesto[]
}

export interface Organizacion {
  departamentos: Departamento[]
  niveles: Nivel[]
  resumen: { departamentos: number; puestos: number; tareas: number; tareas_activas: number; personas: number }
}

export interface Empresa {
  nombre: string
  sector: string | null
  config_iluo: { ejecuciones_para_L: number; umbral_cuestionario: number; meses_validez: number; [k: string]: unknown }
  por_defecto: { ejecuciones_para_L: number; umbral_cuestionario: number; meses_validez: number }
}

export type Rol = 'empleado' | 'jefe' | 'admin'

export interface Formacion {
  id: number
  usuario_id: number
  departamento: { id: number; nombre: string | null; color: string | null }
  puesto: { id: number; nombre: string } | null
  estado: 'activa' | 'completada' | 'cancelada'
  inicio: string | null
  fin_previsto: string | null
}

export interface Empleado {
  id: number
  usuario: string
  nombre: string
  iniciales: string
  email: string | null
  departamento: { id: number; nombre: string; color: string | null } | null
  nivel: { id: number; orden: number; nombre: string } | null
  puesto: { id: number; nombre: string } | null
  rol: Rol
  es_experto: boolean
  activo: boolean
  origen_identidad: 'local' | 'ldap' | 'oidc'
  origen_texto: string
  contrasena_gestionable: boolean
  formaciones_activas: number
  creado: string | null
  ultimo_acceso: string | null
  formaciones?: Formacion[]
}

export interface ListaEmpleados {
  empleados: Empleado[]
  total: number
  solo_lectura: boolean
}

export interface ModeloIA {
  id: number
  nombre: string
  ref: string
  tipo: 'chat' | 'embeddings' | 'vision' | 'asr'
  tipo_texto: string
  ubicacion: 'local' | 'nube'
  donde: string
  proveedor: string
  permitido: boolean
  predeterminado: boolean
  soporta_vision: boolean
  descripcion: string | null
  descargado: boolean | null
  bloqueado: boolean
  /** Modelo de búsqueda con el que el servidor indexa los documentos: no se puede desactivar ni sustituir aquí. */
  indexa_documentos: boolean
  uso: string
}

export interface RespuestaModelos {
  modelos: ModeloIA[]
  servidor: { ok: boolean; error: string | null; descargados: string[]; sin_registrar: string[] }
  permitir_nube: boolean
  creado?: ModeloIA
}

export interface SentenciaXapi {
  id: string
  momento: string
  actor_id: number | null
  actor_nombre: string | null
  verbo: string
  verbo_texto: string
  objeto_tipo: string
  objeto_id: string | null
  objeto_nombre: string | null
  texto: string
  resultado: Record<string, unknown> | null
  contexto: Record<string, unknown> | null
  sentencia: Record<string, unknown>
}

export interface PaginaXapi {
  total: number
  pagina: number
  por_pagina: number
  paginas: number
  sentencias: SentenciaXapi[]
  verbos: { clave: string; nombre: string }[]
  tipos_objeto: string[]
}

export interface FilaAuditoria {
  id: number
  momento: string
  usuario_id: number | null
  usuario_nombre: string | null
  accion: string
  entidad: string | null
  entidad_id: string | null
  detalle: Record<string, unknown> | null
  texto: string
}

export interface PaginaAuditoria {
  total: number
  pagina: number
  por_pagina: number
  paginas: number
  filas: FilaAuditoria[]
  acciones: string[]
  entidades: string[]
}

export const NOMBRE_ROL_ADMIN: Record<Rol, string> = {
  empleado: 'Empleado',
  jefe: 'Jefe de equipo',
  admin: 'Administración',
}

export const CRITICIDAD = [
  { valor: 1, texto: 'Baja', tono: 'verde' as const },
  { valor: 2, texto: 'Media', tono: 'naranja' as const },
  { valor: 3, texto: 'Alta', tono: 'roja' as const },
]

/** Colores que se ofrecen para los departamentos. */
export const PALETA = ['#1F8A70', '#2F6FBF', '#C8442F', '#7A4FB5', '#D97A00', '#0E7C86', '#8A6D00', '#3A4048']

/** Construye una cadena de consulta sin los valores vacíos. */
export function consulta(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}
