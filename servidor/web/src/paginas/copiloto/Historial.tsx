// Historial de mis preguntas al copiloto: buscar y recuperar una conversación anterior.

import { useEffect, useState } from 'react'
import { BookOpen, CircleHelp, History, Search } from 'lucide-react'
import { get, hace } from '../../api'
import { Boton, Esqueleto, Etiqueta, Modal, Vacio, useAvisarError } from '../../ui'
import type { ConsultaGuardada, PaginaHistorial } from './tipos'

const POR_PAGINA = 15

export default function Historial({ abierto, onCerrar, onElegir }: {
  abierto: boolean
  onCerrar: () => void
  onElegir: (c: ConsultaGuardada) => void
}) {
  const [busqueda, setBusqueda] = useState('')
  // Filtro y página van juntos: cambiar el filtro siempre vuelve a la primera página.
  const [peticion, setPeticion] = useState({ filtro: '', pagina: 1 })
  const [elementos, setElementos] = useState<ConsultaGuardada[]>([])
  const [paginas, setPaginas] = useState(1)
  const [total, setTotal] = useState(0)
  const [cargando, setCargando] = useState(false)
  const avisarError = useAvisarError()

  // Búsqueda con una pequeña espera mientras se escribe.
  useEffect(() => {
    const t = setTimeout(() => setPeticion((p) => (p.filtro === busqueda.trim() ? p : { filtro: busqueda.trim(), pagina: 1 })), 300)
    return () => clearTimeout(t)
  }, [busqueda])

  // Cada vez que se abre, se empieza por las más recientes (si ya estaba en la primera página, la
  // carga la dispara el propio cambio de «abierto»: así no se pide dos veces).
  useEffect(() => {
    if (abierto) setPeticion((p) => (p.pagina === 1 ? p : { ...p, pagina: 1 }))
  }, [abierto])

  useEffect(() => {
    if (!abierto) return
    const ctl = new AbortController()
    const { filtro, pagina } = peticion
    setCargando(true)
    const q = filtro ? `&q=${encodeURIComponent(filtro)}` : ''
    get<PaginaHistorial>(`/api/consulta/historial?pagina=${pagina}&por_pagina=${POR_PAGINA}${q}`, ctl.signal)
      .then((d) => {
        setElementos((prev) => (pagina === 1 ? d.elementos : [...prev, ...d.elementos]))
        setPaginas(d.paginas)
        setTotal(d.total)
      })
      .catch((e) => { if (e?.name !== 'AbortError') avisarError(e) })
      .finally(() => { if (!ctl.signal.aborted) setCargando(false) })
    return () => ctl.abort()
  }, [abierto, peticion, avisarError])

  const { filtro, pagina } = peticion

  return (
    <Modal abierto={abierto} titulo="Tus preguntas anteriores" onCerrar={onCerrar} ancho>
      <div className="entrada-icono mb-2">
        <Search />
        <input className="entrada" placeholder="Buscar en tus preguntas…" value={busqueda} autoFocus
          onChange={(e) => setBusqueda(e.target.value)} />
      </div>
      {cargando && pagina === 1 ? (
        <div className="columna">
          {[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={54} />)}
        </div>
      ) : elementos.length === 0 ? (
        <Vacio icono={<History />} titulo={filtro ? 'No hay preguntas con ese texto' : 'Todavía no has preguntado nada'}>
          {filtro ? 'Prueba con otras palabras.' : 'Cuando hagas preguntas al copiloto, aparecerán aquí para que puedas retomarlas.'}
        </Vacio>
      ) : (
        <>
          <div className="diminuto apagado mb-1">{total === 1 ? '1 pregunta' : `${total} preguntas`}</div>
          <ul className="historial-lista">
            {elementos.map((c) => (
              <li key={c.id}>
                <button className="historial-elemento" onClick={() => onElegir(c)}>
                  <span className={`historial-icono ${c.con_respaldo ? 'con' : 'sin'}`}>
                    {c.con_respaldo ? <BookOpen /> : <CircleHelp />}
                  </span>
                  <span className="crece">
                    <span className="historial-pregunta">{c.pregunta}</span>
                    <span className="historial-detalle">
                      {hace(c.creada)}
                      {c.con_respaldo
                        ? ` · ${c.fuentes.length === 1 ? '1 fuente' : `${c.fuentes.length} fuentes`}`
                        : ' · sin respaldo en la documentación'}
                    </span>
                  </span>
                  {c.modo === 'socratico' && <Etiqueta tono="azul">Socrático</Etiqueta>}
                  {c.modo === 'planta' && <Etiqueta tono="amarilla">Planta</Etiqueta>}
                </button>
              </li>
            ))}
          </ul>
          {pagina < paginas && (
            <div className="centro mt-2">
              <Boton cargando={cargando} onClick={() => setPeticion((p) => ({ ...p, pagina: p.pagina + 1 }))}>Ver más</Boton>
            </div>
          )}
        </>
      )}
    </Modal>
  )
}
