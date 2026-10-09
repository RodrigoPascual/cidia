// Cuestionario de una tarea: presentación, una pregunta por pantalla con su progreso y
// resultado con la explicación de cada fallo y el siguiente paso. Se corrige en el servidor.

import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ArrowRight, CheckCircle2, ClipboardCheck, RotateCcw, Send, ShieldAlert, TrendingUp, XCircle,
} from 'lucide-react'
import { ErrorApi, get, post } from '../../api'
import {
  Aviso, BarraProgreso, Boton, Cargando, ErrorCarga, Etiqueta, Iluo, Tarjeta, useAvisarError, useAvisos, useConfirmar,
  useDatos,
} from '../../ui'
import { LETRAS_OPCION, type Cuestionario as TCuestionario, type ResultadoCuestionario } from './tipos'

function Resultado({ r, tareaId, onRepetir, onSalir }: {
  r: ResultadoCuestionario; tareaId: number; onRepetir: () => void; onSalir: () => void
}) {
  const navegar = useNavigate()
  const [verAciertos, setVerAciertos] = useState(false)
  const fallos = r.correccion.filter((c) => !c.acierto)
  const aciertos = r.correccion.filter((c) => c.acierto)
  const pct = Math.round(r.puntuacion * 100)
  return (
    <div className="ev-estrecho columna" style={{ gap: 16 }}>
      <Tarjeta>
        <div className="ev-resultado">
          <div className={`ev-nota ${r.aprobado ? 'aprobado' : 'suspenso'}`} style={{ ['--pct' as string]: `${pct}%` }}>
            <div><strong>{pct} %</strong><span>{r.aciertos} de {r.total}</span></div>
          </div>
          <div className="crece">
            <h2 className="fila" style={{ gap: 8 }}>
              {r.aprobado ? <CheckCircle2 color="var(--verde)" /> : <XCircle color="var(--alerta)" />}
              {r.aprobado ? '¡Cuestionario aprobado!' : 'Todavía no lo has superado'}
            </h2>
            <p className="apagado mt-1">
              Has acertado {r.aciertos} de {r.total} preguntas. Para aprobar hace falta un {Math.round(r.umbral * 100)} %.
              {!r.aprobado && ' Repasa los fallos y vuelve a intentarlo cuando quieras.'}
            </p>
          </div>
        </div>
        {r.nivel.subio && (
          <Aviso tono="exito" titulo={`Has subido al nivel ${r.nivel.letra}`}>
            <span className="fila" style={{ gap: 10 }}><Iluo nivel={r.nivel.nivel} tamano={26} /> {r.nivel.nombre}</span>
          </Aviso>
        )}
        {r.siguiente && (
          <div className="ev-siguiente mt-2">
            <TrendingUp size={18} />
            <div><div className="negrita pequeno">Siguiente paso</div><div className="pequeno">{r.siguiente}</div></div>
          </div>
        )}
        <div className="fila envolver mt-2" style={{ gap: 8 }}>
          {!r.aprobado && <Boton variante="primario" icono={<RotateCcw />} onClick={onRepetir}>Repetir el cuestionario</Boton>}
          <Boton icono={<TrendingUp />} onClick={() => navegar(`/progreso?tarea=${tareaId}`)}>Ver mi progreso</Boton>
          <Boton variante="fantasma" onClick={onSalir}>Volver a mis cuestionarios</Boton>
        </div>
      </Tarjeta>

      <Tarjeta titulo={fallos.length ? `Fallos (${fallos.length})` : 'Sin fallos'}
        icono={fallos.length ? <XCircle size={18} color="var(--alerta)" /> : <CheckCircle2 size={18} color="var(--verde)" />}>
        {fallos.length === 0 ? (
          <div className="pequeno apagado">Has respondido bien todas las preguntas.</div>
        ) : (
          <div className="columna" style={{ gap: 14 }}>
            {fallos.map((c) => (
              <div key={c.id} className="ev-fallo">
                {c.paso && <div className="diminuto apagado mb-1">Paso {c.paso.orden} · {c.paso.titulo}{c.paso.es_critico ? ' · crítico' : ''}</div>}
                <div className="negrita">{c.enunciado}</div>
                <div className="ev-respuesta mal">
                  <XCircle size={15} />
                  {c.elegida === null || c.elegida === undefined ? 'Sin responder' : <>Tu respuesta: {c.opciones[c.elegida]}</>}
                </div>
                <div className="ev-respuesta bien"><CheckCircle2 size={15} /> Correcta: {c.opciones[c.correcta]}</div>
                {c.explicacion && <div className="pequeno apagado mt-1">{c.explicacion}</div>}
              </div>
            ))}
          </div>
        )}
        {aciertos.length > 0 && (
          <>
            <Boton variante="fantasma" tamano="pequeno" className="mt-2" onClick={() => setVerAciertos(!verAciertos)}>
              {verAciertos ? 'Ocultar las acertadas' : `Ver también las acertadas (${aciertos.length})`}
            </Boton>
            {verAciertos && (
              <div className="columna mt-1" style={{ gap: 8 }}>
                {aciertos.map((c) => (
                  <div key={c.id} className="ev-acierto">
                    <CheckCircle2 size={15} />
                    <div><div className="pequeno negrita">{c.enunciado}</div><div className="diminuto apagado">{c.opciones[c.correcta]}</div></div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Tarjeta>
    </div>
  )
}

export default function Cuestionario({ tareaId, onSalir }: { tareaId: number; onSalir: (cambios: boolean) => void }) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const [vuelta, setVuelta] = useState(0)
  const { datos: q, error, cargando, recargar } = useDatos(
    (s) => get<TCuestionario>(`/api/evaluacion/cuestionario/${tareaId}`, s), [tareaId, vuelta])
  const [fase, setFase] = useState<'intro' | 'preguntas' | 'resultado'>('intro')
  const [indice, setIndice] = useState(0)
  // {pregunta_id: clave opaca de la opción elegida}
  const [respuestas, setRespuestas] = useState<Record<number, string>>({})
  const [enviando, setEnviando] = useState(false)
  const [resultado, setResultado] = useState<ResultadoCuestionario | null>(null)

  const total = q?.preguntas.length ?? 0
  const actual = q?.preguntas[indice]
  const respondidas = Object.keys(respuestas).length

  const elegir = useCallback((clave: string) => {
    if (actual) setRespuestas((r) => ({ ...r, [actual.id]: clave }))
  }, [actual])

  async function entregar() {
    if (!q) return
    const faltan = total - respondidas
    if (faltan > 0) {
      const ok = await confirmar('Entregar el cuestionario',
        `Te ${faltan === 1 ? 'queda 1 pregunta' : `quedan ${faltan} preguntas`} sin responder y contarán como fallo. ¿Entregar igualmente?`)
      if (!ok) return
    }
    setEnviando(true)
    try {
      const r = await post<ResultadoCuestionario>(`/api/evaluacion/cuestionario/${tareaId}/responder`,
        { instruccion_id: q.instruccion.id, respuestas })
      setResultado(r)
      setFase('resultado')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 409) {
        // Se publicó una versión nueva mientras respondía: se carga el cuestionario nuevo.
        avisar(e.message, 'info')
        setRespuestas({})
        setIndice(0)
        setFase('intro')
        setVuelta((v) => v + 1)
      } else {
        avisarError(e)
      }
    } finally {
      setEnviando(false)
    }
  }

  const siguiente = useCallback(() => {
    if (indice < total - 1) setIndice((i) => i + 1)
  }, [indice, total])

  // Teclado: 1-4 o A-D eligen opción; Intro o flecha derecha pasan; flecha izquierda vuelve.
  useEffect(() => {
    if (fase !== 'preguntas' || !actual) return
    const tecla = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement || e.ctrlKey || e.metaKey) return
      if (document.querySelector('.velo')) return  // con un diálogo abierto, el teclado es suyo
      const k = e.key.toUpperCase()
      const pos = /^[1-6]$/.test(k) ? Number(k) - 1 : LETRAS_OPCION.indexOf(k)
      if (pos >= 0 && pos < actual.opciones.length) elegir(actual.opciones[pos].clave)
      else if ((e.key === 'Enter' || e.key === 'ArrowRight') && respuestas[actual.id] !== undefined) siguiente()
      else if (e.key === 'ArrowLeft') setIndice((i) => Math.max(0, i - 1))
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [fase, actual, respuestas, elegir, siguiente])

  async function salir() {
    if (fase === 'preguntas' && respondidas > 0) {
      const ok = await confirmar('Salir del cuestionario', 'Perderás las respuestas de este intento. ¿Salir?', true)
      if (!ok) return
    }
    onSalir(fase === 'resultado')
  }

  function repetir() {
    setRespuestas({})
    setIndice(0)
    setResultado(null)
    setFase('preguntas')
    setVuelta((v) => v + 1)  // nuevo orden aleatorio
  }

  if (error) {
    return (
      <Tarjeta>
        <ErrorCarga error={error} reintentar={recargar} />
        <div className="centro mb-2"><Boton variante="fantasma" icono={<ArrowLeft />} onClick={() => onSalir(false)}>Volver</Boton></div>
      </Tarjeta>
    )
  }
  if (fase === 'resultado' && resultado) {
    return <Resultado r={resultado} tareaId={tareaId} onRepetir={repetir} onSalir={() => onSalir(true)} />
  }
  if (!q || cargando) return <Tarjeta><Cargando texto="Preparando el cuestionario…" /></Tarjeta>

  if (fase === 'intro') {
    return (
      <div className="ev-estrecho">
        <Tarjeta>
          <div className="ev-intro">
            <div className="ev-intro-icono"><ClipboardCheck /></div>
            <div className="diminuto apagado">{[q.instruccion.codigo, `versión ${q.instruccion.version}`].filter(Boolean).join(' · ')}</div>
            <h2>{q.tarea.nombre}</h2>
            <p className="apagado">
              {total} {total === 1 ? 'pregunta' : 'preguntas'} sobre los pasos de la instrucción, sobre todo los críticos.
              Para aprobar necesitas un {Math.round(q.umbral * 100)} % de aciertos.
            </p>
            {q.intentos_previos > 0 && (
              <div className="pequeno apagado">Ya lo has intentado {q.intentos_previos} {q.intentos_previos === 1 ? 'vez' : 'veces'}. Las preguntas salen en otro orden.</div>
            )}
            <div className="fila envolver mt-2" style={{ gap: 8, justifyContent: 'center' }}>
              <Boton variante="primario" tamano="grande" icono={<ArrowRight />} onClick={() => setFase('preguntas')}>Empezar</Boton>
              <Boton tamano="grande" variante="fantasma" onClick={() => onSalir(false)}>Ahora no</Boton>
            </div>
          </div>
        </Tarjeta>
      </div>
    )
  }

  if (!actual) return null
  const elegida = respuestas[actual.id]
  const ultima = indice === total - 1
  return (
    <div className="ev-estrecho">
      <div className="fila entre mb-1">
        <span className="pequeno apagado"><strong className="ev-tinta">{q.tarea.nombre}</strong> · pregunta {indice + 1} de {total}</span>
        <Boton variante="fantasma" tamano="pequeno" onClick={salir}>Salir</Boton>
      </div>
      <BarraProgreso valor={((indice + (elegida !== undefined ? 1 : 0)) / total) * 100} tono="amarilla" />
      <Tarjeta className="ev-pregunta mt-2">
        {actual.paso && (
          <div className="fila mb-1" style={{ gap: 6 }}>
            <Etiqueta tono={actual.paso.es_critico ? 'roja' : undefined} icono={actual.paso.es_critico ? <ShieldAlert /> : undefined}>
              Paso {actual.paso.orden}{actual.paso.es_critico ? ' · crítico' : ''}
            </Etiqueta>
          </div>
        )}
        <h2 className="ev-enunciado">{actual.enunciado}</h2>
        <div className="ev-opciones" role="radiogroup" aria-label="Opciones">
          {actual.opciones.map((o, pos) => (
            <button key={o.clave} role="radio" aria-checked={elegida === o.clave}
              className={`ev-opcion ${elegida === o.clave ? 'elegida' : ''}`} onClick={() => elegir(o.clave)}>
              <span className="ev-letra">{LETRAS_OPCION[pos]}</span>
              <span>{o.texto}</span>
            </button>
          ))}
        </div>
      </Tarjeta>
      <div className="fila entre mt-2">
        <Boton icono={<ArrowLeft />} disabled={indice === 0} onClick={() => setIndice((i) => i - 1)}>Anterior</Boton>
        <span className="diminuto apagado ev-ocultar-movil">Puedes responder con las teclas 1 a {actual.opciones.length}</span>
        {ultima ? (
          <Boton variante="verde" tamano="grande" icono={<Send />} cargando={enviando} onClick={entregar}>Entregar</Boton>
        ) : (
          <Boton variante="primario" tamano="grande" icono={<ArrowRight />} disabled={elegida === undefined} onClick={siguiente}>
            Siguiente
          </Boton>
        )}
      </div>
      {dialogo}
    </div>
  )
}
