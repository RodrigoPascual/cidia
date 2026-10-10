// Nota de voz «mantén pulsado para grabar», de hasta 2 minutos, con el tiempo a la vista.
// Al soltar se ofrece escucharla antes de enviarla y la opción de volver a grabar.
// La URL de la nota (URL.createObjectURL) la libera quien guarda la nota, no este componente:
// así se puede volver a escuchar aunque se cambie entre «Escribir» y «Nota de voz».

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { Mic, RotateCcw } from 'lucide-react'
import { Aviso, BarraProgreso, Boton, useGrabadora } from '../../ui'
import { mmss } from './tipos'

export const MAX_SEGUNDOS = 120

export interface Nota {
  blob: Blob
  url: string
  segundos: number
}

export function GrabadorNota({ nota, onCambio, compacto }: {
  nota: Nota | null; onCambio: (n: Nota | null) => void; compacto?: boolean
}) {
  const { grabando, error, empezar, parar } = useGrabadora()
  const [segundos, setSegundos] = useState(0)
  // Indicación breve bajo el botón cuando la grabación no ha servido (soltó antes de tiempo).
  const [pista, setPista] = useState<string | null>(null)
  const pulsado = useRef(false)
  const inicio = useRef(0)
  const soltarRef = useRef<() => void>(() => {})
  const sinMicro = typeof navigator !== 'undefined' && !navigator.mediaDevices

  async function pulsar() {
    if (pulsado.current || sinMicro) return
    pulsado.current = true
    inicio.current = 0
    setSegundos(0)
    setPista(null)
    const antes = Date.now()
    await empezar()
    inicio.current = Date.now()
    // Si soltó mientras se abría el micrófono (p. ej. con el aviso de permisos), se descarta.
    if (!pulsado.current) {
      await parar()
      if (Date.now() - antes > 400) setPista('Ya puedes grabar: mantén pulsado el botón mientras hablas.')
    }
  }

  async function soltar() {
    if (!pulsado.current) return
    pulsado.current = false
    const duracion = inicio.current ? (Date.now() - inicio.current) / 1000 : 0
    const blob = await parar()
    // Segundos enteros hacia abajo, como el reproductor (si no, «0:07» y el reproductor dice 0:06).
    if (blob) onCambio({ blob, url: URL.createObjectURL(blob), segundos: Math.max(1, Math.min(MAX_SEGUNDOS, Math.floor(duracion))) })
    else if (duracion > 0 && duracion < 1.5) setPista('Ha sido muy corta: mantén pulsado el botón mientras hablas.')
  }
  soltarRef.current = soltar

  // Si se sale de la página a mitad de una grabación, se apaga el micrófono (y se descarta).
  useEffect(() => () => {
    if (pulsado.current) {
      pulsado.current = false
      void parar()
    }
  }, [parar])

  // Reloj visible y corte automático a los 2 minutos.
  useEffect(() => {
    if (!grabando) return
    const t = setInterval(() => {
      const s = (Date.now() - inicio.current) / 1000
      setSegundos(s)
      if (s >= MAX_SEGUNDOS) soltarRef.current()
    }, 200)
    return () => clearInterval(t)
  }, [grabando])

  const alPulsar = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId) // sigue grabando aunque el dedo se mueva
    pulsar()
  }
  const alTecla = (e: KeyboardEvent<HTMLButtonElement>, abajo: boolean) => {
    if (e.key !== ' ' && e.key !== 'Enter') return
    e.preventDefault()
    if (abajo && !e.repeat) pulsar()
    if (!abajo) soltar()
  }

  if (nota && !grabando) {
    return (
      <div className="apo-nota-lista">
        <div className="apo-nota-icono"><Mic /></div>
        <div className="crece">
          <div className="negrita">Nota de voz de {mmss(nota.segundos)}</div>
          <audio controls src={nota.url} className="apo-audio-control" />
        </div>
        <Boton variante="secundario" tamano="pequeno" icono={<RotateCcw />} onClick={() => onCambio(null)}>
          Volver a grabar
        </Boton>
      </div>
    )
  }

  return (
    <div className={`apo-grabador ${compacto ? 'compacto' : ''} ${grabando ? 'grabando' : ''}`}>
      <button
        type="button"
        className={`boton-voz ${grabando ? 'grabando' : ''}`}
        aria-label={grabando ? 'Grabando: suelta para terminar' : 'Mantén pulsado para grabar una nota de voz'}
        disabled={sinMicro}
        onPointerDown={alPulsar}
        onPointerUp={() => soltar()}
        onPointerCancel={() => soltar()}
        onContextMenu={(e) => e.preventDefault()}
        onKeyDown={(e) => alTecla(e, true)}
        onKeyUp={(e) => alTecla(e, false)}
      >
        <Mic />
      </button>
      {grabando ? (
        <div className="apo-grabador-texto">
          <div className="apo-reloj"><span className="apo-punto-rojo" />{mmss(segundos)} <span className="apagado">/ {mmss(MAX_SEGUNDOS)}</span></div>
          <BarraProgreso valor={(segundos / MAX_SEGUNDOS) * 100} tono="amarilla" />
          <div className="pequeno apagado mt-1">Suelta para terminar</div>
        </div>
      ) : (
        <div className="apo-grabador-texto">
          <div className="negrita">Mantén pulsado para grabar</div>
          {pista && !error
            ? <div className="pequeno apo-pista" role="status">{pista}</div>
            : <div className="pequeno apagado">Una nota de voz de hasta 2 minutos, sin teclear</div>}
        </div>
      )}
      {(error || sinMicro) && (
        <div className="apo-grabador-error">
          <Aviso tono="alerta">
            {error ?? 'Este equipo no permite usar el micrófono desde aquí. Puedes escribirlo en su lugar.'}
          </Aviso>
        </div>
      )}
    </div>
  )
}
