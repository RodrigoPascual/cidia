// «Mis cuestionarios»: los cuestionarios de las tareas del itinerario, pendientes primero.

import { CheckCircle2, ClipboardCheck, ClipboardList, Play, RefreshCw, RotateCcw } from 'lucide-react'
import { fecha } from '../../api'
import { Boton, Etiqueta, Iluo, Tarjeta, Vacio } from '../../ui'
import type { CuestionarioDisponible } from './tipos'

function TarjetaCuestionario({ c, onEmpezar }: { c: CuestionarioDisponible; onEmpezar: () => void }) {
  const estado = c.requiere_reevaluacion
    ? <Etiqueta tono="naranja" icono={<RefreshCw />}>Reevaluación</Etiqueta>
    : c.aprobado
      ? <Etiqueta tono="verde" icono={<CheckCircle2 />}>Aprobado</Etiqueta>
      : <Etiqueta tono="amarilla">Pendiente</Etiqueta>
  return (
    <Tarjeta className={`ev-cuestionario ${c.pendiente ? 'pendiente' : ''}`}>
      <div className="fila arriba" style={{ gap: 12 }}>
        <div className="ev-cuestionario-icono"><ClipboardCheck /></div>
        <div className="crece" style={{ minWidth: 0 }}>
          <div className="diminuto apagado recortar">{[c.codigo, `v${c.version}`, c.puesto].filter(Boolean).join(' · ')}</div>
          <div className="negrita">{c.tarea}</div>
        </div>
        <Iluo nivel={c.nivel} tamano={26} />
      </div>
      <div className="fila envolver mt-2" style={{ gap: 6 }}>
        {estado}
        <Etiqueta>{c.preguntas} {c.preguntas === 1 ? 'pregunta' : 'preguntas'}</Etiqueta>
      </div>
      <div className="diminuto apagado mt-1">
        {c.ultimo
          ? <>Último intento el {fecha(c.ultimo.fecha)}: {Math.round(c.ultimo.puntuacion * 100)} %{c.ultimo.aprobado ? ' (aprobado)' : ''}</>
          : 'Aún no lo has intentado.'}
        {c.requiere_reevaluacion && ' Hay una versión nueva de la instrucción.'}
        {!c.requiere_reevaluacion && c.aprobado_caducado && ' Tu último aprobado ya no está vigente: vuelve a hacerlo para renovar tu nivel.'}
      </div>
      <div className="mt-2">
        <Boton bloque variante={c.pendiente ? 'primario' : 'secundario'} icono={c.intentos ? <RotateCcw /> : <Play />} onClick={onEmpezar}>
          {c.pendiente ? (c.intentos ? 'Volver a intentarlo' : 'Empezar') : 'Repasar'}
        </Boton>
      </div>
    </Tarjeta>
  )
}

export default function MisCuestionarios({ cuestionarios, onEmpezar }: {
  cuestionarios: CuestionarioDisponible[]; onEmpezar: (tareaId: number) => void
}) {
  if (!cuestionarios.length) {
    return (
      <Tarjeta>
        <Vacio icono={<ClipboardList />} titulo="No tienes cuestionarios disponibles">
          Aparecen cuando un experto aprueba las preguntas de las tareas de tu itinerario. Mientras tanto, puedes avanzar
          con la formación y practicar en modo planta.
        </Vacio>
      </Tarjeta>
    )
  }
  const pendientes = cuestionarios.filter((c) => c.pendiente)
  const hechos = cuestionarios.filter((c) => !c.pendiente)
  return (
    <div className="columna" style={{ gap: 22 }}>
      {pendientes.length > 0 && (
        <section>
          <h3 className="ev-seccion">Pendientes <span className="apagado">· {pendientes.length}</span></h3>
          <div className="rejilla auto">
            {pendientes.map((c) => <TarjetaCuestionario key={c.tarea_id} c={c} onEmpezar={() => onEmpezar(c.tarea_id)} />)}
          </div>
        </section>
      )}
      {hechos.length > 0 && (
        <section>
          <h3 className="ev-seccion">Aprobados <span className="apagado">· {hechos.length}</span></h3>
          <div className="rejilla auto">
            {hechos.map((c) => <TarjetaCuestionario key={c.tarea_id} c={c} onEmpezar={() => onEmpezar(c.tarea_id)} />)}
          </div>
        </section>
      )}
    </div>
  )
}
