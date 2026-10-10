// Panel del copiloto en el modo planta: respuestas del paso actual con sus citas, botón de
// micrófono «mantén pulsado para preguntar» y caja de texto. Donde el navegador no deja usar el
// micrófono (http desde otro equipo) se explica por qué y se ofrece escribir la pregunta.

import { Fragment, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { Bot, Loader2, MessageCircleQuestion, Mic, MicOff, Send } from 'lucide-react'
import { Aviso, Boton, Etiqueta, useAvisarError, useAvisos, useGrabadora } from '../../ui'
import { motivoSinMicrofono, transcribir, type Respuesta } from './copiloto'
import { RespuestaCopiloto } from './Fuentes'

export interface Mensaje {
  id: string
  pasoId: number | null
  pregunta: string
  respuesta: Respuesta
}

export function PanelCopiloto({ numero, mensajes, soloLectura, onPreguntar }: {
  numero: number
  mensajes: Mensaje[]
  soloLectura: boolean
  onPreguntar: (texto: string) => void
}) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { grabando, error: errorMicro, empezar, parar } = useGrabadora()
  const [texto, setTexto] = useState('')
  const [transcribiendo, setTranscribiendo] = useState(false)
  const pulsado = useRef(false)
  const lista = useRef<HTMLDivElement>(null)
  const entrada = useRef<HTMLInputElement>(null)
  const sinMicrofono = motivoSinMicrofono()

  // Siempre a la vista la última respuesta (también mientras llega en streaming).
  const ultimo = mensajes[mensajes.length - 1]
  useEffect(() => {
    const el = lista.current
    if (el) el.scrollTop = el.scrollHeight
  }, [mensajes.length, ultimo?.respuesta.texto])

  async function soltar() {
    pulsado.current = false
    const audio = await parar()
    if (!audio) return
    setTranscribiendo(true)
    let pregunta = ''
    try {
      pregunta = await transcribir(audio)
    } catch (e) {
      avisarError(e)
      return
    } finally {
      setTranscribiendo(false)
    }
    if (pregunta) onPreguntar(pregunta)
    else avisar('No he entendido la pregunta. Habla más cerca del micrófono y prueba otra vez.', 'info')
  }

  async function pulsar() {
    if (soloLectura || transcribiendo || pulsado.current) return
    pulsado.current = true
    await empezar()
    if (!pulsado.current) await soltar() // se soltó antes de que el micrófono arrancara
  }

  const alPulsar = (e: PointerEvent<HTMLButtonElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    pulsar()
  }
  const teclaAbajo = (e: KeyboardEvent<HTMLButtonElement>) => {
    if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); pulsar() }
  }
  const teclaArriba = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); soltar() }
  }

  function enviar() {
    const t = texto.trim()
    if (!t) return
    onPreguntar(t)
    setTexto('')
  }

  return (
    <div className="ej-copiloto">
      <div className="ej-copiloto-cabecera">
        <div className="icono"><Bot /></div>
        <div className="crece">
          <div className="negrita">Copiloto</div>
          <div className="pequeno apagado">Responde con la instrucción, en el contexto del paso {numero}</div>
        </div>
        {mensajes.length > 0 && (
          <Etiqueta>{mensajes.length} {mensajes.length === 1 ? 'pregunta' : 'preguntas'}</Etiqueta>
        )}
      </div>

      <div className="ej-mensajes" ref={lista} aria-live="polite">
        {mensajes.length === 0 ? (
          <div className="ej-copiloto-vacio">
            <MessageCircleQuestion />
            <div className="negrita">{soloLectura ? 'Sin preguntas en este paso' : '¿Dudas en este paso?'}</div>
            {!soloLectura && (
              <div className="pequeno">Mantén pulsado el micrófono y pregunta en voz alta, o escríbelo abajo.</div>
            )}
          </div>
        ) : mensajes.map((m) => (
          <Fragment key={m.id}>
            <div className="ej-pregunta">{m.pregunta}</div>
            <div className="ej-respuesta"><RespuestaCopiloto respuesta={m.respuesta} pensando="Buscando en la instrucción…" /></div>
          </Fragment>
        ))}
      </div>

      {!soloLectura && (
        <div className="ej-voz">
          {errorMicro && <Aviso tono="alerta">{errorMicro}</Aviso>}
          {sinMicrofono ? (
            <div className="ej-voz-fila">
              <button type="button" className="boton-voz no-disponible" onClick={() => entrada.current?.focus()}
                aria-label="Micrófono no disponible: escribe la pregunta" title="Micrófono no disponible en esta conexión">
                <MicOff />
              </button>
              <div className="ej-voz-ayuda"><strong>El micrófono no está disponible aquí</strong>{sinMicrofono}</div>
            </div>
          ) : (
            <div className="ej-voz-fila">
              <button
                type="button"
                className={`boton-voz ${grabando ? 'grabando' : ''}`}
                disabled={transcribiendo}
                aria-label="Mantén pulsado para preguntar"
                aria-pressed={grabando}
                onPointerDown={alPulsar}
                onPointerUp={soltar}
                onPointerCancel={soltar}
                onKeyDown={teclaAbajo}
                onKeyUp={teclaArriba}
                onContextMenu={(e) => e.preventDefault()}
              >
                {transcribiendo ? <Loader2 className="girando" /> : <Mic />}
              </button>
              <div className="ej-voz-ayuda">
                {grabando ? (
                  <><strong>Te escucho…</strong>Suelta para enviar la pregunta.</>
                ) : transcribiendo ? (
                  <><strong>Transcribiendo…</strong>Un momento.</>
                ) : (
                  <><strong>Mantén pulsado para preguntar</strong>Habla con normalidad. La respuesta cita la instrucción y el paso.</>
                )}
              </div>
            </div>
          )}
          <form className="ej-escribir" onSubmit={(e) => { e.preventDefault(); enviar() }}>
            <input ref={entrada} className="entrada" placeholder={sinMicrofono ? 'Escribe tu pregunta' : 'O escribe tu pregunta'}
              value={texto} maxLength={2000}
              onChange={(e) => setTexto(e.target.value)} aria-label="Pregunta para el copiloto" />
            <Boton variante="oscuro" type="submit" icono={<Send />} disabled={!texto.trim()} aria-label="Enviar pregunta" />
          </form>
        </div>
      )}
    </div>
  )
}
