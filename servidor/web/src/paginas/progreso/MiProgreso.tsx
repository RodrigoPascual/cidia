// Mi progreso: el pasaporte de habilidades de la persona con sesión.

import { useNavigate, useSearchParams } from 'react-router-dom'
import { BookOpen, ClipboardCheck, GraduationCap, RefreshCw, Wrench } from 'lucide-react'
import { get } from '../../api'
import { Boton, Cabecera, ErrorCarga, Esqueleto, Tarjeta, useDatos, Vacio } from '../../ui'
import Pasaporte from './Pasaporte'
import type { Progreso, TareaProgreso } from './tipos'
import './progreso.css'

function EsqueletoPasaporte() {
  return (
    <div className="columna" style={{ gap: 18 }}>
      <Tarjeta>
        <div className="fila" style={{ gap: 16 }}>
          <Esqueleto alto={56} ancho={56} className="redondo" />
          <div className="crece columna" style={{ gap: 8 }}><Esqueleto alto={20} ancho="40%" /><Esqueleto alto={14} ancho="60%" /></div>
        </div>
      </Tarjeta>
      <div className="pp-rejilla">
        <div className="columna" style={{ gap: 8 }}>
          {[0, 1, 2].map((i) => <Esqueleto key={i} alto={86} />)}
        </div>
        <div className="columna" style={{ gap: 16 }}><Esqueleto alto={150} /><Esqueleto alto={240} /></div>
      </div>
    </div>
  )
}

export default function MiProgreso() {
  const navegar = useNavigate()
  const [params] = useSearchParams()
  const { datos, error, cargando, recargar } = useDatos((s) => get<Progreso>('/api/progreso/yo', s), [])
  const tareaInicial = Number(params.get('tarea')) || undefined

  function acciones(t: TareaProgreso) {
    const pendiente = t.cuestionario_disponible && (!t.cuestionario_aprobado || t.requiere_reevaluacion)
    return (
      <>
        {pendiente && (
          <Boton variante="primario" icono={<ClipboardCheck />} onClick={() => navegar(`/evaluacion?tarea=${t.tarea.id}`)}>
            Hacer el cuestionario
          </Boton>
        )}
        <Boton icono={<Wrench />} onClick={() => navegar('/planta')}>Practicar en modo planta</Boton>
        <Boton variante="fantasma" icono={<BookOpen />} onClick={() => navegar(`/formacion/tarea/${t.tarea.id}`)}>
          Ver la formación
        </Boton>
      </>
    )
  }

  return (
    <>
      <Cabecera
        antetitulo="Pasaporte de habilidades"
        titulo="Mi progreso"
        subtitulo="Qué tareas dominas, con qué nivel, hasta cuándo y con qué evidencias. Tu responsable ve este mismo panel."
        acciones={<Boton variante="fantasma" icono={<RefreshCw />} onClick={recargar} cargando={cargando && !!datos}>Actualizar</Boton>}
      />
      {error ? (
        <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
      ) : !datos ? (
        <EsqueletoPasaporte />
      ) : datos.tareas.length === 0 ? (
        <Tarjeta>
          <Vacio icono={<GraduationCap />} titulo="Todavía no tienes tareas en tu itinerario"
            accion={<Boton variante="primario" onClick={() => navegar('/formacion')}>Ir a formación</Boton>}>
            Cuando tengas un puesto o una formación asignada, aquí verás tu nivel en cada tarea, lo que te falta
            para subir y tu curva de autonomía.
          </Vacio>
        </Tarjeta>
      ) : (
        <Pasaporte datos={datos} propio acciones={acciones} tareaInicial={tareaInicial} />
      )}
    </>
  )
}
