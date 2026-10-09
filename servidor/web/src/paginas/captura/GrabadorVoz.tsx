// Grabación de voz con el tiempo y el nivel del micrófono a la vista. Se pulsa para empezar y
// otra vez para terminar (las notas y respuestas pueden durar varios minutos).

import { useCallback, useEffect, useRef, useState } from 'react'
import { Mic, Square } from 'lucide-react'
import { Aviso, Boton, useAvisos, useGrabadora } from '../../ui'
import { mmss } from './tipos'

const BARRAS = 32

// En iPhone y iPad, abrir el micrófono por segunda vez (para el medidor) puede silenciar la pista
// que está grabando useGrabadora. Allí se graba sin medidor.
const MICRO_UNICO = typeof navigator !== 'undefined'
  && (/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1))

/** Nivel del micrófono (0..1) mientras `activo`, con un historial corto para dibujar barras. */
export function useNivelMicro(activo: boolean, barras = BARRAS) {
  const [niveles, setNiveles] = useState<number[]>(() => Array(barras).fill(0))
  useEffect(() => {
    if (!activo || MICRO_UNICO) {
      setNiveles(Array(barras).fill(0))
      return
    }
    let vivo = true
    let flujo: MediaStream | null = null
    let ctx: AudioContext | null = null
    let marco = 0
    let ultimo = 0
    const historial: number[] = Array(barras).fill(0)
    navigator.mediaDevices?.getUserMedia({ audio: true })
      .then((f) => {
        if (!vivo) {
          f.getTracks().forEach((t) => t.stop())
          return
        }
        flujo = f
        ctx = new AudioContext()
        const analizador = ctx.createAnalyser()
        analizador.fftSize = 1024
        ctx.createMediaStreamSource(f).connect(analizador)
        const muestras = new Uint8Array(analizador.fftSize)
        const medir = (t: number) => {
          if (!vivo) return
          analizador.getByteTimeDomainData(muestras)
          let suma = 0
          for (const v of muestras) {
            const x = (v - 128) / 128
            suma += x * x
          }
          // RMS amplificado: la voz normal llena la mitad de la barra.
          const nivel = Math.min(1, Math.sqrt(suma / muestras.length) * 5)
          if (t - ultimo > 70) {
            ultimo = t
            historial.push(nivel)
            historial.shift()
            setNiveles([...historial])
          }
          marco = requestAnimationFrame(medir)
        }
        marco = requestAnimationFrame(medir)
      })
      .catch(() => { /* sin medidor: la grabación sigue funcionando */ })
    return () => {
      vivo = false
      cancelAnimationFrame(marco)
      flujo?.getTracks().forEach((t) => t.stop())
      ctx?.close().catch(() => {})
    }
  }, [activo, barras])
  return niveles
}

/** Segundos transcurridos desde que `activo` pasó a verdadero. */
export function useCronometro(activo: boolean) {
  const [segundos, setSegundos] = useState(0)
  useEffect(() => {
    if (!activo) return
    const inicio = Date.now()
    setSegundos(0)
    const t = setInterval(() => setSegundos((Date.now() - inicio) / 1000), 250)
    return () => clearInterval(t)
  }, [activo])
  return segundos
}

export function MedidorNivel({ niveles, alto = 34 }: { niveles: number[]; alto?: number }) {
  return (
    <div className="cap-nivel" style={{ height: alto }} aria-hidden="true">
      {niveles.map((n, i) => <span key={i} style={{ height: `${Math.max(8, n * 100)}%` }} />)}
    </div>
  )
}

export default function GrabadorVoz({ onAudio, ocupado, compacto, maxSegundos = 600, ayuda }: {
  onAudio: (audio: Blob, segundos: number) => void
  ocupado?: boolean
  compacto?: boolean
  maxSegundos?: number
  ayuda?: string
}) {
  const { grabando, error, empezar, parar } = useGrabadora()
  const segundos = useCronometro(grabando)
  const niveles = useNivelMicro(grabando, compacto ? 14 : BARRAS)
  const avisar = useAvisos()
  const sinMicro = typeof navigator === 'undefined' || !navigator.mediaDevices
  const duracion = useRef(0)
  duracion.current = segundos

  const terminar = useCallback(async () => {
    const s = duracion.current
    const audio = await parar()
    if (audio) onAudio(audio, s)
    else avisar('La grabación ha sido demasiado corta.', 'info')
  }, [parar, onAudio, avisar])

  // Corte automático al llegar al máximo.
  useEffect(() => {
    if (grabando && segundos >= maxSegundos) terminar()
  }, [grabando, segundos, maxSegundos, terminar])

  const alternar = () => (grabando ? terminar() : empezar())
  const fallo = error ?? (sinMicro ? 'Este equipo no permite usar el micrófono desde aquí.' : null)

  if (compacto) {
    return grabando ? (
      <div className="cap-grabando-compacto" role="status">
        <span className="cap-punto-rojo" />
        <span className="mono">{mmss(segundos)}</span>
        <MedidorNivel niveles={niveles} alto={22} />
        <Boton variante="peligro" tamano="pequeno" icono={<Square />} onClick={terminar}>Parar y enviar</Boton>
      </div>
    ) : (
      <Boton variante="fantasma" icono={<Mic />} onClick={alternar} disabled={ocupado || sinMicro}
        title={fallo ?? 'Responder por voz'} aria-label="Responder por voz" />
    )
  }

  return (
    <div className={`cap-grabador ${grabando ? 'grabando' : ''}`}>
      <button type="button" className={`boton-voz ${grabando ? 'grabando' : ''}`} onClick={alternar}
        disabled={ocupado || sinMicro} aria-label={grabando ? 'Terminar la grabación' : 'Empezar a grabar'}>
        {grabando ? <Square /> : <Mic />}
      </button>
      {grabando ? (
        <div className="cap-grabador-estado">
          <div className="cap-reloj"><span className="cap-punto-rojo" />{mmss(segundos)}
            <span className="apagado pequeno"> / {mmss(maxSegundos)}</span></div>
          <MedidorNivel niveles={niveles} />
          <div className="pequeno apagado">Pulsa otra vez para terminar</div>
        </div>
      ) : (
        <div className="cap-grabador-estado">
          <div className="negrita">Pulsa para grabar</div>
          <div className="pequeno apagado">{ayuda ?? `Hasta ${Math.round(maxSegundos / 60)} minutos.`}</div>
        </div>
      )}
      {fallo && <Aviso tono="alerta">{fallo}</Aviso>}
    </div>
  )
}
