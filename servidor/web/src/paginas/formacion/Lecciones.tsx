// Micro-lecciones de una tarea como tarjetas navegables, una a una, con pregunta de control y
// feedback inmediato. Primer fallo: se marca y se puede volver a intentar; segundo fallo: se
// muestra la respuesta correcta con su explicación. Lo decide el servidor, que no envía la
// respuesta correcta hasta entonces.

import { useState, type ReactNode } from 'react'
import { ArrowLeft, ArrowRight, Check, CheckCircle2, HelpCircle, Lightbulb, Award, X } from 'lucide-react'
import { post } from '../../api'
import { Aviso, Boton, Etiqueta, TextoFormato, useAvisarError } from '../../ui'
import type { Correccion, Leccion } from './tipos'

interface EstadoPregunta {
  fallidas: number[]
  acierto: boolean
  revelada: boolean
  correccion: Correccion | null
}

const LETRAS = 'ABCDEF'

function Pregunta({ leccion, estado, onResponder, enviando }: {
  leccion: Leccion; estado: EstadoPregunta | undefined; onResponder: (opcion: number) => void; enviando: boolean
}) {
  const p = leccion.pregunta!
  const e = estado ?? { fallidas: [], acierto: false, revelada: false, correccion: null }
  const cerrada = e.acierto || e.revelada
  const correcta = e.correccion?.opcion_correcta
  return (
    <div className="fl-pregunta">
      <div className="fl-pregunta-titulo"><HelpCircle /> Comprueba lo que has aprendido</div>
      <div className="fl-enunciado">{p.enunciado}</div>
      <div className="fl-opciones" role="group" aria-label="Opciones">
        {p.opciones.map((o, k) => {
          const fallida = e.fallidas.includes(k)
          const buena = cerrada && k === correcta
          const clase = buena ? 'correcta' : fallida ? 'incorrecta' : cerrada ? 'apagada' : ''
          return (
            <button key={k} type="button" className={`fl-opcion ${clase}`} disabled={cerrada || fallida || enviando}
              onClick={() => onResponder(k)}>
              <span className="letra">{LETRAS[k]}</span>
              <span>{o}</span>
              {buena && <Check className="marca" />}
              {fallida && <X className="marca" />}
            </button>
          )
        })}
      </div>
      <div className="fl-feedback" aria-live="polite">
        {e.acierto ? (
          <Aviso tono="exito" titulo="¡Correcto!">{e.correccion?.explicacion || 'Bien visto.'}</Aviso>
        ) : e.revelada ? (
          <Aviso tono="alerta" titulo={`La respuesta correcta es la ${LETRAS[correcta ?? 0]}`}>
            {e.correccion?.explicacion || 'Repasa el punto clave de esta micro-lección.'}
          </Aviso>
        ) : e.fallidas.length ? (
          <Aviso tono="amarillo" titulo="No es esa">Vuelve a leer el punto clave y prueba otra vez.</Aviso>
        ) : null}
      </div>
    </div>
  )
}

export function Lecciones({ lecciones, onVista, alTerminar }: {
  lecciones: Leccion[]
  onVista: (id: number) => Promise<void>
  alTerminar: ReactNode
}) {
  const avisarError = useAvisarError()
  const primera = lecciones.findIndex((l) => !l.vista)
  const [indice, setIndice] = useState(primera >= 0 ? primera : 0)
  const [terminado, setTerminado] = useState(false)
  const [preguntas, setPreguntas] = useState<Record<number, EstadoPregunta>>({})
  const [enviando, setEnviando] = useState(false)
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())

  const total = lecciones.length
  const i = Math.min(indice, total - 1)
  const l = lecciones[i]
  const vista = (x: Leccion) => x.vista || marcadas.has(x.id)

  async function marcar(x: Leccion) {
    if (vista(x)) return
    setMarcadas((m) => new Set(m).add(x.id))
    try {
      await onVista(x.id)
    } catch (e) {
      // No se ha guardado: deja de verse como vista para que cuente al volver a abrirla.
      setMarcadas((m) => { const n = new Set(m); n.delete(x.id); return n })
      avisarError(e)
    }
  }

  async function responder(opcion: number) {
    setEnviando(true)
    try {
      const c = await post<Correccion>(`/api/formacion/microlecciones/${l.id}/responder`, { opcion })
      setPreguntas((ps) => {
        const previo = ps[l.id] ?? { fallidas: [], acierto: false, revelada: false, correccion: null }
        const fallidas = c.correcta ? previo.fallidas : [...previo.fallidas, opcion]
        return { ...ps, [l.id]: { fallidas, acierto: c.correcta, revelada: !c.correcta && c.revelada, correccion: c } }
      })
      marcar(l)
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
    }
  }

  function siguiente() {
    marcar(l)
    if (i < total - 1) setIndice(i + 1)
    else setTerminado(true)
  }

  if (terminado) {
    return (
      <div className="tarjeta fl-fin">
        <div className="icono"><Award /></div>
        <h2>Has repasado todas las micro-lecciones</h2>
        <p className="apagado mt-1">Ahora toca demostrarlo: el cuestionario y la práctica en el modo planta.</p>
        <div className="fila envolver mt-2" style={{ justifyContent: 'center' }}>
          {alTerminar}
          <Boton variante="fantasma" icono={<ArrowLeft />} onClick={() => { setTerminado(false); setIndice(0) }}>Repasar desde el principio</Boton>
        </div>
      </div>
    )
  }

  return (
    <div className="tarjeta fl-leccion">
      <div className="fl-cabecera">
        <span className="fl-num">Micro-lección {i + 1} de {total}</span>
        <div className="fl-puntos">
          {lecciones.map((x, j) => (
            <button key={x.id} type="button" className={`fl-punto ${vista(x) ? 'vista' : ''} ${j === i ? 'actual' : ''}`}
              onClick={() => setIndice(j)} aria-label={`Micro-lección ${j + 1}${vista(x) ? ', vista' : ''}`} title={x.titulo} />
          ))}
        </div>
      </div>
      <div className="fl-cuerpo" key={l.id}>
        <h2>
          {l.titulo}
          {vista(l) && <Etiqueta tono="verde" icono={<CheckCircle2 />}>Vista</Etiqueta>}
        </h2>
        <TextoFormato texto={l.contenido} />
        {l.punto_clave && (
          <div className="fl-clave">
            <Lightbulb />
            <div><strong>Punto clave</strong>{l.punto_clave}</div>
          </div>
        )}
        {l.pregunta && <Pregunta leccion={l} estado={preguntas[l.id]} onResponder={responder} enviando={enviando} />}
      </div>
      <div className="fl-pie">
        <Boton variante="fantasma" icono={<ArrowLeft />} disabled={i === 0} onClick={() => setIndice(i - 1)}>Anterior</Boton>
        <Boton variante="primario" icono={i === total - 1 ? <Check /> : <ArrowRight />} onClick={siguiente}>
          {i === total - 1 ? 'Terminar' : 'Siguiente'}
        </Boton>
      </div>
    </div>
  )
}
