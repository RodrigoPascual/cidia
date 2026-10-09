// Tipos de la API de documentos (/api/documentos) y utilidades de presentación.

export type EstadoDocumento = 'procesando' | 'listo' | 'error' | 'borrador'

export interface Documento {
  id: number
  titulo: string
  descripcion: string | null
  tipo: string
  tipo_nombre: string
  departamento_id: number | null
  departamento: string | null
  nivel_minimo: number
  nivel_nombre: string | null
  es_formacion: boolean
  es_publico: boolean
  estado: EstadoDocumento
  mensaje_estado: string | null
  nombre_fichero: string | null
  tamano: number | null
  url: string | null
  url_descarga: string | null
  mime: string | null
  autor: string | null
  validador: string | null
  subido_por: string | null
  origen: string
  origen_id: number | null
  version: number
  fragmentos: number
  creado: string | null
  actualizado: string | null
  motor_id: string | null
  puede_editar: boolean
  /** Tiene un indexado en la cola o en curso. */
  indexando: boolean
  /** Está «procesando» pero sin trabajo vivo (p. ej. se reinició el servidor): hay que reindexarlo. */
  interrumpido: boolean
}

export interface ListaDocumentos {
  documentos: Documento[]
  total: number
  pagina: number
  por_pagina: number
  paginas: number
  /** `indexando`: documentos visibles con un indexado vivo (decide la recarga automática). */
  resumen: { total: number; listo: number; procesando: number; error: number; indexando: number }
  motor: string
}

export interface FragmentoMuestra {
  id: number
  orden: number
  texto: string
  metadatos: Record<string, unknown>
  caracteres: number
  con_vector: boolean
}

export interface TrabajoDocumento {
  id: number
  estado: 'pendiente' | 'en_curso' | 'completado' | 'error'
  progreso: number
  mensaje: string | null
  creado: string | null
  actualizado: string | null
}

export interface DetalleDocumento extends Documento {
  texto_extraido: string | null
  texto_extraido_recortado: boolean
  fragmentos_total: number
  fragmentos_muestra: FragmentoMuestra[]
  trabajos: TrabajoDocumento[]
  motor: string
}

export interface DepartamentoOpcion { id: number; nombre: string; codigo: string | null; color: string | null; gestionable: boolean }
export interface NivelOpcion { orden: number; nombre: string; descripcion: string | null }
export interface PersonaOpcion { id: number; nombre: string; usuario: string; rol: string; departamento: string | null; nivel: string | null }

export interface Opciones {
  departamentos: DepartamentoOpcion[]
  niveles: NivelOpcion[]
  tipos: { valor: string; texto: string }[]
  tipos_subida: string[]
  estados: { valor: string; texto: string }[]
  es_admin: boolean
  departamento_propio: number | null
  motor: string
  umbral_respaldo: number
  fragmentos_por_consulta: number
  personas?: PersonaOpcion[]
}

export interface ResultadoBusqueda {
  posicion: number
  documento_id: number
  titulo: string
  texto: string
  puntuacion: number
  similitud: number | null
  supera_umbral: boolean
  fragmento_id: number | string | null
  metadatos: Record<string, unknown>
  departamento: string | null
  nivel_minimo: number | null
  nivel_nombre: string | null
  es_publico: boolean | null
  es_formacion: boolean | null
  puede_abrir: boolean
}

export interface RespuestaBusqueda {
  consulta: string
  motor: string
  k: number
  duracion_ms: number
  umbral_respaldo: number
  con_respaldo: boolean
  como: { id: number | null; nombre: string; rol: string; departamento: string | null; nivel: string | null }
  alcance: { tipo: 'todo' | 'publico' | 'departamento' | 'formacion'; texto: string }[]
  ambitos: { base: string; etiquetas: string[] | null; descripcion: string }[] | null
  resultados: ResultadoBusqueda[]
}

// ------------------------------------------------------------------ formatos

/** Extensiones que admite la subida (las mismas que reconoce el servidor). */
export const EXTENSIONES: Record<string, string[]> = {
  pdf: ['.pdf'],
  office: ['.docx', '.xlsx', '.pptx'],
  texto: ['.txt', '.md', '.csv', '.json', '.log'],
  audio: ['.mp3', '.wav', '.m4a', '.ogg', '.oga', '.opus', '.webm', '.flac', '.aac'],
  imagen: ['.png', '.jpg', '.jpeg', '.webp'],
}
export const ACEPTA = Object.values(EXTENSIONES).flat().join(',')

export function extension(nombre?: string | null): string {
  const i = (nombre ?? '').lastIndexOf('.')
  return i >= 0 ? (nombre ?? '').slice(i).toLowerCase() : ''
}

export function tipoDeFichero(nombre: string): string | null {
  const ext = extension(nombre)
  for (const [tipo, lista] of Object.entries(EXTENSIONES)) if (lista.includes(ext)) return tipo
  return null
}

/** Clase de color e icono según el tipo (y la extensión, para distinguir Word, Excel y PowerPoint). */
export function claseTipo(tipo: string, nombre?: string | null): string {
  if (tipo === 'office') {
    const ext = extension(nombre)
    return ext === '.xlsx' ? 'excel' : ext === '.pptx' ? 'powerpoint' : 'word'
  }
  return tipo
}

export const NOMBRE_ORIGEN: Record<string, string> = {
  subida: 'Subido a mano',
  instruccion: 'Instrucción publicada',
  aportacion: 'Aportación validada',
  captura: 'Captura',
}

/** Metadatos de un fragmento que se enseñan con nombre (el resto se ve como clave interna). */
export const NOMBRE_META: Record<string, string> = {
  pagina: 'Página',
  hoja: 'Hoja',
  diapositiva: 'Diapositiva',
  paso: 'Paso',
  codigo: 'Código',
}

/** Número en castellano con hasta `decimales` decimales. */
export function numero(n: number | null | undefined, decimales = 2): string {
  if (n === null || n === undefined) return '-'
  return n.toLocaleString('es-ES', { maximumFractionDigits: decimales, minimumFractionDigits: Math.min(2, decimales) })
}

/** Frase con quién encontrará un documento según sus etiquetas (misma regla que el servidor). */
export function quienLoEncontrara(
  departamento: string | null, nivel: NivelOpcion | undefined, formacion: boolean, publico: boolean,
): string {
  if (publico) return 'Cualquier persona, también sin iniciar sesión: es un documento público.'
  if (!departamento) return 'Solo la administración: no tiene departamento ni es público.'
  const partes = [
    nivel && nivel.orden > 1
      ? `las personas de ${departamento} con nivel ${nivel.nombre} o superior`
      : `todas las personas de ${departamento}`,
  ]
  if (formacion) partes.push(`quienes se estén formando en ${departamento}`)
  return `Lo encontrarán ${partes.join(' y ')}, además de la administración.`
}
