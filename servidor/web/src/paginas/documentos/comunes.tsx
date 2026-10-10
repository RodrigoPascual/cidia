// Piezas pequeñas que comparten la biblioteca, el detalle, la subida y la consola de búsqueda.

import { useEffect, type ReactNode } from 'react'
import {
  AlertTriangle, CheckCircle2, File, FileAudio, FileImage, FileSpreadsheet, FileText, ListChecks, Loader2,
  MessageCircleQuestion, NotebookText, PauseCircle, Presentation, X,
} from 'lucide-react'
import { Boton, Etiqueta } from '../../ui'
import { claseTipo, NOMBRE_META, type EstadoDocumento, type NivelOpcion } from './tipos'

const ICONOS: Record<string, ReactNode> = {
  pdf: <FileText />,
  word: <FileText />,
  excel: <FileSpreadsheet />,
  powerpoint: <Presentation />,
  texto: <File />,
  audio: <FileAudio />,
  imagen: <FileImage />,
  instruccion: <ListChecks />,
  faq: <MessageCircleQuestion />,
  ficha: <NotebookText />,
}

/** Icono del tipo de documento, con el color de su formato. */
export function IconoTipo({ tipo, nombre, grande, titulo }: { tipo: string; nombre?: string | null; grande?: boolean; titulo?: string }) {
  const clase = claseTipo(tipo, nombre)
  return (
    <span className={`doc-icono ${clase} ${grande ? 'grande' : ''}`} title={titulo} aria-hidden={!titulo}>
      {ICONOS[clase] ?? <File />}
    </span>
  )
}

/** Nivel mínimo como cuatro barras que se llenan, con el nombre del nivel. */
export function NivelMinimo({ nivel, nombre, maximo = 4, compacto }: { nivel: number; nombre?: string | null; maximo?: number; compacto?: boolean }) {
  const total = Math.max(maximo, nivel)
  return (
    <span className="doc-nivel" title={`Nivel mínimo ${nivel}${nombre ? ` · ${nombre}` : ''}`}>
      <span className="barras" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <i key={i} className={i < nivel ? 'lleno' : ''} style={{ height: 5 + (i * 9) / Math.max(1, total - 1) }} />
        ))}
      </span>
      <span className="codigo">N{nivel}</span>
      {!compacto && nombre && <span>{nombre}</span>}
    </span>
  )
}

export function EstadoEtiqueta({ estado, mensaje, interrumpido }: {
  estado: EstadoDocumento; mensaje?: string | null; interrumpido?: boolean
}) {
  if (estado === 'procesando' && interrumpido) {
    return (
      <Etiqueta tono="naranja" icono={<PauseCircle />} title="El indexado se cortó (por ejemplo, al reiniciar el servidor). Pulsa «Reindexar».">
        Interrumpido
      </Etiqueta>
    )
  }
  if (estado === 'procesando') return <Etiqueta tono="amarilla" icono={<Loader2 className="girando" />}>Procesando</Etiqueta>
  if (estado === 'error') return <Etiqueta tono="roja" icono={<AlertTriangle />} title={mensaje ?? undefined}>Con error</Etiqueta>
  if (estado === 'borrador') return <Etiqueta title="Ficha sin publicar: el copiloto todavía no la encuentra.">Borrador</Etiqueta>
  if (estado === 'obsoleto') return <Etiqueta tono="oscura" title={mensaje ?? 'Sustituido por una versión posterior.'}>Sustituido</Etiqueta>
  return <Etiqueta tono="verde" icono={<CheckCircle2 />}>Listo</Etiqueta>
}

/** Selector del nivel mínimo en botones (con el nombre de cada nivel). */
export function SelectorNivel({ niveles, valor, onCambio, deshabilitado }: {
  niveles: NivelOpcion[]; valor: number; onCambio: (n: number) => void; deshabilitado?: boolean
}) {
  return (
    <div className="doc-niveles" role="radiogroup" aria-label="Nivel mínimo">
      {niveles.map((n) => (
        <button
          key={n.orden} type="button" role="radio" aria-checked={valor === n.orden} disabled={deshabilitado}
          className={`doc-nivel-opcion ${valor === n.orden ? 'activa' : ''}`} onClick={() => onCambio(n.orden)}
          title={n.descripcion ?? undefined}
        >
          <div className="n">N{n.orden}</div>
          <div className="t">{n.nombre}</div>
        </button>
      ))}
    </div>
  )
}

/** Metadatos de un fragmento como fichas pequeñas (las claves internas del motor, aparte). */
export function MetaFragmento({ metadatos, internas = false }: { metadatos: Record<string, unknown>; internas?: boolean }) {
  const piezas = Object.entries(metadatos).filter(([, v]) => v !== null && v !== undefined && v !== '')
  const conNombre = piezas.filter(([k]) => NOMBRE_META[k])
  const resto = internas ? piezas.filter(([k]) => !NOMBRE_META[k]) : []
  return (
    <>
      {conNombre.map(([k, v]) => <span key={k} className="doc-meta">{NOMBRE_META[k]} {String(v)}</span>)}
      {resto.map(([k, v]) => (
        <span key={k} className="doc-meta interna" title={`${k}: ${JSON.stringify(v)}`}>
          {k}={typeof v === 'object' ? JSON.stringify(v) : String(v).slice(0, 18)}
        </span>
      ))}
    </>
  )
}

/** Panel lateral deslizante (detalle de un documento). Se cierra con Escape o pulsando fuera. */
export function Cajon({ abierto, onCerrar, cabecera, pie, children }: {
  abierto: boolean; onCerrar: () => void; cabecera: ReactNode; pie?: ReactNode; children: ReactNode
}) {
  useEffect(() => {
    if (!abierto) return
    // Con un diálogo abierto encima (editar, confirmar borrado), Escape cierra solo el diálogo.
    const tecla = (e: KeyboardEvent) => e.key === 'Escape' && !document.querySelector('.velo') && onCerrar()
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [abierto, onCerrar])
  if (!abierto) return null
  return (
    <>
      <div className="doc-velo" onClick={onCerrar} />
      <aside className="doc-cajon" role="dialog" aria-modal="true">
        <div className="doc-cajon-cabecera">
          <div className="crece">{cabecera}</div>
          <Boton variante="fantasma" icono={<X />} onClick={onCerrar} aria-label="Cerrar" />
        </div>
        <div className="doc-cajon-cuerpo">{children}</div>
        {pie && <div className="doc-cajon-pie">{pie}</div>}
      </aside>
    </>
  )
}
