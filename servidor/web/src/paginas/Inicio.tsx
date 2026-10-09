// Inicio: panel de cada persona según su rol. Saludo, «continúa donde lo dejaste», accesos
// rápidos, sus tareas con nivel ILUO y sus aportaciones; bandejas del equipo para los jefes y
// cifras de la planta para la administración. Todo llega calculado de GET /api/inicio.

import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight, BookOpen, Brain, CircleHelp, ClipboardCheck, Eye, FileText, GraduationCap, Hourglass, Inbox, Lightbulb,
  ListChecks, MessageSquare, Network, CirclePlay, RefreshCw, ScrollText, Server, ShieldCheck, Sparkles, TrendingUp,
  UserCog, Users, Wrench,
} from 'lucide-react'
import { hace, get } from '../api'
import { NOMBRE_ROL, useSesion } from '../sesion'
import {
  BarraProgreso, Boton, Dato, ErrorCarga, Esqueleto, Etiqueta, Iluo, LETRA_ILUO, NOMBRE_ILUO, Tarjeta, Vacio, useDatos,
} from '../ui'
import './inicio/inicio.css'

// ------------------------------------------------------------------ tipos de /api/inicio

interface Continuar {
  tipo: 'ejecucion' | 'microleccion' | 'evaluacion'
  id: number
  titulo: string
  codigo: string | null
  detalle: string
  progreso: number
  ruta: string
  momento: string | null
}

interface MiTarea {
  id: number
  codigo: string | null
  nombre: string
  puesto: string
  criticidad: number
  origen: 'puesto' | 'formacion' | 'historial'
  nivel: number
  letra: string
  caduca: string | null
  caducado: boolean
  requiere_reevaluacion: boolean
  instruccion_id: number | null
}

interface Equipo {
  ambito: string | null
  personas: number
  pendientes_validar: number
  aportaciones: { id: number; titulo: string; autor: string | null; creada: string; nota_de_voz: boolean }[]
  lagunas_abiertas: number
  lagunas: { id: number; pregunta: string; frecuencia: number; ultima_vez: string }[]
  reevaluaciones_total: number
  reevaluaciones: { usuario_id: number; persona: string; tarea_id: number; tarea: string; letra: string; motivo: string; caduca: string | null }[]
  observaciones_sugeridas: { usuario_id: number; persona: string; tarea_id: number; tarea: string; codigo: string | null }[]
}

interface DatosInicio {
  nombre: string
  nombre_corto: string
  saludo: string
  rol: 'empleado' | 'jefe' | 'admin'
  es_experto: boolean
  puesto: string | null
  accesos: { clave: string; titulo: string; descripcion: string; ruta: string }[]
  continuar: Continuar | null
  cifras: { tareas_autonomas: number; tareas_en_formacion: number; ejecuciones: number; consultas_semana: number; aportaciones_validadas: number }
  mis_tareas: MiTarea[]
  mis_tareas_total: number
  mis_aportaciones: { id: number; titulo: string; estado: string; creada: string }[]
  cuestionarios_disponibles: number
  experto: { borradores: number; preguntas_por_revisar: number } | null
  equipo: Equipo | null
  planta: {
    personas: number; departamentos: number; documentos: number; documentos_procesando: number
    instrucciones_publicadas: number; consultas_semana: number; pct_con_respaldo: number | null; lagunas_abiertas: number
  } | null
}

const ICONO_ACCESO: Record<string, ReactNode> = {
  planta: <Wrench />, chat: <MessageSquare />, formacion: <GraduationCap />, aportaciones: <Lightbulb />,
}

const ESTADO_APORTACION: Record<string, { texto: string; tono?: 'amarilla' | 'verde' | 'roja' | 'azul' }> = {
  procesando: { texto: 'Procesando', tono: 'azul' },
  pendiente: { texto: 'Pendiente de validar', tono: 'amarilla' },
  validada: { texto: 'Validada', tono: 'verde' },
  rechazada: { texto: 'No validada', tono: 'roja' },
}

function saludoLocal(nombre: string): string {
  const h = new Date().getHours()
  return `${h >= 6 && h < 14 ? 'Buenos días' : h >= 14 && h < 21 ? 'Buenas tardes' : 'Buenas noches'}, ${nombre}`
}

// ------------------------------------------------------------------ página

export default function Inicio() {
  const { perfil } = useSesion()
  const { datos, error, recargar } = useDatos((s) => get<DatosInicio>('/api/inicio', s), [])

  if (error && !datos) return <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
  if (!datos) return <EsqueletoInicio />

  const d = datos
  const esAdmin = d.rol === 'admin'
  const hoy = new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })
  const rolTexto = [NOMBRE_ROL[d.rol] ?? d.rol, d.es_experto && d.rol === 'empleado' ? 'Experto' : null].filter(Boolean).join(' · ')

  return (
    <>
      <section className="ini-portada">
        <div>
          <div className="ini-fecha">{hoy}</div>
          <h1>{saludoLocal(d.nombre_corto || perfil?.nombre || '')}</h1>
          <div className="ini-sub">
            {d.puesto && <><span>{d.puesto}</span><span className="separa">·</span></>}
            <span>{rolTexto}</span>
          </div>
          <div className="ini-chips">
            {!esAdmin && d.cifras.tareas_autonomas > 0 && (
              <Link className="ini-chip" to="/progreso"><Sparkles /> <strong>{d.cifras.tareas_autonomas}</strong> {d.cifras.tareas_autonomas === 1 ? 'tarea dominada' : 'tareas dominadas'}</Link>
            )}
            {d.cuestionarios_disponibles > 0 && (
              <Link className="ini-chip" to="/evaluacion"><ClipboardCheck /> <strong>{d.cuestionarios_disponibles}</strong> {d.cuestionarios_disponibles === 1 ? 'cuestionario disponible' : 'cuestionarios disponibles'}</Link>
            )}
            {d.equipo && d.equipo.pendientes_validar > 0 && (
              <Link className="ini-chip" to="/validar"><Inbox /> <strong>{d.equipo.pendientes_validar}</strong> por validar</Link>
            )}
            {d.cifras.aportaciones_validadas > 0 && (
              <Link className="ini-chip" to="/aportaciones"><Lightbulb /> <strong>{d.cifras.aportaciones_validadas}</strong> {d.cifras.aportaciones_validadas === 1 ? 'aportación tuya ayuda' : 'aportaciones tuyas ayudan'} a otros</Link>
            )}
          </div>
        </div>
        <TarjetaContinuar continuar={d.continuar} tareas={d.mis_tareas} esAdmin={esAdmin} />
      </section>

      {d.accesos.length > 0 && (
        <nav className="ini-accesos" aria-label="Accesos rápidos">
          {d.accesos.map((a) => (
            <Link key={a.clave} to={a.ruta} className={`ini-acceso ${a.clave}`}>
              <div className="icono">{ICONO_ACCESO[a.clave] ?? <ArrowRight />}</div>
              <ArrowRight className="flecha" size={18} />
              <h3>{a.titulo}</h3>
              <p>{a.descripcion}</p>
            </Link>
          ))}
        </nav>
      )}

      {d.planta && <CifrasPlanta p={d.planta} />}

      {!esAdmin && (
        <section className="ini-seccion">
          <div className="ini-cifras">
            <Dato icono={<Sparkles />} tono="verde" valor={d.cifras.tareas_autonomas} etiqueta="Tareas que haces solo (U u O)" />
            <Dato icono={<GraduationCap />} valor={d.cifras.tareas_en_formacion} etiqueta="Tareas en aprendizaje (I o L)" />
            <Dato icono={<Wrench />} tono="info" valor={d.cifras.ejecuciones} etiqueta="Ejecuciones completadas" />
            <Dato icono={<MessageSquare />} valor={d.cifras.consultas_semana} etiqueta="Consultas esta semana" />
          </div>
        </section>
      )}

      {d.equipo && <Bandejas e={d.equipo} />}

      <div className="ini-dos">
        {(!esAdmin || d.mis_tareas.length > 0) ? <MisTareas d={d} /> : <AccesosAdmin />}
        <div className="columna" style={{ gap: 16 }}>
          {d.experto && <TrabajoExperto e={d.experto} />}
          <MisAportaciones d={d} />
          {esAdmin && d.mis_tareas.length > 0 && <AccesosAdmin />}
        </div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ piezas

function TarjetaContinuar({ continuar, tareas, esAdmin }: { continuar: Continuar | null; tareas: MiTarea[]; esAdmin: boolean }) {
  const navegar = useNavigate()
  if (!continuar) {
    const siguiente = tareas.find((t) => t.instruccion_id && t.nivel < 3)
    return (
      <div className="ini-continuar">
        <div className="antetitulo"><CirclePlay /> {esAdmin ? 'Estado de la planta' : 'Nada a medias'}</div>
        {esAdmin ? (
          <>
            <h3>La planta de un vistazo</h3>
            <div className="detalle">Comprueba que los servicios responden y revisa los modelos permitidos y la actividad reciente.</div>
            <Boton variante="primario" icono={<Server />} onClick={() => navegar('/admin/sistema')}>Ver el sistema</Boton>
          </>
        ) : siguiente ? (
          <>
            <h3>{siguiente.nombre}</h3>
            <div className="detalle">Una buena tarea para seguir aprendiendo: nivel {LETRA_ILUO[siguiente.nivel]} · {NOMBRE_ILUO[siguiente.nivel].toLowerCase()}.</div>
            <Boton variante="primario" icono={<ArrowRight />} onClick={() => navegar(`/formacion/tarea/${siguiente.id}`)}>Empezar</Boton>
          </>
        ) : (
          <>
            <h3>¿Por dónde empezamos?</h3>
            <div className="detalle">Pregunta al copiloto cualquier duda del puesto o comparte un truco que te haya funcionado.</div>
            <Boton variante="primario" icono={<MessageSquare />} onClick={() => navegar('/copiloto')}>Abrir el copiloto</Boton>
          </>
        )}
      </div>
    )
  }
  const textoBoton = continuar.tipo === 'ejecucion' ? 'Seguir en modo planta' : continuar.tipo === 'evaluacion' ? 'Hacer el cuestionario' : 'Seguir aprendiendo'
  return (
    <div className="ini-continuar">
      <div className="antetitulo"><CirclePlay /> Continúa donde lo dejaste</div>
      <h3>{continuar.titulo}</h3>
      {continuar.codigo && <div className="codigo">{continuar.codigo}</div>}
      <div className="detalle">{continuar.detalle}{continuar.momento && <> · {hace(continuar.momento)}</>}</div>
      <BarraProgreso valor={continuar.progreso} tono="amarilla" />
      <div className="mt-2">
        <Boton variante="primario" icono={<ArrowRight />} onClick={() => navegar(continuar.ruta)}>{textoBoton}</Boton>
      </div>
    </div>
  )
}

function CifrasPlanta({ p }: { p: NonNullable<DatosInicio['planta']> }) {
  return (
    <section className="ini-seccion">
      <div className="ini-seccion-titulo">
        <h2><TrendingUp /> La planta en cifras</h2>
        <span className="pequeno apagado">Consultas de los últimos 7 días</span>
      </div>
      <div className="ini-cifras">
        <Dato icono={<Users />} valor={p.personas} etiqueta={`Personas en ${p.departamentos} ${p.departamentos === 1 ? 'departamento' : 'departamentos'}`} />
        <Dato icono={<FileText />} tono="info" valor={p.documentos}
          etiqueta={p.documentos_procesando ? `Documentos listos · ${p.documentos_procesando} pendientes` : 'Documentos listos para consultar'} />
        <Dato icono={<ListChecks />} tono="verde" valor={p.instrucciones_publicadas} etiqueta="Instrucciones publicadas" />
        <Dato icono={<MessageSquare />} valor={p.consultas_semana} etiqueta="Consultas esta semana" />
        <Dato icono={<ShieldCheck />} tono={p.pct_con_respaldo !== null && p.pct_con_respaldo < 70 ? 'alerta' : 'verde'}
          valor={p.pct_con_respaldo === null ? '-' : `${p.pct_con_respaldo} %`} etiqueta="Consultas con respaldo documental" />
        <Dato icono={<CircleHelp />} tono={p.lagunas_abiertas ? 'alerta' : undefined} valor={p.lagunas_abiertas} etiqueta="Lagunas de conocimiento abiertas" />
      </div>
    </section>
  )
}

function Bandeja({ titulo, icono, cifra, alerta, ruta, textoRuta, vacio, children }: {
  titulo: string; icono: ReactNode; cifra: number; alerta?: boolean; ruta: string; textoRuta: string; vacio: string; children: ReactNode
}) {
  return (
    <Tarjeta relleno={false}
      titulo={<>{icono}{titulo} <span className={`ini-bandeja-cifra ${cifra ? (alerta ? 'alerta' : 'activa') : ''}`}>{cifra}</span></>}
      acciones={<Link to={ruta} className="pequeno negrita">{textoRuta} <ArrowRight size={13} style={{ verticalAlign: -2 }} /></Link>}>
      {cifra ? <ul className="ini-lista">{children}</ul> : <div className="ini-vacio-mini"><ShieldCheck /> {vacio}</div>}
    </Tarjeta>
  )
}

function Bandejas({ e }: { e: Equipo }) {
  return (
    <section className="ini-seccion">
      <div className="ini-seccion-titulo">
        <h2><Users /> Tu equipo{e.ambito ? ` · ${e.ambito}` : ''}</h2>
        <span className="pequeno apagado">{e.personas} {e.personas === 1 ? 'persona activa' : 'personas activas'}</span>
      </div>
      {!e.ambito ? (
        <Tarjeta><Vacio icono={<Users />} titulo="Sin departamento asignado">Pide a la administración que te asigne un departamento para ver las bandejas de tu equipo.</Vacio></Tarjeta>
      ) : (
        <div className="ini-bandejas">
          <Bandeja titulo="Aportaciones por validar" icono={<Inbox size={18} />} cifra={e.pendientes_validar} ruta="/validar"
            textoRuta="Validar" vacio="No hay aportaciones esperando. Todo validado.">
            {e.aportaciones.map((a) => (
              <li key={a.id}>
                <Link className="ini-item" to="/validar">
                  <div className="icono-item"><Lightbulb /></div>
                  <div className="cuerpo">
                    <div className="titulo">{a.titulo}</div>
                    <div className="sub">{a.autor ?? 'Alguien'} · {hace(a.creada)}{a.nota_de_voz && ' · nota de voz'}</div>
                  </div>
                </Link>
              </li>
            ))}
          </Bandeja>
          <Bandeja titulo="Lagunas abiertas" icono={<CircleHelp size={18} />} cifra={e.lagunas_abiertas} alerta ruta="/lagunas"
            textoRuta="Ver lagunas" vacio="El copiloto ha encontrado respaldo para todo lo que se le ha preguntado.">
            {e.lagunas.map((l) => (
              <li key={l.id}>
                <Link className="ini-item" to="/lagunas">
                  <div className="cuerpo">
                    <div className="titulo">«{l.pregunta}»</div>
                    <div className="sub">Última vez {hace(l.ultima_vez)}</div>
                  </div>
                  <span className="ini-frecuencia">{l.frecuencia} {l.frecuencia === 1 ? 'vez' : 'veces'}</span>
                </Link>
              </li>
            ))}
          </Bandeja>
          <Bandeja titulo="Reevaluaciones" icono={<RefreshCw size={18} />} cifra={e.reevaluaciones_total} ruta="/equipo"
            textoRuta="Progreso del equipo" vacio="Ningún nivel ILUO caduca en los próximos 30 días.">
            {e.reevaluaciones.map((r) => (
              <li key={`${r.usuario_id}-${r.tarea_id}`}>
                <Link className="ini-item" to="/equipo">
                  <div className="icono-item"><Hourglass /></div>
                  <div className="cuerpo">
                    <div className="titulo">{r.persona}</div>
                    <div className="sub">{r.tarea} · nivel {r.letra}</div>
                  </div>
                  <Etiqueta tono={r.motivo === 'Caduca pronto' ? 'amarilla' : 'naranja'}>{r.motivo}</Etiqueta>
                </Link>
              </li>
            ))}
          </Bandeja>
          <Bandeja titulo="Listos para observar" icono={<Eye size={18} />} cifra={e.observaciones_sugeridas.length} ruta="/equipo"
            textoRuta="Progreso del equipo" vacio="Nadie está en L esperando una observación en el puesto.">
            {e.observaciones_sugeridas.map((o) => (
              <li key={`${o.usuario_id}-${o.tarea_id}`}>
                <Link className="ini-item" to="/equipo">
                  <Iluo nivel={2} tamano={26} />
                  <div className="cuerpo">
                    <div className="titulo">{o.persona}</div>
                    <div className="sub">{o.codigo && <span className="codigo">{o.codigo}</span>}{o.tarea}</div>
                  </div>
                  <span className="pequeno apagado">Observar para U</span>
                </Link>
              </li>
            ))}
          </Bandeja>
        </div>
      )}
    </section>
  )
}

function MisTareas({ d }: { d: DatosInicio }) {
  return (
    <Tarjeta relleno={false} titulo={<><Wrench size={18} /> Mis tareas</>}
      acciones={d.mis_tareas_total > d.mis_tareas.length
        ? <Link to="/progreso" className="pequeno negrita">Ver las {d.mis_tareas_total}</Link>
        : <Link to="/progreso" className="pequeno negrita">Mi progreso</Link>}>
      {!d.mis_tareas.length ? (
        <Vacio icono={<Wrench />} titulo="Aún no tienes tareas">
          Cuando la administración te asigne un puesto o una formación, sus tareas aparecerán aquí con tu nivel ILUO.
        </Vacio>
      ) : (
        <ul className="ini-lista">
          {d.mis_tareas.map((t) => (
            <li key={t.id}>
              <Link className="ini-item" to={`/formacion/tarea/${t.id}`}>
                <Iluo nivel={t.nivel} tamano={30} caducado={t.caducado} />
                <div className="cuerpo">
                  <div className="titulo">{t.nombre}</div>
                  <div className="sub">
                    {t.codigo && <span className="codigo">{t.codigo}</span>}
                    <span>{t.puesto}</span>
                    {t.origen === 'formacion' && <Etiqueta tono="azul">Formación</Etiqueta>}
                    {t.caducado ? <Etiqueta tono="roja">Caducado</Etiqueta>
                      : t.requiere_reevaluacion && <Etiqueta tono="naranja">Reevaluar</Etiqueta>}
                    {!t.instruccion_id && <span className="apagado">sin instrucción todavía</span>}
                  </div>
                </div>
                <div className="ini-nivel">
                  <strong>{LETRA_ILUO[t.nivel]}</strong>
                  {NOMBRE_ILUO[t.nivel]}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Tarjeta>
  )
}

function TrabajoExperto({ e }: { e: NonNullable<DatosInicio['experto']> }) {
  return (
    <Tarjeta titulo={<><BookOpen size={18} /> Tu saber, en marcha</>}>
      <div className="ini-experto">
        <Link to="/instrucciones">
          <strong>{e.borradores}</strong>
          <span>{e.borradores === 1 ? 'borrador de instrucción' : 'borradores de instrucciones'}</span>
        </Link>
        <Link to="/evaluacion">
          <strong>{e.preguntas_por_revisar}</strong>
          <span>{e.preguntas_por_revisar === 1 ? 'pregunta por revisar' : 'preguntas por revisar'}</span>
        </Link>
      </div>
    </Tarjeta>
  )
}

function MisAportaciones({ d }: { d: DatosInicio }) {
  const navegar = useNavigate()
  return (
    <Tarjeta relleno={false} titulo={<><Lightbulb size={18} /> Mis aportaciones</>}
      acciones={<Boton tamano="pequeno" icono={<Lightbulb />} onClick={() => navegar('/aportaciones')}>Aportar</Boton>}>
      {!d.mis_aportaciones.length ? (
        <div className="ini-vacio-mini" style={{ alignItems: 'flex-start' }}>
          <Lightbulb />
          <span>¿Conoces un truco o la solución a una avería? Cuéntalo por voz o por escrito: tu jefe lo valida y el copiloto lo cita con tu nombre.</span>
        </div>
      ) : (
        <ul className="ini-lista">
          {d.mis_aportaciones.map((a) => {
            const e = ESTADO_APORTACION[a.estado] ?? { texto: a.estado }
            return (
              <li key={a.id}>
                <Link className="ini-item" to="/aportaciones">
                  <div className="cuerpo">
                    <div className="titulo">{a.titulo}</div>
                    <div className="sub">{hace(a.creada)}</div>
                  </div>
                  <Etiqueta tono={e.tono}>{e.texto}</Etiqueta>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Tarjeta>
  )
}

function AccesosAdmin() {
  const enlaces: [string, string, ReactNode][] = [
    ['/admin/organizacion', 'Organización', <Network key="o" />],
    ['/admin/empleados', 'Empleados', <UserCog key="e" />],
    ['/admin/modelos', 'Modelos', <Brain key="m" />],
    ['/admin/registro', 'Registro', <ScrollText key="r" />],
    ['/documentos', 'Documentos', <FileText key="d" />],
    ['/admin/sistema', 'Sistema', <Server key="s" />],
  ]
  return (
    <Tarjeta titulo={<><ShieldCheck size={18} /> Administración</>}>
      <div className="ini-enlaces-admin">
        {enlaces.map(([ruta, texto, icono]) => <Link key={ruta} to={ruta} className="ini-enlace-admin">{icono}{texto}</Link>)}
      </div>
    </Tarjeta>
  )
}

function EsqueletoInicio() {
  return (
    <>
      <div className="ini-portada" style={{ minHeight: 190 }}>
        <div className="columna">
          <Esqueleto alto={14} ancho={160} />
          <Esqueleto alto={34} ancho="70%" />
          <Esqueleto alto={14} ancho={220} />
        </div>
        <Esqueleto alto={150} />
      </div>
      <div className="ini-accesos">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={148} />)}</div>
      <div className="ini-dos">
        <div className="columna">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={52} />)}</div>
        <Esqueleto alto={220} />
      </div>
    </>
  )
}
