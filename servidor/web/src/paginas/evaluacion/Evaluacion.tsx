// Evaluación: pestañas según el rol.
//  · «Mis cuestionarios» (todos): los cuestionarios de las tareas del itinerario.
//  · «Revisar preguntas» (expertos): aprobar, editar, descartar o generar preguntas.
//  · «Observar en el puesto» (jefes): lista de comprobación de los pasos.
// La pestaña y lo que se está haciendo van en la URL (?pestana=observar&usuario=3&tarea=5),
// para poder llegar desde el pasaporte o la matriz del equipo.

import { useCallback, useEffect } from 'react'
import { ClipboardCheck, Eye, ListChecks } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { get } from '../../api'
import { refrescarContadores } from '../../Marco'
import { useSesion } from '../../sesion'
import { Cabecera, ErrorCarga, Esqueleto, Pestanas, Tarjeta, useDatos } from '../../ui'
import Cuestionario from './Cuestionario'
import MisCuestionarios from './MisCuestionarios'
import Observar from './Observar'
import RevisarPreguntas from './RevisarPreguntas'
import type { Pendientes } from './tipos'
import './evaluacion.css'

type Pestana = 'cuestionarios' | 'preguntas' | 'observar'

const SUBTITULOS: Record<Pestana, string> = {
  cuestionarios: 'Demuestra lo que sabes de cada tarea. Las preguntas salen de los pasos de la instrucción vigente y las aprueba un experto.',
  preguntas: 'Revisa las preguntas que propone la IA antes de que entren en el cuestionario: apruébalas, corrígelas o descártalas.',
  observar: 'Observa a una persona mientras trabaja y marca cada paso. Los críticos van en rojo.',
}

export default function Evaluacion() {
  const { puede } = useSesion()
  const [params, setParams] = useSearchParams()
  const { datos: pend, error, recargar } = useDatos((s) => get<Pendientes>('/api/evaluacion/pendientes', s), [])
  // Algo ha cambiado (cuestionario, observación, preguntas): las pestañas y el menú lo reflejan ya.
  const cambio = useCallback(() => { recargar(); refrescarContadores() }, [recargar])

  const disponibles: Pestana[] = ['cuestionarios']
  if (puede('revisar_preguntas')) disponibles.push('preguntas')
  if (puede('observar')) disponibles.push('observar')
  const pedida = params.get('pestana') as Pestana | null
  const activa: Pestana = pedida && disponibles.includes(pedida) ? pedida : 'cuestionarios'
  const tareaCuestionario = activa === 'cuestionarios' ? Number(params.get('tarea')) || null : null

  const contadores = {
    cuestionarios: pend?.cuestionarios.filter((c) => c.pendiente).length,
    preguntas: pend?.preguntas?.reduce((n, i) => n + i.propuestas, 0),
    observar: pend?.observaciones?.length,
  }
  // En el móvil las tres pestañas no caben: texto corto y sin icono (evaluacion.css).
  const texto = (largo: string, corto: string) => (
    <><span className="ev-txt-largo">{largo}</span><span className="ev-txt-corto">{corto}</span></>
  )
  const pestanas = [
    { id: 'cuestionarios' as const, texto: texto('Mis cuestionarios', 'Cuestionarios'), icono: <ClipboardCheck size={17} />, contador: contadores.cuestionarios || undefined },
    { id: 'preguntas' as const, texto: texto('Revisar preguntas', 'Preguntas'), icono: <ListChecks size={17} />, contador: contadores.preguntas || undefined },
    { id: 'observar' as const, texto: texto('Observar en el puesto', 'Observar'), icono: <Eye size={17} />, contador: contadores.observar || undefined },
  ].filter((p) => disponibles.includes(p.id))

  // Si aun así no caben, la pestaña activa se desliza a la vista (al llegar desde la matriz con
  // ?pestana=observar quedaba fuera de la pantalla).
  useEffect(() => {
    document.querySelector('.ev-pestanas .pestana.activa')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [activa])

  function contenido() {
    if (tareaCuestionario) {
      return (
        <Cuestionario key={tareaCuestionario} tareaId={tareaCuestionario}
          onSalir={(cambios) => { setParams({}); if (cambios) cambio() }} />
      )
    }
    if (activa === 'observar') return <Observar sugeridas={pend?.observaciones ?? []} onCambio={cambio} />
    if (error) return <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
    if (!pend) {
      return <div className="rejilla auto">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={190} />)}</div>
    }
    if (activa === 'preguntas') return <RevisarPreguntas instrucciones={pend.preguntas ?? []} onCambio={cambio} />
    return <MisCuestionarios cuestionarios={pend.cuestionarios} onEmpezar={(id) => setParams({ tarea: String(id) })} />
  }

  return (
    <>
      <Cabecera antetitulo="Evaluación" titulo={tareaCuestionario ? 'Cuestionario' : 'Evaluación'}
        subtitulo={tareaCuestionario ? undefined : SUBTITULOS[activa]} />
      {!tareaCuestionario && pestanas.length > 1 && (
        <div className="ev-pestanas">
          <Pestanas<Pestana> pestanas={pestanas} activa={activa} onCambio={(id) => setParams(id === 'cuestionarios' ? {} : { pestana: id })} />
        </div>
      )}
      {contenido()}
    </>
  )
}
