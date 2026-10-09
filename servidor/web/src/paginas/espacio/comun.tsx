// Tipos y utilidades del espacio de trabajo (explorador, vista previa y consola).

import {
  File, FileArchive, FileAudio, FileCode, FileImage, FileJson, FileQuestion, FileSpreadsheet, FileSymlink, FileText,
  FileVideo, Folder, Presentation,
} from 'lucide-react'

export type Vista = 'texto' | 'markdown' | 'csv' | 'imagen' | 'pdf' | null

export interface Elemento {
  nombre: string
  ruta: string
  tipo: 'carpeta' | 'fichero' | 'enlace' | 'especial'
  tamano: number
  modificado: string
  hijos?: Elemento[]
  vista?: Vista
  mime?: string
  url_descarga?: string
  url?: string | null
}

export interface Arbol {
  carpeta: string
  elementos: Elemento[]
  uso: number
  cuota: number
  max_fichero: number
  incompleto: boolean
  ejecutor_configurado: boolean
}

export interface Fichero extends Elemento {
  contenido: string | null
  truncado: boolean
  es_texto: boolean
}

export interface Ejecucion {
  codigo: number | null
  salida: string
  recortada: boolean
  duracion: number
  tiempo_agotado: boolean
  memoria_agotada: boolean
  cuota_superada: boolean
  uso: number
  cuota: number
}

/** ¿Se puede abrir? Los enlaces y los elementos especiales (FIFO, socket) que pueda crear una
 * orden en la caja de arena se ven, se renombran y se borran, pero no se abren. */
export function seAbre(el: Pick<Elemento, 'tipo'>): boolean {
  return el.tipo === 'carpeta' || el.tipo === 'fichero'
}

/** Une una carpeta y un nombre en una ruta relativa («» es la carpeta principal). */
export function unir(carpeta: string, nombre: string): string {
  return [carpeta, nombre].filter(Boolean).join('/')
}

/** Carpeta que contiene una ruta. */
export function padre(ruta: string): string {
  const i = ruta.lastIndexOf('/')
  return i < 0 ? '' : ruta.slice(0, i)
}

/** Busca una carpeta del árbol por su ruta. */
export function buscarCarpeta(elementos: Elemento[], ruta: string): Elemento[] | null {
  if (!ruta) return elementos
  let actual = elementos
  for (const parte of ruta.split('/')) {
    const siguiente = actual.find((e) => e.tipo === 'carpeta' && e.nombre === parte)
    if (!siguiente) return null
    actual = siguiente.hijos ?? []
  }
  return actual
}

/** Busca un fichero del árbol por su ruta. */
export function buscarElemento(elementos: Elemento[], ruta: string): Elemento | null {
  const lista = buscarCarpeta(elementos, padre(ruta))
  const nombre = ruta.slice(ruta.lastIndexOf('/') + 1)
  return lista?.find((e) => e.nombre === nombre) ?? null
}

export function extension(nombre: string): string {
  const i = nombre.lastIndexOf('.')
  return i > 0 ? nombre.slice(i + 1).toLowerCase() : ''
}

const TIPOS: { exts: string[]; icono: typeof File; tono: string }[] = [
  { exts: ['csv', 'tsv', 'xlsx', 'xls', 'ods'], icono: FileSpreadsheet, tono: 'hoja' },
  { exts: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'], icono: FileImage, tono: 'imagen' },
  { exts: ['pdf'], icono: FileText, tono: 'pdf' },
  { exts: ['doc', 'docx', 'odt', 'rtf'], icono: FileText, tono: 'documento' },
  { exts: ['ppt', 'pptx', 'odp'], icono: Presentation, tono: 'presentacion' },
  { exts: ['json'], icono: FileJson, tono: 'codigo' },
  { exts: ['py', 'js', 'ts', 'sh', 'html', 'htm', 'css', 'xml', 'yml', 'yaml', 'sql', 'r', 'ipynb', 'toml', 'ini'], icono: FileCode, tono: 'codigo' },
  { exts: ['zip', 'tar', 'gz', 'tgz', '7z', 'bz2', 'xz'], icono: FileArchive, tono: 'archivo' },
  { exts: ['mp3', 'wav', 'ogg', 'oga', 'opus', 'm4a', 'flac'], icono: FileAudio, tono: 'medio' },
  { exts: ['mp4', 'mov', 'avi', 'mkv', 'webm'], icono: FileVideo, tono: 'medio' },
  { exts: ['md', 'markdown', 'txt', 'log'], icono: FileText, tono: 'texto' },
]

/** Icono de un elemento según su tipo y extensión. */
export function IconoElemento({ el, tamano = 20 }: { el: Pick<Elemento, 'tipo' | 'nombre'>; tamano?: number }) {
  if (el.tipo === 'carpeta') return <Folder size={tamano} className="icono-el carpeta" />
  if (el.tipo === 'enlace') return <FileSymlink size={tamano} className="icono-el enlace" />
  if (el.tipo === 'especial') return <FileQuestion size={tamano} className="icono-el enlace" />
  const ext = extension(el.nombre)
  const t = TIPOS.find((x) => x.exts.includes(ext))
  const Icono = t?.icono ?? File
  return <Icono size={tamano} className={`icono-el ${t?.tono ?? 'otro'}`} />
}

/** Lee un CSV (detecta «;», «,» o tabulador; respeta comillas). Devuelve como mucho `maxFilas`. */
export function leerCsv(texto: string, maxFilas = 500): { filas: string[][]; mas: boolean } {
  const limpio = texto.replace(/^﻿/, '')
  const primera = limpio.slice(0, limpio.indexOf('\n') >= 0 ? limpio.indexOf('\n') : undefined)
  const candidatos = [';', ',', '\t']
  const sep = candidatos.reduce((a, b) => (primera.split(b).length > primera.split(a).length ? b : a), ',')
  const filas: string[][] = []
  let fila: string[] = []
  let campo = ''
  let comillas = false
  for (let i = 0; i < limpio.length; i++) {
    const c = limpio[i]
    if (comillas) {
      if (c === '"') {
        if (limpio[i + 1] === '"') { campo += '"'; i++ } else comillas = false
      } else campo += c
    } else if (c === '"') comillas = true
    else if (c === sep) { fila.push(campo); campo = '' }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && limpio[i + 1] === '\n') i++
      fila.push(campo); campo = ''
      if (fila.length > 1 || fila[0] !== '') filas.push(fila)
      fila = []
      if (filas.length > maxFilas) return { filas: filas.slice(0, maxFilas), mas: true }
    } else campo += c
  }
  if (campo !== '' || fila.length) { fila.push(campo); filas.push(fila) }
  return { filas: filas.slice(0, maxFilas), mas: filas.length > maxFilas }
}
