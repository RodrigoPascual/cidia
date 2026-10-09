// Piezas compartidas por las páginas de aportaciones y lagunas.

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { CheckCircle2, ChevronDown, Hourglass, Loader2, X, XCircle } from 'lucide-react'
import { Esqueleto, Etiqueta, TextoFormato } from '../../ui'
import type { Aportacion, EstadoAportacion } from './tipos'

// ------------------------------------------------------------------ estado

const ESTADOS: Record<EstadoAportacion, { texto: string; tono: 'azul' | 'amarilla' | 'verde' | 'roja'; icono: ReactNode }> = {
  procesando: { texto: 'Ordenándose', tono: 'azul', icono: <Loader2 className="girando" /> },
  pendiente: { texto: 'Pendiente de validar', tono: 'amarilla', icono: <Hourglass /> },
  validada: { texto: 'Validada', tono: 'verde', icono: <CheckCircle2 /> },
  rechazada: { texto: 'No validada', tono: 'roja', icono: <XCircle /> },
}

export function EtiquetaEstado({ estado }: { estado: EstadoAportacion }) {
  const e = ESTADOS[estado]
  return <Etiqueta tono={e.tono} icono={e.icono}>{e.texto}</Etiqueta>
}

// ------------------------------------------------------------------ plegable

/** Bloque que se abre y se cierra (transcripción, texto original, ejemplos...). */
export function Plegable({ titulo, children, abierto: inicial = false, icono }: {
  titulo: ReactNode; children: ReactNode; abierto?: boolean; icono?: ReactNode
}) {
  const [abierto, setAbierto] = useState(inicial)
  return (
    <div className={`apo-plegable ${abierto ? 'abierto' : ''}`}>
      <button type="button" className="apo-plegable-boton" onClick={() => setAbierto((a) => !a)} aria-expanded={abierto}>
        {icono}
        <span>{titulo}</span>
        <ChevronDown className="apo-chevron" />
      </button>
      {abierto && <div className="apo-plegable-cuerpo">{children}</div>}
    </div>
  )
}

// ------------------------------------------------------------------ ficha Problema / Causa / Solución

/** Ficha de solo lectura. Mientras se procesa muestra un esqueleto. */
export function FichaAportacion({ ap }: { ap: Aportacion }) {
  if (ap.estado === 'procesando') {
    return (
      <div className="apo-ficha">
        {['Problema', 'Causa', 'Solución'].map((t) => (
          <div key={t} className="apo-bloque">
            <div className="apo-bloque-titulo">{t}</div>
            <Esqueleto alto={14} className="mb-1" />
            <Esqueleto alto={14} ancho="70%" />
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="apo-ficha">
      <BloqueFicha titulo="Problema" texto={ap.problema} vacio="Sin describir" />
      <BloqueFicha titulo="Causa" texto={ap.causa} vacio="No se ha indicado" />
      <BloqueFicha titulo="Solución" texto={ap.solucion} vacio="Pendiente de escribir" destacado />
    </div>
  )
}

function BloqueFicha({ titulo, texto, vacio, destacado }: { titulo: string; texto: string | null; vacio: string; destacado?: boolean }) {
  return (
    <div className={`apo-bloque ${destacado ? 'destacado' : ''}`}>
      <div className="apo-bloque-titulo">{titulo}</div>
      {texto ? <TextoFormato texto={texto} /> : <div className="apagado pequeno">{vacio}</div>}
    </div>
  )
}

/** Contenido de la pregunta frecuente publicada, con las etiquetas «Problema:», «Causa:»... en negrita. */
export function ContenidoPublicado({ texto }: { texto: string }) {
  const conFormato = texto.replace(/^(Pregunta|Problema|Causa|Solución|Tarea|Etiquetas):/gm, '**$1:**')
  return <TextoFormato texto={conFormato} />
}

// ------------------------------------------------------------------ edición

/** Área de texto que crece con su contenido (edición en línea). */
export function AreaAuto(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight + 2}px`
  }, [props.value])
  return <textarea ref={ref} rows={2} {...props} className={`area apo-area-auto ${props.className ?? ''}`} />
}

/** Lista de etiquetas editable: Intro o coma para añadir, × para quitar. */
export function EditorEtiquetas({ valor, onCambio, maximo = 10 }: { valor: string[]; onCambio: (v: string[]) => void; maximo?: number }) {
  const [texto, setTexto] = useState('')
  const anadir = (t: string) => {
    const limpio = t.trim().replace(/^#/, '').slice(0, 40)
    if (!limpio || valor.some((v) => v.toLowerCase() === limpio.toLowerCase()) || valor.length >= maximo) return
    onCambio([...valor, limpio])
  }
  const tecla = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      anadir(texto)
      setTexto('')
    } else if (e.key === 'Backspace' && !texto && valor.length) {
      onCambio(valor.slice(0, -1))
    }
  }
  return (
    <div className="apo-editor-etiquetas">
      {valor.map((v) => (
        <span key={v} className="etiqueta">
          {v}
          <button type="button" aria-label={`Quitar ${v}`} onClick={() => onCambio(valor.filter((x) => x !== v))}><X /></button>
        </span>
      ))}
      {valor.length < maximo && (
        <input value={texto} placeholder={valor.length ? 'Añadir…' : 'Añade palabras clave (Intro para separar)'}
          onChange={(e) => setTexto(e.target.value)} onKeyDown={tecla}
          onBlur={() => { if (texto.trim()) { anadir(texto); setTexto('') } }} />
      )}
    </div>
  )
}

// ------------------------------------------------------------------ sondeo

/** Repite `accion` cada `ms` mientras `activo` sea verdadero (p. ej. mientras algo se procesa). */
export function useSondeo(activo: boolean, accion: () => void, ms = 3000, clave?: unknown) {
  useEffect(() => {
    if (!activo) return
    const t = setTimeout(accion, ms)
    return () => clearTimeout(t)
    // `clave` cambia con cada respuesta: así se programa la siguiente consulta.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activo, clave])
}
