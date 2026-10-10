// Progreso del equipo: matriz ILUO personas × tareas del departamento, con indicadores,
// caducidades próximas y reevaluaciones pendientes. La administración elige departamento y
// ve además el resumen de toda la planta. Cada celda abre el detalle de esa persona en esa
// tarea con sus evidencias y las acciones: observar, validar como formador y ajustar el nivel.

import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, Award, CalendarClock, Eye, Factory, Grid3x3, RefreshCw, Search, ShieldAlert, SlidersHorizontal,
  Timer, TrendingUp, Users,
} from 'lucide-react'
import { fecha, get, post, put } from '../../api'
import { useSesion } from '../../sesion'
import {
  Area, Avatar, Boton, Cabecera, Campo, Dato, ErrorCarga, Esqueleto, Etiqueta, Iluo, LETRA_ILUO, Modal, NOMBRE_ILUO,
  Selector, Tarjeta, useAvisarError, useAvisos, useConfirmar, useDatos, Vacio,
} from '../../ui'
import DetalleTarea from './DetalleTarea'
import Pasaporte from './Pasaporte'
import { duracionDias, type AvisoNivel, type Celda, type DetalleCelda, type Matriz, type Planta, type Progreso } from './tipos'
import './progreso.css'

// ------------------------------------------------------------------ detalle de una celda

function FormAjuste({ d, alGuardar }: { d: DetalleCelda; alGuardar: () => void }) {
  const [nivel, setNivel] = useState(String(d.nivel))
  const [motivo, setMotivo] = useState('')
  const [guardando, setGuardando] = useState(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  async function guardar() {
    setGuardando(true)
    try {
      await put(`/api/progreso/iluo/${d.persona.id}/${d.tarea.id}`, { nivel: Number(nivel), motivo })
      avisar(`Nivel de ${d.persona.nombre} ajustado a ${LETRA_ILUO[Number(nivel)] === '·' ? 'sin iniciar' : LETRA_ILUO[Number(nivel)]}.`)
      alGuardar()
    } catch (e) {
      avisarError(e)
    } finally {
      setGuardando(false)
    }
  }
  return (
    <div className="mz-ajuste">
      <div className="rejilla c2" style={{ gap: 12 }}>
        <Campo etiqueta="Nuevo nivel">
          <Selector value={nivel} onChange={(e) => setNivel(e.target.value)}
            opciones={[0, 1, 2, 3, 4].map((n) => ({ valor: n, texto: n ? `${LETRA_ILUO[n]} · ${NOMBRE_ILUO[n]}` : 'Sin iniciar' }))} />
        </Campo>
        <div className="pequeno apagado" style={{ alignSelf: 'center' }}>
          Si bajas el nivel, las evidencias anteriores dejan de contar y tendrá que volver a demostrarlo.
        </div>
      </div>
      <Campo etiqueta="Motivo" ayuda="Queda en el registro de auditoría.">
        <Area value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={2}
          placeholder="Por ejemplo: lleva años haciendo esta tarea en la otra planta." />
      </Campo>
      <div className="fila" style={{ justifyContent: 'flex-end' }}>
        <Boton variante="oscuro" cargando={guardando} disabled={motivo.trim().length < 5 || Number(nivel) === d.nivel}
          onClick={guardar}>Guardar ajuste</Boton>
      </div>
    </div>
  )
}

function ModalCelda({ usuarioId, tareaId, onCerrar, onCambio }: {
  usuarioId: number; tareaId: number; onCerrar: () => void; onCambio: () => void
}) {
  const navegar = useNavigate()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const [ajustando, setAjustando] = useState(false)
  const [validando, setValidando] = useState(false)
  const { datos: d, error, recargar } = useDatos(
    (s) => get<DetalleCelda>(`/api/progreso/iluo/${usuarioId}/${tareaId}`, s), [usuarioId, tareaId])

  async function validarFormador() {
    if (!d) return
    const ok = await confirmar('Validar como formador',
      <>{d.persona.nombre} pasará al nivel O en «{d.tarea.nombre}» y podrá formar a otras personas en esta tarea.</>)
    if (!ok) return
    setValidando(true)
    try {
      await post(`/api/progreso/iluo/${d.persona.id}/${d.tarea.id}/formador`)
      avisar(`${d.persona.nombre} ya puede formar a otros en esta tarea.`)
      recargar()
      onCambio()
    } catch (e) {
      avisarError(e)
    } finally {
      setValidando(false)
    }
  }

  const acciones = d && (
    <>
      {d.acciones.observar && (
        <Boton variante="primario" icono={<Eye />}
          onClick={() => navegar(`/evaluacion?pestana=observar&usuario=${d.persona.id}&tarea=${d.tarea.id}`)}>
          Observar en el puesto
        </Boton>
      )}
      {d.acciones.validar_formador && (
        <Boton variante="verde" icono={<Award />} cargando={validando} onClick={validarFormador}>Validar como formador</Boton>
      )}
      {d.acciones.ajustar && (
        <Boton variante={ajustando ? 'oscuro' : 'secundario'} icono={<SlidersHorizontal />} onClick={() => setAjustando(!ajustando)}>
          Ajustar nivel
        </Boton>
      )}
    </>
  )

  return (
    <Modal abierto ancho titulo={d ? `${d.persona.nombre} · ${d.tarea.nombre}` : 'Cargando…'} onCerrar={onCerrar}>
      {error ? <ErrorCarga error={error} reintentar={recargar} /> : !d ? (
        <div className="columna" style={{ gap: 12 }}><Esqueleto alto={120} /><Esqueleto alto={200} /></div>
      ) : (
        <div className="columna mz-modal" style={{ gap: 12 }}>
          {ajustando && d.acciones.ajustar && (
            <Tarjeta titulo="Ajuste manual del nivel" icono={<SlidersHorizontal size={18} />}>
              <FormAjuste d={d} alGuardar={() => { setAjustando(false); recargar(); onCambio() }} />
            </Tarjeta>
          )}
          <DetalleTarea t={d} acciones={acciones} persona={d.persona.nombre} />
        </div>
      )}
      {dialogo}
    </Modal>
  )
}

function ModalPersona({ usuarioId, onCerrar }: { usuarioId: number; onCerrar: () => void }) {
  const { datos, error, recargar } = useDatos((s) => get<Progreso>(`/api/progreso/persona/${usuarioId}`, s), [usuarioId])
  return (
    <Modal abierto ancho titulo={datos ? `Pasaporte de ${datos.persona.nombre}` : 'Cargando…'} onCerrar={onCerrar}>
      {error ? <ErrorCarga error={error} reintentar={recargar} /> : !datos ? <Esqueleto alto={260} /> : datos.tareas.length === 0
        ? <Vacio titulo="Sin tareas en su itinerario">Aún no tiene un puesto o una formación con tareas.</Vacio>
        : <div className="mz-pasaporte-modal"><Pasaporte datos={datos} /></div>}
    </Modal>
  )
}

// ------------------------------------------------------------------ matriz

function TablaMatriz({ m, filtro, onCelda, onPersona }: {
  m: Matriz; filtro: string; onCelda: (u: number, t: number) => void; onPersona: (u: number) => void
}) {
  const celdas = useMemo(() => {
    const mapa = new Map<string, Celda>()
    m.celdas.forEach((c) => mapa.set(`${c.usuario_id}-${c.tarea_id}`, c))
    return mapa
  }, [m.celdas])
  const cobertura = useMemo(() => new Map(m.indicadores?.personas_por_tarea.map((p) => [p.tarea_id, p]) ?? []), [m.indicadores])
  const texto = filtro.trim().toLowerCase()
  const personas = m.personas.filter((p) => !texto || p.nombre.toLowerCase().includes(texto))

  if (!m.tareas.length || !m.personas.length) {
    return (
      <Vacio icono={<Grid3x3 />} titulo={!m.tareas.length ? 'Este departamento aún no tiene tareas' : 'Este departamento aún no tiene personas'}>
        La matriz se llena cuando hay tareas en los puestos del departamento y personas asignadas o en formación.
      </Vacio>
    )
  }
  return (
    <div className="mz-envoltorio">
      <table className="mz-tabla">
        <thead>
          <tr>
            <th className="mz-esquina">Persona</th>
            {m.tareas.map((t) => {
              const c = cobertura.get(t.id)
              return (
                <th key={t.id} className="mz-tarea" title={`${t.nombre}${t.puesto ? ` · ${t.puesto}` : ''}`}>
                  {t.codigo && <div className="mz-tarea-codigo">{t.codigo}</div>}
                  <div className="mz-tarea-nombre">{t.nombre}</div>
                  {c && (
                    <div className={`mz-cobertura ${c.u_o_mas < 2 ? 'riesgo' : ''}`}>
                      {c.l_o_mas} en L+ · {c.u_o_mas} en U+
                    </div>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {personas.map((p) => (
            <tr key={p.id}>
              <th className="mz-persona">
                <button onClick={() => onPersona(p.id)} title="Ver su pasaporte">
                  <Avatar nombre={p.nombre} iniciales={p.iniciales} tamano="p" />
                  <span className="crece">
                    <span className="recortar" style={{ display: 'block' }}>{p.nombre}</span>
                    {p.en_formacion
                      ? <span className="diminuto mz-formacion">En formación</span>
                      : p.puesto && <span className="diminuto apagado recortar" style={{ display: 'block' }}>{p.puesto}</span>}
                  </span>
                </button>
              </th>
              {m.tareas.map((t) => {
                const c = celdas.get(`${p.id}-${t.id}`)
                const nivel = c?.nivel ?? 0
                const estado = c?.caducado ? ' (caducado)' : c?.requiere_reevaluacion ? ' (reevaluación pendiente)' : ''
                return (
                  <td key={t.id}>
                    <button className={`mz-celda ${nivel ? '' : 'vacia'}`} onClick={() => onCelda(p.id, t.id)}
                      aria-label={`${p.nombre} · ${t.nombre}: ${NOMBRE_ILUO[nivel]}${estado}`}
                      title={`${p.nombre} · ${t.nombre}\n${nivel ? `${LETRA_ILUO[nivel]} · ` : ''}${NOMBRE_ILUO[nivel]}${estado}${c?.caduca ? `\nVálido hasta ${fecha(c.caduca)}` : ''}`}>
                      <Iluo nivel={nivel} tamano={30} caducado={c?.caducado} />
                      {c?.requiere_reevaluacion && <span className="mz-marca reevaluacion" />}
                      {c?.formador_validado && <Award className="mz-marca-formador" size={12} />}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
          {!personas.length && (
            <tr><td colSpan={m.tareas.length + 1} className="centro apagado pequeno" style={{ padding: 24 }}>
              Nadie coincide con «{filtro}».
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function Leyenda() {
  return (
    <div className="mz-leyenda">
      {[0, 1, 2, 3, 4].map((n) => (
        <span key={n} className="fila" style={{ gap: 6 }}>
          <Iluo nivel={n} tamano={18} /> {n ? `${LETRA_ILUO[n]} · ` : ''}{NOMBRE_ILUO[n]}
        </span>
      ))}
      <span className="fila" style={{ gap: 6 }}><Iluo nivel={3} tamano={18} caducado /> Caducado</span>
      <span className="fila" style={{ gap: 6 }}><span className="mz-marca reevaluacion estatica" /> Reevaluación pendiente</span>
      <span className="fila" style={{ gap: 6 }}><Award size={14} className="pp-icono-formador" /> Formador validado</span>
    </div>
  )
}

function ListaAvisos({ titulo, icono, avisos, vacio, detalle, onAbrir }: {
  titulo: string; icono: ReactNode; avisos: AvisoNivel[]; vacio: string
  detalle: (a: AvisoNivel) => ReactNode; onAbrir: (a: AvisoNivel) => void
}) {
  return (
    <Tarjeta titulo={titulo} icono={icono} acciones={<span className="pequeno apagado">{avisos.length}</span>}>
      {avisos.length === 0 ? <div className="pequeno apagado">{vacio}</div> : (
        <div className="columna" style={{ gap: 4 }}>
          {avisos.slice(0, 12).map((a) => (
            <button key={`${a.usuario_id}-${a.tarea_id}`} className="mz-aviso" onClick={() => onAbrir(a)}>
              <Iluo nivel={a.nivel} tamano={24} caducado={a.caducado} />
              <span className="crece" style={{ minWidth: 0 }}>
                <span className="negrita pequeno recortar" style={{ display: 'block' }}>{a.nombre}</span>
                <span className="diminuto apagado recortar" style={{ display: 'block' }}>{a.tarea}</span>
              </span>
              {detalle(a)}
            </button>
          ))}
          {avisos.length > 12 && <div className="diminuto apagado">Y {avisos.length - 12} más.</div>}
        </div>
      )}
    </Tarjeta>
  )
}

function ResumenPlanta({ depId, onElegir }: { depId: number | null; onElegir: (id: number) => void }) {
  const { datos, error, recargar } = useDatos((s) => get<Planta>('/api/progreso/planta', s), [])
  return (
    <Tarjeta titulo="Toda la planta" icono={<Factory size={18} />} relleno={false}>
      {error ? <ErrorCarga error={error} reintentar={recargar} /> : !datos ? <div className="tarjeta-cuerpo"><Esqueleto alto={90} /></div> : (
        <div className="tabla-envoltorio">
          <table className="tabla">
            <thead>
              <tr>
                <th>Departamento</th><th>Personas</th><th>Tareas</th><th>Niveles L o más</th>
                <th>Tareas con riesgo</th><th>Reevaluaciones</th><th>Caducan pronto</th><th>Primera ejecución correcta</th>
              </tr>
            </thead>
            <tbody>
              {datos.departamentos.map((d) => (
                <tr key={d.id} className={`pulsable ${d.id === depId ? 'mz-dep-activo' : ''}`} onClick={() => onElegir(d.id)}>
                  <td className="negrita">{d.nombre}</td>
                  <td>{d.personas}</td>
                  <td>{d.tareas}</td>
                  <td>{d.celdas_l_o_mas} <span className="diminuto apagado">({d.polivalencia} por persona)</span></td>
                  <td>{d.tareas_con_riesgo ? <Etiqueta tono="roja">{d.tareas_con_riesgo}</Etiqueta> : <Etiqueta tono="verde">0</Etiqueta>}</td>
                  <td>{d.reevaluaciones}</td>
                  <td>{d.caducidades}</td>
                  <td>{duracionDias(d.tiempo_medio_dias)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Tarjeta>
  )
}

// ------------------------------------------------------------------ página

export default function Equipo() {
  const { perfil } = useSesion()
  const esAdmin = perfil?.rol === 'admin'
  const [depId, setDepId] = useState<number | null>(null)
  const [filtro, setFiltro] = useState('')
  const [celda, setCelda] = useState<{ u: number; t: number } | null>(null)
  const [persona, setPersona] = useState<number | null>(null)
  const { datos: m, error, cargando, recargar } = useDatos(
    (s) => get<Matriz>(`/api/progreso/equipo${depId ? `?departamento_id=${depId}` : ''}`, s), [depId])
  const ind = m?.indicadores

  return (
    <>
      <Cabecera
        antetitulo="Matriz ILUO"
        titulo="Progreso del equipo"
        subtitulo={m?.departamento
          ? <>Quién domina cada tarea de <strong>{m.departamento.nombre}</strong>, con qué nivel y hasta cuándo. Pulsa una celda para ver sus evidencias.</>
          : 'Quién domina cada tarea, con qué nivel y hasta cuándo.'}
        acciones={<>
          {esAdmin && m && m.departamentos.length > 0 && (
            <Selector aria-label="Departamento" value={m.departamento?.id ?? ''} style={{ minWidth: 200 }}
              onChange={(e) => setDepId(Number(e.target.value))}
              opciones={m.departamentos.map((d) => ({ valor: d.id, texto: d.nombre }))} />
          )}
          <Boton variante="fantasma" icono={<RefreshCw />} cargando={cargando && !!m} onClick={recargar}>Actualizar</Boton>
        </>}
      />

      {error ? <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta> : !m ? (
        <div className="columna" style={{ gap: 16 }}>
          <div className="rejilla c4">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={76} />)}</div>
          <Esqueleto alto={320} />
        </div>
      ) : !m.departamento ? (
        <Tarjeta><Vacio icono={<Grid3x3 />} titulo="Aún no hay departamentos">Crea la organización para ver la matriz.</Vacio></Tarjeta>
      ) : (
        <div className="columna" style={{ gap: 18 }}>
          {ind && (
            <div className="rejilla c4">
              <Dato icono={<Users />} valor={ind.personas} etiqueta={`personas · ${ind.tareas} ${ind.tareas === 1 ? 'tarea' : 'tareas'}`} />
              <Dato icono={<TrendingUp />} tono="verde" valor={ind.celdas_l_o_mas}
                etiqueta={`niveles L o más · ${ind.polivalencia.toLocaleString('es-ES')} por persona`} />
              <Dato icono={<ShieldAlert />} tono={ind.tareas_con_riesgo ? 'alerta' : 'verde'} valor={ind.tareas_con_riesgo}
                etiqueta="tareas con menos de 2 personas autónomas" />
              <Dato icono={<Timer />} tono="info" valor={duracionDias(ind.tiempo_medio_primera_correcta.dias)}
                etiqueta={`hasta la primera ejecución correcta${ind.tiempo_medio_primera_correcta.muestras ? ` (${ind.tiempo_medio_primera_correcta.muestras})` : ''}`} />
            </div>
          )}

          {esAdmin && <ResumenPlanta depId={m.departamento.id} onElegir={setDepId} />}

          <Tarjeta titulo="Matriz ILUO" icono={<Grid3x3 size={18} />} relleno={false}
            acciones={
              <div className="entrada-icono" style={{ width: 220 }}>
                <Search />
                <input className="entrada" placeholder="Buscar persona" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
              </div>
            }>
            <TablaMatriz m={m} filtro={filtro} onCelda={(u, t) => setCelda({ u, t })} onPersona={setPersona} />
            <Leyenda />
          </Tarjeta>

          {ind && (
            <div className="rejilla c2">
              <ListaAvisos titulo="Caducidades próximas" icono={<CalendarClock size={18} />} avisos={ind.caducidades_proximas}
                vacio="Ningún nivel caduca en los próximos 60 días."
                detalle={(a) => a.caducado
                  ? <Etiqueta tono="roja" icono={<AlertTriangle />}>Caducado</Etiqueta>
                  : <Etiqueta tono="naranja">{a.dias === 0 ? 'Hoy' : `${a.dias} días`}</Etiqueta>}
                onAbrir={(a) => setCelda({ u: a.usuario_id, t: a.tarea_id })} />
              <ListaAvisos titulo="Reevaluaciones pendientes" icono={<RefreshCw size={18} />} avisos={ind.reevaluaciones_pendientes}
                vacio="Nadie tiene reevaluaciones pendientes."
                detalle={() => <Etiqueta tono="amarilla">Versión nueva</Etiqueta>}
                onAbrir={(a) => setCelda({ u: a.usuario_id, t: a.tarea_id })} />
            </div>
          )}
        </div>
      )}

      {celda && <ModalCelda usuarioId={celda.u} tareaId={celda.t} onCerrar={() => setCelda(null)} onCambio={recargar} />}
      {persona !== null && <ModalPersona usuarioId={persona} onCerrar={() => setPersona(null)} />}
    </>
  )
}
