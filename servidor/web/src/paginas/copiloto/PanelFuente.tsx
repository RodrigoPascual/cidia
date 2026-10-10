// Panel lateral con la fuente de una cita: fragmento, documento, versión, paso, autor y validador.

import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  BadgeCheck, ChevronLeft, ChevronRight, ExternalLink, FileText, GraduationCap, ListChecks, Quote, UserRound, Wrench, X,
} from 'lucide-react'
import { urlServidor } from '../../api'
import { useSesion } from '../../sesion'
import { Aviso, Boton, Etiqueta } from '../../ui'
import { nombreTipo, ubicacion, type Fuente } from './tipos'

export default function PanelFuente({ fuentes, n, citadas, onCambiar, onCerrar }: {
  fuentes: Fuente[]
  n: number | null
  citadas?: number[]
  onCambiar: (n: number) => void
  onCerrar: () => void
}) {
  const { puede } = useSesion()
  const indice = fuentes.findIndex((f) => f.n === n)
  const f = indice >= 0 ? fuentes[indice] : null
  const caja = useRef<HTMLElement>(null)
  const abierto = !!f

  // Al abrirse, el foco pasa al panel (el teclado y los lectores de pantalla siguen la cita); al
  // cerrarse vuelve a donde estaba (la cita o el chip de la fuente).
  useEffect(() => {
    if (!abierto) return
    const anterior = document.activeElement as HTMLElement | null
    caja.current?.focus({ preventScroll: true })
    return () => { if (anterior && document.contains(anterior)) anterior.focus({ preventScroll: true }) }
  }, [abierto])

  useEffect(() => {
    if (!f) return
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCerrar()
      if (e.key === 'ArrowRight' && indice < fuentes.length - 1) onCambiar(fuentes[indice + 1].n)
      if (e.key === 'ArrowLeft' && indice > 0) onCambiar(fuentes[indice - 1].n)
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [f, indice, fuentes, onCambiar, onCerrar])

  if (!f) return null
  const donde = ubicacion(f)
  // El editor de instrucciones solo lo abren expertos, jefes y administración. Los demás van a la
  // tarea: en formación (lecciones, resumen y pasos) o, si no tienen formación, al modo planta.
  const esInstruccion = f.origen === 'instruccion' && f.disponible !== false
  const enlace = !esInstruccion ? null
    : puede('instrucciones') && f.origen_id
      ? { a: `/instrucciones/${f.origen_id}`, texto: 'Ver la instrucción', icono: <ListChecks /> }
      : f.tarea_id && puede('formacion')
        ? { a: `/formacion/tarea/${f.tarea_id}`, texto: 'Ver la tarea en formación', icono: <GraduationCap /> }
        : puede('planta')
          ? { a: '/planta', texto: 'Practicarla en el modo planta', icono: <Wrench /> }
          : null

  return (
    <>
      <div className="panel-fuente-velo" onClick={onCerrar} />
      <aside ref={caja} className="panel-fuente" role="dialog" aria-modal="true" aria-label={`Fuente ${f.n}`} tabIndex={-1}>
        <div className="panel-fuente-cabecera">
          <div className="fila">
            <span className="cita grande">{f.n}</span>
            <div>
              <div className="antetitulo-panel">Fuente {f.n} de {fuentes.length}</div>
              {citadas?.includes(f.n) && <div className="diminuto apagado">Citada en la respuesta</div>}
            </div>
          </div>
          <div className="fila" style={{ gap: 4 }}>
            <Boton variante="fantasma" tamano="pequeno" icono={<ChevronLeft />} aria-label="Fuente anterior"
              disabled={indice <= 0} onClick={() => onCambiar(fuentes[indice - 1].n)} />
            <Boton variante="fantasma" tamano="pequeno" icono={<ChevronRight />} aria-label="Fuente siguiente"
              disabled={indice >= fuentes.length - 1} onClick={() => onCambiar(fuentes[indice + 1].n)} />
            <Boton variante="fantasma" tamano="pequeno" icono={<X />} aria-label="Cerrar" onClick={onCerrar} />
          </div>
        </div>

        <div className="panel-fuente-cuerpo">
          <h3 className="panel-fuente-titulo">{f.titulo}</h3>
          {f.disponible !== false && (
            <div className="fila envolver mt-1">
              <Etiqueta tono={f.tipo === 'instruccion' ? 'amarilla' : f.tipo === 'faq' ? 'verde' : 'azul'}
                icono={f.tipo === 'instruccion' ? <ListChecks /> : <FileText />}>
                {nombreTipo(f.tipo)}
              </Etiqueta>
              {donde && <Etiqueta>{donde}</Etiqueta>}
            </div>
          )}

          {f.disponible === false ? (
            <div className="mt-2">
              <Aviso titulo="Ya no tienes acceso a esta fuente">
                El documento se ha retirado o ha cambiado quién puede verlo. Si lo necesitas, pregúntalo de nuevo
                o consúltalo con tu responsable.
              </Aviso>
            </div>
          ) : (
            <>
              {f.obsoleta && (
                <div className="mt-2">
                  <Aviso tono="amarillo" titulo="Versión sustituida">
                    Esta respuesta se basó en una versión anterior de la instrucción. Antes de aplicarlo, comprueba la
                    versión vigente.
                  </Aviso>
                </div>
              )}
              <div className="panel-fuente-fragmento">
                <Quote className="comillas" />
                <p className="pre">{f.fragmento}</p>
              </div>
            </>
          )}

          {(f.autor || f.validador) && (
            <div className="panel-fuente-personas">
              {f.autor && (
                <div className="fila">
                  <span className="icono-persona"><UserRound /></span>
                  <div><div className="diminuto apagado">Autoría</div><div className="negrita">{f.autor}</div></div>
                </div>
              )}
              {f.validador && (
                <div className="fila">
                  <span className="icono-persona verde"><BadgeCheck /></span>
                  <div><div className="diminuto apagado">Validado por</div><div className="negrita">{f.validador}</div></div>
                </div>
              )}
            </div>
          )}

          {typeof f.similitud === 'number' && (
            <div className="diminuto apagado mt-2">
              Parecido con tu pregunta: {Math.round(Math.max(0, Math.min(1, f.similitud)) * 100)} %
            </div>
          )}
        </div>

        {(f.url || enlace) && (
          <div className="panel-fuente-pie">
            {enlace && (
              <Link to={enlace.a} className="boton secundario">
                {enlace.icono} {enlace.texto}
              </Link>
            )}
            {f.url && (
              <a className="boton oscuro" href={urlServidor(f.url)} target="_blank" rel="noreferrer">
                <ExternalLink /> Abrir el documento
              </a>
            )}
          </div>
        )}
      </aside>
    </>
  )
}
