// Tutor socrático compacto: no da la respuesta, ayuda a razonarla con preguntas.
// Usa el copiloto general (/api/consulta) con modo «socratico» y el contexto de la tarea.

import { useEffect, useRef, useState } from 'react'
import { RotateCcw, Send, Sparkles } from 'lucide-react'
import { Boton, Tarjeta } from '../../ui'
import { consumirRespuesta, idLocal, RESPUESTA_VACIA, type Respuesta } from '../planta/copiloto'
import { RespuestaCopiloto } from '../planta/Fuentes'

interface Turno {
  id: string
  pregunta: string
  respuesta: Respuesta
}

const SUGERENCIAS = [
  '¿Por qué los pasos van en este orden?',
  '¿Qué puede salir mal en el paso crítico?',
  'Hazme preguntas para comprobar si lo he entendido',
]

export function Tutor({ tareaId }: { tareaId: number }) {
  const [turnos, setTurnos] = useState<Turno[]>([])
  const [texto, setTexto] = useState('')
  const control = useRef<AbortController | null>(null)
  const lista = useRef<HTMLDivElement>(null)
  const ocupado = turnos.some((t) => !t.respuesta.terminado)

  useEffect(() => () => control.current?.abort(), [])
  const ultimo = turnos[turnos.length - 1]
  useEffect(() => {
    const el = lista.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turnos.length, ultimo?.respuesta.texto])

  function enviar(pregunta: string) {
    const p = pregunta.trim()
    if (!p || ocupado) return
    // Últimos turnos de la conversación para que el tutor siga el hilo (formato de /api/consulta).
    const historial = turnos.slice(-3).flatMap((t) => [
      { rol: 'usuario', texto: t.pregunta },
      ...(t.respuesta.texto ? [{ rol: 'asistente', texto: t.respuesta.texto }] : []),
    ])
    const id = idLocal()
    setTurnos((ts) => [...ts, { id, pregunta: p, respuesta: { ...RESPUESTA_VACIA } }])
    setTexto('')
    control.current = new AbortController()
    consumirRespuesta('/api/consulta', { pregunta: p, modo: 'socratico', contexto: { tarea_id: tareaId }, historial },
      (r) => setTurnos((ts) => ts.map((t) => (t.id === id ? { ...t, respuesta: r } : t))), control.current.signal)
  }

  function reiniciar() {
    control.current?.abort()
    setTurnos([])
  }

  return (
    <Tarjeta titulo="Tutor socrático" icono={<Sparkles size={18} />}
      acciones={turnos.length > 0 && (
        <Boton variante="fantasma" tamano="pequeno" icono={<RotateCcw />} onClick={reiniciar}>Empezar de nuevo</Boton>
      )}>
      <div className="tu">
        <div className="tu-mensajes" ref={lista} aria-live="polite">
          {turnos.length === 0 ? (
            <div>
              <div className="tu-intro">
                No te da la respuesta: te hace preguntas para que la razones tú. Así se aprende de verdad.
              </div>
              <div className="tu-sugerencias">
                {SUGERENCIAS.map((s) => (
                  <button key={s} type="button" className="tu-sugerencia" onClick={() => enviar(s)}>{s}</button>
                ))}
              </div>
            </div>
          ) : turnos.map((t) => (
            <div key={t.id} className="columna" style={{ gap: 8 }}>
              <div className="tu-yo">{t.pregunta}</div>
              <div className="tu-tutor"><RespuestaCopiloto respuesta={t.respuesta} pensando="Pensando una buena pregunta…" /></div>
            </div>
          ))}
        </div>
        <form className="tu-entrada" onSubmit={(e) => { e.preventDefault(); enviar(texto) }}>
          <textarea rows={1} value={texto} maxLength={2000} placeholder="Escribe tu duda o tu respuesta"
            aria-label="Mensaje para el tutor" onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(texto) } }} />
          <Boton variante="oscuro" type="submit" icono={<Send />} disabled={!texto.trim() || ocupado} aria-label="Enviar" />
        </form>
      </div>
    </Tarjeta>
  )
}
