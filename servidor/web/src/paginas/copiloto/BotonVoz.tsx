// Botón «mantén pulsado para hablar»: graba mientras se mantiene pulsado (ratón, dedo o teclado),
// transcribe en el servidor (/api/voz/transcribir) y entrega el texto.
// Donde el navegador no deja usar el micrófono (http desde otro equipo), explica por qué y lleva a
// escribir la pregunta.

import { useEffect, useRef, useState } from 'react'
import { Loader2, Mic, MicOff } from 'lucide-react'
import { enviarFormulario } from '../../api'
import { useAvisarError, useAvisos, useGrabadora } from '../../ui'
import { motivoSinMicrofono } from '../planta/copiloto'

export default function BotonVoz({ onTexto, deshabilitado, grande, onSinMicrofono }: {
  onTexto: (texto: string) => void
  deshabilitado?: boolean
  grande?: boolean
  /** Se llama cuando no se puede grabar aquí (para llevar el foco a la caja de texto). */
  onSinMicrofono?: () => void
}) {
  const { grabando, error, empezar, parar } = useGrabadora()
  const [transcribiendo, setTranscribiendo] = useState(false)
  const [explicacion, setExplicacion] = useState(false)
  const pulsado = useRef(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const sinMicrofono = motivoSinMicrofono()

  useEffect(() => {
    if (error) avisar(error, 'error')
  }, [error, avisar])

  // La explicación se queda unos segundos a la vista y se va sola.
  useEffect(() => {
    if (!explicacion) return
    const t = setTimeout(() => setExplicacion(false), 9000)
    return () => clearTimeout(t)
  }, [explicacion])

  // Si se sale de la pantalla con el botón pulsado, se apaga el micrófono.
  useEffect(() => () => {
    if (pulsado.current) {
      pulsado.current = false
      void parar()
    }
  }, [parar])

  const pulsar = async () => {
    if (deshabilitado || transcribiendo || pulsado.current) return
    pulsado.current = true
    await empezar()
    // Si ya se ha soltado mientras el navegador pedía el micrófono, se descarta.
    if (!pulsado.current) await parar()
  }

  const soltar = async () => {
    if (!pulsado.current) return
    pulsado.current = false
    const audio = await parar()
    if (!audio) return
    setTranscribiendo(true)
    try {
      const datos = new FormData()
      datos.append('audio', audio, audio.type.includes('ogg') ? 'voz.ogg' : 'voz.webm')
      const r = await enviarFormulario<{ texto: string }>('/api/voz/transcribir', datos)
      if (r.texto.trim()) onTexto(r.texto.trim())
      else avisar('No te he entendido. Prueba otra vez, un poco más cerca del micrófono.', 'info')
    } catch (e) {
      avisarError(e)
    } finally {
      setTranscribiendo(false)
    }
  }

  if (sinMicrofono) {
    return (
      <div className="voz-envoltorio">
        {explicacion && (
          <div className="voz-globo voz-globo-aviso" role="status">
            <strong>El micrófono no está disponible aquí.</strong> {sinMicrofono}
          </div>
        )}
        <button
          type="button"
          className={`boton-microfono no-disponible ${grande ? 'grande' : ''}`}
          title="Micrófono no disponible en esta conexión"
          aria-label="Micrófono no disponible: escribe la pregunta"
          aria-expanded={explicacion}
          onClick={() => { setExplicacion((v) => !v); onSinMicrofono?.() }}
        >
          <MicOff />
        </button>
      </div>
    )
  }

  const titulo = transcribiendo ? 'Transcribiendo…' : grabando ? 'Suelta para enviar' : 'Mantén pulsado para hablar'
  return (
    <div className="voz-envoltorio">
      {(grabando || transcribiendo) && (
        <div className="voz-globo" role="status">
          {grabando ? <><span className="voz-onda" /> Te escucho… suelta para enviar</> : 'Transcribiendo tu pregunta…'}
        </div>
      )}
      <button
        type="button"
        className={`boton-microfono ${grabando ? 'grabando' : ''} ${grande ? 'grande' : ''}`}
        disabled={deshabilitado || transcribiendo}
        title={titulo}
        aria-label={titulo}
        aria-pressed={grabando}
        onPointerDown={(e) => {
          if (e.button !== 0) return
          e.preventDefault()
          e.currentTarget.setPointerCapture(e.pointerId)
          pulsar()
        }}
        onPointerUp={soltar}
        onPointerCancel={soltar}
        onContextMenu={(e) => e.preventDefault()}
        onKeyDown={(e) => {
          if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); pulsar() }
        }}
        onKeyUp={(e) => {
          if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); soltar() }
        }}
        onBlur={soltar}
      >
        {transcribiendo ? <Loader2 className="girando" /> : <Mic />}
      </button>
    </div>
  )
}
