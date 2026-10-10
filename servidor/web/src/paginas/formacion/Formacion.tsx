// Formación: itinerario de la persona. Una tarjeta por tarea con su nivel ILUO, el avance,
// la siguiente acción recomendada y un botón para continuar. Las formaciones activas en otros
// departamentos se destacan aparte.

import { useNavigate } from 'react-router-dom'
import {
  ArrowRight, Award, BookOpen, Briefcase, ClipboardCheck, Clock, Eye, GraduationCap, ListChecks, RefreshCw,
  TrendingUp, Wrench,
} from 'lucide-react'
import { fecha, get } from '../../api'
import {
  BarraProgreso, Boton, Cabecera, Dato, ErrorCarga, Esqueleto, Etiqueta, Iluo, LETRA_ILUO, Tarjeta, Vacio, useDatos,
} from '../../ui'
import type { FormacionActiva, ItemItinerario, Itinerario } from './tipos'
import './formacion.css'

function textoBoton(t: ItemItinerario): string {
  if (!t.tiene_instruccion) return 'Ver'
  if (t.siguiente.accion === 'cuestionario') return 'Ir al cuestionario'
  if (t.nivel >= 3) return 'Repasar'
  return t.avance > 0 || t.nivel > 0 ? 'Continuar' : 'Empezar'
}

function FilaTarea({ t }: { t: ItemItinerario }) {
  const navegar = useNavigate()
  const ir = () => navegar(`/formacion/tarea/${t.tarea_id}`)
  const ml = t.microlecciones
  return (
    <div className={`fm-item ${t.tiene_instruccion ? '' : 'sin-instruccion'}`} role="link" tabIndex={0} onClick={ir}
      onKeyDown={(e) => { if (e.key === 'Enter' && e.target === e.currentTarget) ir() }} aria-label={`${t.nombre}: ${t.siguiente.texto}`}>
      <div className="fm-iluo" title={`Nivel ${LETRA_ILUO[t.nivel]}`}>
        <Iluo nivel={t.nivel} tamano={42} caducado={t.caducado} />
        <span className="letra">{t.nivel ? t.nivel_letra : 'Sin nivel'}</span>
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="fm-titulo">
          <span className="fm-nombre">{t.nombre}</span>
          {t.codigo && <span className="fm-codigo">{t.codigo}</span>}
          {t.requiere_reevaluacion && <Etiqueta tono="naranja" icono={<RefreshCw />}>Reevaluar</Etiqueta>}
          {t.caducado && <Etiqueta tono="roja" icono={<Clock />}>Caducado</Etiqueta>}
          {!t.tiene_instruccion && <Etiqueta>Sin instrucción todavía</Etiqueta>}
        </div>
        {t.tiene_instruccion && (
          <>
            <div className="fm-avance">
              <BarraProgreso valor={t.avance} tono={t.avance >= 100 ? undefined : 'amarilla'} />
              <span>{t.avance} %</span>
            </div>
            <div className="fm-hitos">
              {ml.total > 0 && (
                <span className={`fm-hito ${ml.vistas === ml.total ? 'ok' : ''}`}><BookOpen /> {ml.vistas}/{ml.total} micro-lecciones</span>
              )}
              <span className={`fm-hito ${t.cuestionario.aprobado ? 'ok' : ''}`}>
                <ClipboardCheck /> {t.cuestionario.aprobado ? 'Cuestionario aprobado' : 'Cuestionario pendiente'}
              </span>
              <span className={`fm-hito ${t.ejecuciones.completadas >= t.ejecuciones.objetivo ? 'ok' : ''}`}>
                <Wrench /> {Math.min(t.ejecuciones.completadas, t.ejecuciones.objetivo)}/{t.ejecuciones.objetivo} ejecuciones
              </span>
              {t.observacion_aprobada && <span className="fm-hito ok"><Eye /> Observación aprobada</span>}
            </div>
          </>
        )}
        <div className="fm-siguiente"><ArrowRight /> <span>{t.siguiente.texto}</span></div>
      </div>
      <Boton variante={t.tiene_instruccion && t.nivel < 3 ? 'primario' : 'secundario'} icono={<ArrowRight />}
        onClick={(e) => { e.stopPropagation(); navegar(t.siguiente.ruta || `/formacion/tarea/${t.tarea_id}`) }}>
        {textoBoton(t)}
      </Boton>
    </div>
  )
}

function BloqueFormacion({ f, tareas }: { f: FormacionActiva; tareas: ItemItinerario[] }) {
  return (
    <section className="fm-formacion">
      <div className="fm-formacion-cabecera">
        <div className="fm-formacion-icono"><GraduationCap /></div>
        <div className="crece">
          <div className="pequeno negrita" style={{ color: 'var(--acento-oscuro)' }}>Formación activa en otro departamento</div>
          <h2>{f.departamento}{f.puesto ? ` · ${f.puesto}` : ''}</h2>
          <div className="pequeno apagado">
            Desde el {fecha(f.inicio)}{f.fin_previsto ? `, hasta el ${fecha(f.fin_previsto)}` : ''} · {f.tareas}{' '}
            {f.tareas === 1 ? 'tarea' : 'tareas'}. Mientras dure, encuentras su material de formación en el copiloto.
          </div>
        </div>
        <div className="fm-avance">
          <BarraProgreso valor={f.avance} />
          <span>{f.avance} %</span>
        </div>
      </div>
      {tareas.length ? (
        <div className="fm-lista">{tareas.map((t) => <FilaTarea key={t.tarea_id} t={t} />)}</div>
      ) : (
        <div className="apagado pequeno">Esta formación todavía no tiene tareas con instrucción.</div>
      )}
    </section>
  )
}

function EsqueletoItinerario() {
  return (
    <>
      <div className="rejilla c4 mb-3">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={76} />)}</div>
      <div className="fm-lista">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={112} />)}</div>
    </>
  )
}

export default function Formacion() {
  const navegar = useNavigate()
  const { datos, error, cargando, recargar } = useDatos((s) => get<Itinerario>('/api/formacion/itinerario', s))

  const cabecera = (
    <Cabecera
      antetitulo={<><GraduationCap size={14} /> Formación</>}
      titulo="Tu itinerario"
      subtitulo="Las tareas de tu puesto y de tus formaciones, con lo que te falta para dominar cada una."
      acciones={<Boton icono={<Wrench />} onClick={() => navegar('/planta')}>Modo planta</Boton>}
    />
  )
  if (cargando && !datos) return <>{cabecera}<EsqueletoItinerario /></>
  if (error || !datos) return <>{cabecera}<Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta></>

  const { tareas, formaciones, resumen } = datos
  const propias = tareas.filter((t) => t.origen === 'puesto')
  const otras = tareas.filter((t) => t.origen === 'departamento' || t.origen === 'admin')
  const fuera = formaciones.filter((f) => f.otro_departamento)
  const dentro = formaciones.filter((f) => !f.otro_departamento)
  const deFormacion = (f: FormacionActiva) => tareas.filter((t) => t.formacion?.id === f.id)

  if (!tareas.length && !formaciones.length) {
    return (
      <>
        {cabecera}
        <Tarjeta>
          <Vacio icono={<GraduationCap />} titulo="Tu itinerario está vacío">
            Aún no hay tareas asignadas a tu puesto. Pide a tu responsable que te asigne un puesto o una formación
            y aquí verás qué aprender y en qué orden.
          </Vacio>
        </Tarjeta>
      </>
    )
  }

  return (
    <>
      {cabecera}
      <div className="rejilla c4">
        <Dato icono={<ListChecks />} valor={resumen.tareas} etiqueta="Tareas en tu itinerario" />
        <Dato icono={<Award />} tono="verde" valor={resumen.autonomas} etiqueta="Ya eres autónomo (U u O)" />
        <Dato icono={<TrendingUp />} tono="info" valor={`${resumen.avance_medio} %`} etiqueta="Avance medio" />
        <Dato icono={<RefreshCw />} tono={resumen.reevaluacion ? 'alerta' : undefined} valor={resumen.reevaluacion}
          etiqueta="Pendientes de reevaluar" />
      </div>

      {fuera.map((f) => <BloqueFormacion key={f.id} f={f} tareas={deFormacion(f)} />)}

      {propias.length > 0 && (
        <section className="fm-seccion">
          <div className="fm-seccion-titulo"><Briefcase /> Tu puesto</div>
          <div className="fm-lista">{propias.map((t) => <FilaTarea key={t.tarea_id} t={t} />)}</div>
        </section>
      )}

      {dentro.map((f) => {
        const suyas = deFormacion(f)
        return (
          <section key={f.id} className="fm-seccion">
            <div className="fm-seccion-titulo"><GraduationCap /> Formación en {f.puesto ?? f.departamento}</div>
            {suyas.length ? (
              <div className="fm-lista">{suyas.map((t) => <FilaTarea key={t.tarea_id} t={t} />)}</div>
            ) : (
              <div className="apagado pequeno">Esta formación todavía no tiene tareas con instrucción.</div>
            )}
          </section>
        )
      })}

      {otras.length > 0 && (
        <section className="fm-seccion">
          <div className="fm-seccion-titulo"><Award /> Otras tareas en las que tienes nivel</div>
          <div className="fm-lista">{otras.map((t) => <FilaTarea key={t.tarea_id} t={t} />)}</div>
        </section>
      )}
    </>
  )
}
