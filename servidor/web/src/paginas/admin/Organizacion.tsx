// Administración · Organización: árbol departamentos → puestos → tareas con su formulario,
// niveles de responsabilidad (ordenables) y datos de la empresa con las reglas ILUO.

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  ArrowDown, ArrowUp, Briefcase, Building2, ChevronDown, ChevronRight, ClipboardList, Factory, GripVertical, Layers,
  Network, Pencil, Plus, RotateCcw, Save, Search, ShieldAlert, Trash2, Users,
} from 'lucide-react'
import { del, get, post, put } from '../../api'
import {
  Area, Aviso, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Iluo, Interruptor, Modal, Pestanas,
  Selector, Tarjeta, Vacio, useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import { CRITICIDAD, PALETA, type Departamento, type Empresa, type Nivel, type Organizacion as Org, type Puesto, type Tarea } from './tipos'
import './admin.css'

type Seleccion =
  | { tipo: 'departamento'; id: number }
  | { tipo: 'puesto'; id: number }
  | { tipo: 'tarea'; id: number }
  | { tipo: 'nuevo-departamento' }
  | { tipo: 'nuevo-puesto'; departamento_id: number }
  | { tipo: 'nueva-tarea'; puesto_id: number }

type IdPestana = 'estructura' | 'niveles' | 'empresa'

export default function Organizacion() {
  const [pestana, setPestana] = useState<IdPestana>('estructura')
  const [sel, setSel] = useState<Seleccion | null>(null)
  const org = useDatos((s) => get<Org>('/api/admin/organizacion', s), [])

  return (
    <>
      <Cabecera
        antetitulo={<><Network size={14} /> Administración</>}
        titulo="Organización"
        subtitulo="Departamentos, puestos y tareas de la planta, niveles de responsabilidad y reglas para certificar el nivel ILUO."
        acciones={pestana === 'estructura' && (
          <Boton variante="primario" icono={<Plus />} onClick={() => setSel({ tipo: 'nuevo-departamento' })}>
            Nuevo departamento
          </Boton>
        )}
      />
      <Pestanas<IdPestana>
        activa={pestana}
        onCambio={setPestana}
        pestanas={[
          { id: 'estructura', texto: 'Departamentos y tareas', icono: <Factory size={16} /> },
          { id: 'niveles', texto: 'Niveles', icono: <Layers size={16} />, contador: org.datos?.niveles.length },
          { id: 'empresa', texto: 'Empresa y reglas ILUO', icono: <Building2 size={16} /> },
        ]}
      />
      {org.error && !org.datos ? (
        <Tarjeta><ErrorCarga error={org.error} reintentar={org.recargar} /></Tarjeta>
      ) : pestana === 'estructura' ? (
        <Estructura org={org.datos} cargando={org.cargando} sel={sel} setSel={setSel} recargar={org.recargar} />
      ) : pestana === 'niveles' ? (
        <Niveles niveles={org.datos?.niveles ?? null} recargar={org.recargar} />
      ) : (
        <EmpresaReglas />
      )}
    </>
  )
}

// ------------------------------------------------------------------ estructura (árbol + formulario)

function Estructura({ org, cargando, sel, setSel, recargar }: {
  org: Org | null; cargando: boolean; sel: Seleccion | null; setSel: (s: Seleccion | null) => void; recargar: () => void
}) {
  const [filtro, setFiltro] = useState('')
  const [plegados, setPlegados] = useState<Set<string>>(new Set())

  // Índices para encontrar cada elemento por id.
  const indice = useMemo(() => {
    const deps = new Map<number, Departamento>()
    const puestos = new Map<number, Puesto>()
    const tareas = new Map<number, Tarea>()
    for (const d of org?.departamentos ?? []) {
      deps.set(d.id, d)
      for (const p of d.puestos) {
        puestos.set(p.id, p)
        for (const t of p.tareas) tareas.set(t.id, t)
      }
    }
    return { deps, puestos, tareas }
  }, [org])

  // Filtro: un elemento se muestra si coincide él o algo que cuelga de él.
  const arbol = useMemo(() => {
    const deps = org?.departamentos ?? []
    const f = filtro.trim().toLowerCase()
    if (!f) return deps
    const coincide = (...textos: (string | null)[]) => textos.some((t) => t?.toLowerCase().includes(f))
    return deps
      .map((d) => {
        if (coincide(d.nombre, d.codigo)) return d
        const puestos = d.puestos
          .map((p) => (coincide(p.nombre) ? p : { ...p, tareas: p.tareas.filter((t) => coincide(t.nombre, t.codigo)) }))
          .filter((p) => coincide(p.nombre) || p.tareas.length)
        return { ...d, puestos }
      })
      .filter((d) => coincide(d.nombre, d.codigo) || d.puestos.length)
  }, [org, filtro])

  const alternar = (clave: string) => setPlegados((p) => {
    const n = new Set(p)
    if (n.has(clave)) n.delete(clave)
    else n.add(clave)
    return n
  })
  const esActivo = (tipo: string, id: number) => sel && 'id' in sel && sel.tipo === tipo && sel.id === id

  const r = org?.resumen
  return (
    <>
      {r && (
        <div className="adm-resumen">
          <span><strong>{r.departamentos}</strong> departamentos</span>
          <span><strong>{r.puestos}</strong> puestos</span>
          <span><strong>{r.tareas_activas}</strong> tareas activas{r.tareas !== r.tareas_activas && ` de ${r.tareas}`}</span>
          <span><strong>{r.personas}</strong> personas asignadas</span>
        </div>
      )}
      <div className="adm-org">
        <div className="tarjeta adm-arbol">
          <div className="adm-arbol-busca">
            <div className="entrada-icono">
              <Search />
              <Entrada placeholder="Buscar departamento, puesto o tarea" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
            </div>
          </div>
          <div className="adm-arbol-lista">
            {!org ? (
              <div className="columna" style={{ padding: 8 }}>
                {[0, 1, 2, 3, 4, 5].map((i) => <Esqueleto key={i} alto={28} ancho={i % 3 === 0 ? '70%' : '85%'} />)}
              </div>
            ) : !arbol.length ? (
              <Vacio icono={<Factory />} titulo={filtro ? 'Nada coincide' : 'Aún no hay departamentos'}>
                {filtro ? 'Prueba con otra palabra o un código de tarea.' : 'Empieza creando el primer departamento de la planta.'}
              </Vacio>
            ) : arbol.map((d) => {
              const abiertoDep = !!filtro || !plegados.has(`d${d.id}`)
              return (
                <div key={d.id}>
                  <button className={`adm-nodo dep ${esActivo('departamento', d.id) ? 'activo' : ''}`}
                    onClick={() => setSel({ tipo: 'departamento', id: d.id })}>
                    <span className="plegar" role="button" aria-label={abiertoDep ? 'Plegar' : 'Desplegar'}
                      onClick={(e) => { e.stopPropagation(); alternar(`d${d.id}`) }}>
                      {abiertoDep ? <ChevronDown /> : <ChevronRight />}
                    </span>
                    <span className="adm-color" style={{ background: d.color ?? undefined }} />
                    <span className="nombre">{d.nombre}</span>
                    <span className="cuenta" title="Personas del departamento"><Users />{d.n_personas}</span>
                  </button>
                  {abiertoDep && (
                    <>
                      {d.puestos.map((p) => {
                        const abiertoPuesto = !!filtro || !plegados.has(`p${p.id}`)
                        return (
                          <div key={p.id}>
                            <button className={`adm-nodo puesto ${esActivo('puesto', p.id) ? 'activo' : ''}`}
                              onClick={() => setSel({ tipo: 'puesto', id: p.id })}>
                              <span className="plegar" role="button" aria-label={abiertoPuesto ? 'Plegar' : 'Desplegar'}
                                onClick={(e) => { e.stopPropagation(); alternar(`p${p.id}`) }}>
                                {abiertoPuesto ? <ChevronDown /> : <ChevronRight />}
                              </span>
                              <Briefcase style={{ color: d.color ?? undefined }} />
                              <span className="nombre">{p.nombre}</span>
                              <span className="cuenta">{p.tareas.length} {p.tareas.length === 1 ? 'tarea' : 'tareas'}</span>
                            </button>
                            {abiertoPuesto && (
                              <>
                                {p.tareas.map((t) => (
                                  <button key={t.id}
                                    className={`adm-nodo tarea ${t.activa ? '' : 'inactiva'} ${esActivo('tarea', t.id) ? 'activo' : ''}`}
                                    onClick={() => setSel({ tipo: 'tarea', id: t.id })}
                                    title={t.activa ? undefined : 'Tarea desactivada'}>
                                    <span className={`adm-critico c${t.criticidad}`} title={`Criticidad ${CRITICIDAD[t.criticidad - 1]?.texto.toLowerCase()}`} />
                                    {t.codigo && <span className="codigo">{t.codigo}</span>}
                                    <span className="nombre">{t.nombre}</span>
                                  </button>
                                ))}
                                {!filtro && (
                                  <button className="adm-nodo anadir tarea" onClick={() => setSel({ tipo: 'nueva-tarea', puesto_id: p.id })}>
                                    <Plus /> Añadir tarea
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        )
                      })}
                      {!filtro && (
                        <button className="adm-nodo anadir puesto" onClick={() => setSel({ tipo: 'nuevo-puesto', departamento_id: d.id })}>
                          <Plus /> Añadir puesto
                        </button>
                      )}
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <div>
          <PanelElemento org={org} cargando={cargando} indice={indice} sel={sel} setSel={setSel} recargar={recargar} />
        </div>
      </div>
    </>
  )
}

interface Indice { deps: Map<number, Departamento>; puestos: Map<number, Puesto>; tareas: Map<number, Tarea> }

function PanelElemento({ org, cargando, indice, sel, setSel, recargar }: {
  org: Org | null; cargando: boolean; indice: Indice; sel: Seleccion | null; setSel: (s: Seleccion | null) => void
  recargar: () => void
}) {
  // Recién creado: hasta que llega el árbol actualizado aún no está en el índice.
  const pendiente = sel && 'id' in sel && cargando && !(
    (sel.tipo === 'departamento' && indice.deps.has(sel.id)) || (sel.tipo === 'puesto' && indice.puestos.has(sel.id))
    || (sel.tipo === 'tarea' && indice.tareas.has(sel.id)))
  if (!org || pendiente) {
    return <Tarjeta><div className="columna"><Esqueleto alto={46} ancho={260} /><Esqueleto alto={40} /><Esqueleto alto={40} /><Esqueleto alto={90} /></div></Tarjeta>
  }
  if (!sel) {
    return (
      <Tarjeta>
        <Vacio icono={<Network />} titulo="Elige un elemento del árbol">
          Selecciona un departamento, un puesto o una tarea para ver y editar sus datos. Las tareas son la unidad de
          formación y de certificación ILUO: cada instrucción, micro-lección y evaluación cuelga de una tarea.
        </Vacio>
      </Tarjeta>
    )
  }
  const alGuardar = (s: Seleccion) => { recargar(); setSel(s) }
  const alBorrar = () => { recargar(); setSel(null) }
  switch (sel.tipo) {
    case 'departamento':
    case 'nuevo-departamento': {
      const d = sel.tipo === 'departamento' ? indice.deps.get(sel.id) : undefined
      if (sel.tipo === 'departamento' && !d) return <NoEncontrado />
      return <FormDepartamento key={d?.id ?? 'nuevo'} dep={d} n={org.departamentos.length} onGuardado={alGuardar} onBorrado={alBorrar}
        onAnadirPuesto={(id) => setSel({ tipo: 'nuevo-puesto', departamento_id: id })} />
    }
    case 'puesto':
    case 'nuevo-puesto': {
      const p = sel.tipo === 'puesto' ? indice.puestos.get(sel.id) : undefined
      if (sel.tipo === 'puesto' && !p) return <NoEncontrado />
      const depId = p?.departamento_id ?? (sel.tipo === 'nuevo-puesto' ? sel.departamento_id : 0)
      return <FormPuesto key={p?.id ?? `nuevo-${depId}`} puesto={p} departamentoId={depId} org={org} onGuardado={alGuardar}
        onBorrado={alBorrar} onAnadirTarea={(id) => setSel({ tipo: 'nueva-tarea', puesto_id: id })} />
    }
    case 'tarea':
    case 'nueva-tarea': {
      const t = sel.tipo === 'tarea' ? indice.tareas.get(sel.id) : undefined
      if (sel.tipo === 'tarea' && !t) return <NoEncontrado />
      const puestoId = t?.puesto_id ?? (sel.tipo === 'nueva-tarea' ? sel.puesto_id : 0)
      return <FormTarea key={t?.id ?? `nueva-${puestoId}`} tarea={t} puestoId={puestoId} org={org} indice={indice}
        onGuardado={alGuardar} onBorrado={alBorrar} />
    }
  }
}

function NoEncontrado() {
  return <Tarjeta><Vacio icono={<Search />} titulo="Ya no existe">Puede que otra persona lo haya borrado. Elige otro elemento.</Vacio></Tarjeta>
}

function CabeceraPanel({ icono, color, titulo, migas, extra }: {
  icono: ReactNode; color?: string | null; titulo: ReactNode; migas?: ReactNode; extra?: ReactNode
}) {
  return (
    <div className="fila entre envolver mb-2">
      <div className="adm-panel-cabecera">
        <div className="adm-icono-tipo" style={{ background: color ?? undefined }}>{icono}</div>
        <div style={{ minWidth: 0 }}>
          {migas && <div className="adm-migas">{migas}</div>}
          <h2 className="recortar">{titulo}</h2>
        </div>
      </div>
      {extra}
    </div>
  )
}

/** Guarda con avisos de éxito y error, y bloqueo del botón mientras tanto. */
function useGuardar() {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const [guardando, setGuardando] = useState(false)
  const ejecutar = async <T,>(accion: () => Promise<T>, mensaje: string): Promise<T | null> => {
    setGuardando(true)
    try {
      const r = await accion()
      avisar(mensaje)
      return r
    } catch (e) {
      avisarError(e)
      return null
    } finally {
      setGuardando(false)
    }
  }
  return { guardando, ejecutar }
}

// ------------------------------------------------------------------ formulario de departamento

function FormDepartamento({ dep, n, onGuardado, onBorrado, onAnadirPuesto }: {
  dep?: Departamento; n: number; onGuardado: (s: Seleccion) => void; onBorrado: () => void; onAnadirPuesto: (id: number) => void
}) {
  const [nombre, setNombre] = useState(dep?.nombre ?? '')
  const [codigo, setCodigo] = useState(dep?.codigo ?? '')
  const [descripcion, setDescripcion] = useState(dep?.descripcion ?? '')
  const [color, setColor] = useState(dep?.color ?? PALETA[n % PALETA.length])
  const { guardando, ejecutar } = useGuardar()
  const { confirmar, dialogo } = useConfirmar()

  const guardar = async () => {
    const cuerpo = { nombre, codigo, descripcion, color }
    const r = dep
      ? await ejecutar(() => put<Departamento>(`/api/admin/departamentos/${dep.id}`, cuerpo), 'Departamento guardado')
      : await ejecutar(() => post<Departamento>('/api/admin/departamentos', cuerpo), 'Departamento creado')
    if (r) onGuardado({ tipo: 'departamento', id: r.id })
  }
  const borrar = async () => {
    if (!dep) return
    const ok = await confirmar('¿Borrar el departamento?',
      <>Se borrará «{dep.nombre}» con sus puestos y tareas vacías. Si tiene personas, documentos o historial, CidIA no lo permitirá y te dirá qué mover antes.</>, true)
    if (ok && (await ejecutar(() => del(`/api/admin/departamentos/${dep.id}`), 'Departamento borrado')) !== null) onBorrado()
  }
  const tareas = dep?.puestos.reduce((a, p) => a + p.tareas.length, 0) ?? 0

  return (
    <Tarjeta
      pie={<>
        {dep && <Boton variante="peligro" icono={<Trash2 />} onClick={borrar} style={{ marginRight: 'auto' }}>Borrar</Boton>}
        {dep && <Boton icono={<Plus />} onClick={() => onAnadirPuesto(dep.id)}>Añadir puesto</Boton>}
        <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={!nombre.trim()} onClick={guardar}>
          {dep ? 'Guardar cambios' : 'Crear departamento'}
        </Boton>
      </>}
    >
      <CabeceraPanel icono={<Factory />} color={color} titulo={dep ? dep.nombre : 'Nuevo departamento'}
        migas={<>Departamento</>} />
      {dep && (
        <div className="adm-cifras mb-2">
          <div className="adm-cifra"><strong>{dep.n_personas}</strong>personas</div>
          <div className="adm-cifra"><strong>{dep.puestos.length}</strong>puestos</div>
          <div className="adm-cifra"><strong>{tareas}</strong>tareas</div>
        </div>
      )}
      <div className="adm-form-rejilla">
        <Campo etiqueta="Nombre">
          <Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Producción" autoFocus={!dep} maxLength={150} />
        </Campo>
        <Campo etiqueta="Código" ayuda="Abreviatura opcional, p. ej. PROD.">
          <Entrada value={codigo} onChange={(e) => setCodigo(e.target.value.toUpperCase())} placeholder="PROD" maxLength={30} />
        </Campo>
        <div className="completo">
          <Campo etiqueta="Descripción">
            <Area value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={3}
              placeholder="Qué hace este departamento y qué conocimiento guarda." />
          </Campo>
        </div>
        <div className="completo">
          <Campo etiqueta="Color" ayuda="Ayuda a reconocer el departamento en listas, etiquetas y en el árbol.">
            <div className="adm-colores">
              {PALETA.map((c) => (
                <button key={c} type="button" className={`adm-muestra ${color.toUpperCase() === c ? 'activa' : ''}`}
                  style={{ background: c }} onClick={() => setColor(c)} aria-label={`Color ${c}`} />
              ))}
              <input type="color" value={color} onChange={(e) => setColor(e.target.value.toUpperCase())} title="Otro color" />
            </div>
          </Campo>
        </div>
      </div>
      {dialogo}
    </Tarjeta>
  )
}

// ------------------------------------------------------------------ formulario de puesto

function FormPuesto({ puesto, departamentoId, org, onGuardado, onBorrado, onAnadirTarea }: {
  puesto?: Puesto; departamentoId: number; org: Org; onGuardado: (s: Seleccion) => void; onBorrado: () => void
  onAnadirTarea: (id: number) => void
}) {
  const [depId, setDepId] = useState(String(departamentoId))
  const [nombre, setNombre] = useState(puesto?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(puesto?.descripcion ?? '')
  const { guardando, ejecutar } = useGuardar()
  const { confirmar, dialogo } = useConfirmar()
  const dep = org.departamentos.find((d) => d.id === Number(depId))
  // Si sus tareas ya tienen instrucciones, el puesto no puede cambiar de departamento.
  const fijo = !!puesto && puesto.tareas.some((t) => t.n_instrucciones > 0)

  const guardar = async () => {
    const cuerpo = { departamento_id: Number(depId), nombre, descripcion }
    const r = puesto
      ? await ejecutar(() => put<Puesto>(`/api/admin/puestos/${puesto.id}`, cuerpo), 'Puesto guardado')
      : await ejecutar(() => post<Puesto>('/api/admin/puestos', cuerpo), 'Puesto creado')
    if (r) onGuardado({ tipo: 'puesto', id: r.id })
  }
  const borrar = async () => {
    if (!puesto) return
    const ok = await confirmar('¿Borrar el puesto?',
      <>Se borrará «{puesto.nombre}» y sus tareas sin historial. Si hay personas asignadas o tareas con instrucciones, no se podrá.</>, true)
    if (ok && (await ejecutar(() => del(`/api/admin/puestos/${puesto.id}`), 'Puesto borrado')) !== null) onBorrado()
  }

  return (
    <Tarjeta
      pie={<>
        {puesto && <Boton variante="peligro" icono={<Trash2 />} onClick={borrar} style={{ marginRight: 'auto' }}>Borrar</Boton>}
        {puesto && <Boton icono={<Plus />} onClick={() => onAnadirTarea(puesto.id)}>Añadir tarea</Boton>}
        <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={!nombre.trim() || !depId} onClick={guardar}>
          {puesto ? 'Guardar cambios' : 'Crear puesto'}
        </Boton>
      </>}
    >
      <CabeceraPanel icono={<Briefcase />} color={dep?.color} titulo={puesto ? puesto.nombre : 'Nuevo puesto'}
        migas={<><span className="adm-color" style={{ background: dep?.color ?? undefined }} />{dep?.nombre ?? 'Departamento'}<ChevronRight />Puesto</>} />
      {puesto && (
        <div className="adm-cifras mb-2">
          <div className="adm-cifra"><strong>{puesto.n_personas}</strong>personas en este puesto</div>
          <div className="adm-cifra"><strong>{puesto.tareas.length}</strong>tareas</div>
        </div>
      )}
      <div className="adm-form-rejilla">
        <Campo etiqueta="Nombre del puesto">
          <Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Montaje línea 2" autoFocus={!puesto} maxLength={150} />
        </Campo>
        <Campo etiqueta="Departamento"
          ayuda={fijo ? 'Sus tareas ya tienen instrucciones: para otro departamento, crea allí un puesto nuevo.' : undefined}>
          <Selector value={depId} onChange={(e) => setDepId(e.target.value)} disabled={fijo}
            opciones={org.departamentos.map((d) => ({ valor: d.id, texto: d.nombre }))} />
        </Campo>
        <div className="completo">
          <Campo etiqueta="Descripción">
            <Area value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={3}
              placeholder="Máquinas, zona de la planta, turnos…" />
          </Campo>
        </div>
      </div>
      {dialogo}
    </Tarjeta>
  )
}

// ------------------------------------------------------------------ formulario de tarea

function FormTarea({ tarea, puestoId, org, indice, onGuardado, onBorrado }: {
  tarea?: Tarea; puestoId: number; org: Org; indice: Indice; onGuardado: (s: Seleccion) => void; onBorrado: () => void
}) {
  const nivelBase = org.niveles[0]?.orden ?? 1
  const [puesto, setPuesto] = useState(String(puestoId))
  const [codigo, setCodigo] = useState(tarea?.codigo ?? '')
  const [nombre, setNombre] = useState(tarea?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(tarea?.descripcion ?? '')
  const [criticidad, setCriticidad] = useState(tarea?.criticidad ?? 2)
  const [riesgos, setRiesgos] = useState(tarea?.riesgos_prl ?? '')
  const [nivel, setNivel] = useState(String(tarea?.nivel_minimo ?? nivelBase))
  const [activa, setActiva] = useState(tarea?.activa ?? true)
  const { guardando, ejecutar } = useGuardar()
  const { confirmar, dialogo } = useConfirmar()

  const p = indice.puestos.get(Number(puesto))
  const dep = p ? indice.deps.get(p.departamento_id) : undefined
  // Con instrucciones, solo se ofrece cambiar a otro puesto del mismo departamento.
  const conInstrucciones = !!tarea && tarea.n_instrucciones > 0
  const opcionesPuesto = org.departamentos
    .filter((d) => !conInstrucciones || d.id === tarea?.departamento_id)
    .flatMap((d) => d.puestos.map((x) => ({ valor: x.id, texto: `${d.nombre} · ${x.nombre}` })))

  const guardar = async () => {
    const cuerpo = {
      puesto_id: Number(puesto), codigo, nombre, descripcion, criticidad, riesgos_prl: riesgos,
      nivel_minimo: Number(nivel), activa,
    }
    const r = tarea
      ? await ejecutar(() => put<Tarea>(`/api/admin/tareas/${tarea.id}`, cuerpo), 'Tarea guardada')
      : await ejecutar(() => post<Tarea>('/api/admin/tareas', cuerpo), 'Tarea creada')
    if (r) onGuardado({ tipo: 'tarea', id: r.id })
  }
  const borrar = async () => {
    if (!tarea) return
    const ok = await confirmar('¿Borrar la tarea?',
      <>Se borrará «{tarea.nombre}». Si ya tiene instrucciones o niveles ILUO, CidIA no la borrará: desactívala para conservar el historial.</>, true)
    if (ok && (await ejecutar(() => del(`/api/admin/tareas/${tarea.id}`), 'Tarea borrada')) !== null) onBorrado()
  }

  return (
    <Tarjeta
      pie={<>
        {tarea && <Boton variante="peligro" icono={<Trash2 />} onClick={borrar} style={{ marginRight: 'auto' }}>Borrar</Boton>}
        <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={!nombre.trim() || !puesto} onClick={guardar}>
          {tarea ? 'Guardar cambios' : 'Crear tarea'}
        </Boton>
      </>}
    >
      <CabeceraPanel icono={<ClipboardList />} color={dep?.color} titulo={tarea ? tarea.nombre : 'Nueva tarea'}
        migas={<><span className="adm-color" style={{ background: dep?.color ?? undefined }} />{dep?.nombre}<ChevronRight />{p?.nombre}<ChevronRight />Tarea</>}
        extra={tarea && (
          <div className="fila envolver">
            {tarea.instruccion_publicada
              ? <Etiqueta tono="verde">Instrucción publicada</Etiqueta>
              : tarea.n_instrucciones
                ? <Etiqueta tono="amarilla">Instrucción en preparación</Etiqueta>
                : <Etiqueta>Sin instrucción</Etiqueta>}
            {!tarea.activa && <Etiqueta tono="roja">Desactivada</Etiqueta>}
          </div>
        )} />
      <div className="adm-form-rejilla">
        <Campo etiqueta="Nombre de la tarea">
          <Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Montaje de la brida B" autoFocus={!tarea} maxLength={200} />
        </Campo>
        <Campo etiqueta="Código" ayuda="El de la instrucción técnica, p. ej. IT-023.">
          <Entrada value={codigo} onChange={(e) => setCodigo(e.target.value.toUpperCase())} placeholder="IT-023" maxLength={30} />
        </Campo>
        <Campo etiqueta="Puesto"
          ayuda={conInstrucciones ? 'Ya tiene instrucciones: solo puede pasar a otro puesto de su departamento.' : undefined}>
          <Selector value={puesto} onChange={(e) => setPuesto(e.target.value)} opciones={opcionesPuesto} />
        </Campo>
        <Campo etiqueta="Nivel mínimo" ayuda="Nivel de responsabilidad necesario para hacerla.">
          <Selector value={nivel} onChange={(e) => setNivel(e.target.value)}
            opciones={org.niveles.map((n) => ({ valor: n.orden, texto: `${n.orden} · ${n.nombre}` }))} />
        </Campo>
        <div className="completo">
          <Campo etiqueta="Criticidad" ayuda="Las tareas críticas piden confirmar los pasos críticos en modo planta y se priorizan en las lagunas.">
            <div className="adm-segmentos" role="radiogroup">
              {CRITICIDAD.map((c) => (
                <button key={c.valor} type="button" role="radio" aria-checked={criticidad === c.valor}
                  className={criticidad === c.valor ? 'activo' : ''} onClick={() => setCriticidad(c.valor)}>
                  <span className={`adm-critico c${c.valor}`} />{c.texto}
                </button>
              ))}
            </div>
          </Campo>
        </div>
        <div className="completo">
          <Campo etiqueta="Descripción">
            <Area value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={3}
              placeholder="En qué consiste, cuándo se hace y con qué resultado." />
          </Campo>
        </div>
        <div className="completo">
          <Campo etiqueta={<span className="fila" style={{ gap: 6 }}><ShieldAlert size={15} /> Riesgos PRL</span>}
            ayuda="Se muestran antes de empezar la tarea en modo planta.">
            <Area value={riesgos} onChange={(e) => setRiesgos(e.target.value)} rows={3}
              placeholder="Atrapamiento, cortes, cargas suspendidas… y los EPI necesarios." />
          </Campo>
        </div>
        <div className="completo">
          <Interruptor activo={activa} onCambio={setActiva}
            etiqueta={activa ? 'Tarea activa: aparece en modo planta, formación y evaluación' : 'Tarea desactivada: se conserva el historial pero no se ofrece'} />
        </div>
      </div>
      {dialogo}
    </Tarjeta>
  )
}

// ------------------------------------------------------------------ niveles

function Niveles({ niveles, recargar }: { niveles: Nivel[] | null; recargar: () => void }) {
  const [lista, setLista] = useState<Nivel[]>(niveles ?? [])
  const [arrastrando, setArrastrando] = useState<number | null>(null)
  const [editando, setEditando] = useState<Nivel | 'nuevo' | null>(null)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  useEffect(() => setLista(niveles ?? []), [niveles])

  const guardarOrden = async (nueva: Nivel[]) => {
    if (nueva.map((n) => n.id).join() === (niveles ?? []).map((n) => n.id).join()) return
    setLista(nueva)
    try {
      await put('/api/admin/niveles/orden', { ids: nueva.map((n) => n.id) })
      avisar('Orden de los niveles guardado')
      recargar()
    } catch (e) {
      avisarError(e)
      setLista(niveles ?? [])
    }
  }
  const mover = (i: number, d: -1 | 1) => {
    const j = i + d
    if (j < 0 || j >= lista.length) return
    const nueva = [...lista]
    ;[nueva[i], nueva[j]] = [nueva[j], nueva[i]]
    guardarOrden(nueva)
  }
  const sobre = (destino: number) => {
    if (arrastrando === null || arrastrando === destino) return
    const desde = lista.findIndex((n) => n.id === arrastrando)
    const hasta = lista.findIndex((n) => n.id === destino)
    if (desde < 0 || hasta < 0 || desde === hasta) return
    const nueva = [...lista]
    const [x] = nueva.splice(desde, 1)
    nueva.splice(hasta, 0, x)
    setLista(nueva)
  }
  const borrar = async (n: Nivel) => {
    const ok = await confirmar('¿Borrar el nivel?', <>Se borrará el nivel «{n.nombre}». Solo es posible si ninguna persona, tarea o documento lo usa.</>, true)
    if (!ok) return
    try {
      await del(`/api/admin/niveles/${n.id}`)
      avisar('Nivel borrado')
      recargar()
    } catch (e) {
      avisarError(e)
    }
  }

  return (
    <div className="adm-niveles-rejilla">
      <Tarjeta titulo="Niveles de responsabilidad" icono={<Layers size={18} />} relleno={false}
        acciones={<Boton variante="primario" tamano="pequeno" icono={<Plus />} onClick={() => setEditando('nuevo')}>Nuevo nivel</Boton>}>
        {!niveles ? (
          <div className="columna" style={{ padding: 18 }}>{[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={40} />)}</div>
        ) : !lista.length ? (
          <Vacio icono={<Layers />} titulo="Sin niveles" accion={<Boton onClick={() => setEditando('nuevo')}>Crear el primero</Boton>}>
            Sin niveles, todas las personas tienen el nivel más bajo.
          </Vacio>
        ) : (
          <ul className="adm-niveles">
            {lista.map((n, i) => (
              <li key={n.id} className={`adm-nivel ${arrastrando === n.id ? 'arrastrando' : ''}`}
                draggable onDragStart={() => setArrastrando(n.id)} onDragOver={(e) => { e.preventDefault(); sobre(n.id) }}
                onDragEnd={() => { setArrastrando(null); guardarOrden(lista) }}>
                <span className="adm-asa" title="Arrastra para cambiar el orden"><GripVertical size={18} /></span>
                <span className="adm-orden">{i + 1}</span>
                <div className="crece">
                  <div className="negrita">{n.nombre}</div>
                  {n.descripcion && <div className="pequeno apagado">{n.descripcion}</div>}
                  <div className="adm-escalon" style={{ width: `${Math.round(((i + 1) / lista.length) * 100)}%` }} />
                </div>
                <span className="pequeno apagado" style={{ whiteSpace: 'nowrap' }}><Users size={13} /> {n.n_personas}</span>
                <div className="fila" style={{ gap: 2 }}>
                  <Boton variante="fantasma" tamano="pequeno" icono={<ArrowUp />} disabled={i === 0} onClick={() => mover(i, -1)} aria-label="Subir" title="Más bajo" />
                  <Boton variante="fantasma" tamano="pequeno" icono={<ArrowDown />} disabled={i === lista.length - 1} onClick={() => mover(i, 1)} aria-label="Bajar" title="Más alto" />
                  <Boton variante="fantasma" tamano="pequeno" icono={<Pencil />} onClick={() => setEditando(n)} aria-label="Editar" title="Editar" />
                  <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} onClick={() => borrar(n)} aria-label="Borrar"
                    title={n.n_personas ? 'Hay personas con este nivel' : 'Borrar'} disabled={n.n_personas > 0} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Tarjeta>
      <div className="columna">
        <Aviso titulo="Cómo funcionan los niveles">
          El primero es el más bajo. Una persona encuentra los documentos de su departamento cuyo nivel mínimo sea el suyo o
          uno inferior. Si no defines otros, CidIA usa Operario, Técnico, Responsable y Dirección.
        </Aviso>
        <Aviso tono="amarillo" titulo="Al cambiar el orden">
          Las tareas, documentos y aportaciones siguen apuntando al mismo nivel por su nombre: CidIA traduce sus números
          automáticamente y lo deja en la auditoría.
        </Aviso>
      </div>
      {editando && <ModalNivel nivel={editando === 'nuevo' ? null : editando} onCerrar={() => setEditando(null)}
        onGuardado={() => { setEditando(null); recargar() }} />}
      {dialogo}
    </div>
  )
}

function ModalNivel({ nivel, onCerrar, onGuardado }: { nivel: Nivel | null; onCerrar: () => void; onGuardado: () => void }) {
  const [nombre, setNombre] = useState(nivel?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(nivel?.descripcion ?? '')
  const { guardando, ejecutar } = useGuardar()
  const guardar = async () => {
    const r = nivel
      ? await ejecutar(() => put(`/api/admin/niveles/${nivel.id}`, { nombre, descripcion }), 'Nivel guardado')
      : await ejecutar(() => post('/api/admin/niveles', { nombre, descripcion }), 'Nivel creado')
    if (r !== null) onGuardado()
  }
  return (
    <Modal abierto titulo={nivel ? `Editar «${nivel.nombre}»` : 'Nuevo nivel'} onCerrar={onCerrar}
      pie={<>
        <Boton onClick={onCerrar}>Cancelar</Boton>
        <Boton variante="primario" cargando={guardando} disabled={!nombre.trim()} onClick={guardar}>{nivel ? 'Guardar' : 'Crear nivel'}</Boton>
      </>}>
      <Campo etiqueta="Nombre"><Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus maxLength={100} placeholder="Técnico" /></Campo>
      <Campo etiqueta="Descripción"><Area value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={3}
        placeholder="Qué responsabilidades tiene este nivel." /></Campo>
      {!nivel && <div className="pequeno apagado">Se añade al final de la lista (el nivel más alto). Después puedes moverlo.</div>}
    </Modal>
  )
}

// ------------------------------------------------------------------ empresa y reglas ILUO

function EmpresaReglas() {
  const { datos, error, recargar, setDatos } = useDatos((s) => get<Empresa>('/api/admin/empresa', s), [])
  const [nombre, setNombre] = useState('')
  const [sector, setSector] = useState('')
  const [ejecuciones, setEjecuciones] = useState(3)
  const [umbral, setUmbral] = useState(80)
  const [meses, setMeses] = useState(12)
  const { guardando, ejecutar } = useGuardar()

  const cargar = (e: Empresa) => {
    setNombre(e.nombre)
    setSector(e.sector ?? '')
    setEjecuciones(e.config_iluo.ejecuciones_para_L)
    setUmbral(Math.round(e.config_iluo.umbral_cuestionario * 100))
    setMeses(e.config_iluo.meses_validez)
  }
  useEffect(() => { if (datos) cargar(datos) }, [datos])

  if (error && !datos) return <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
  if (!datos) return <Tarjeta><div className="columna"><Esqueleto alto={40} /><Esqueleto alto={40} /><Esqueleto alto={120} /></div></Tarjeta>

  const c = datos.config_iluo
  const cambiado = nombre !== datos.nombre || sector !== (datos.sector ?? '') || ejecuciones !== c.ejecuciones_para_L
    || umbral !== Math.round(c.umbral_cuestionario * 100) || meses !== c.meses_validez
  const valido = nombre.trim() && ejecuciones >= 1 && ejecuciones <= 100 && umbral >= 50 && umbral <= 100 && meses >= 1 && meses <= 120

  const guardar = async () => {
    const r = await ejecutar(() => put<Empresa>('/api/admin/empresa', {
      nombre, sector,
      config_iluo: { ejecuciones_para_L: ejecuciones, umbral_cuestionario: umbral / 100, meses_validez: meses },
    }), 'Datos y reglas guardados')
    if (r) setDatos(r)
  }
  const porDefecto = () => {
    setEjecuciones(datos.por_defecto.ejecuciones_para_L)
    setUmbral(Math.round(datos.por_defecto.umbral_cuestionario * 100))
    setMeses(datos.por_defecto.meses_validez)
  }

  const escala = [
    { n: 1, letra: 'I', titulo: 'En formación', texto: 'Ha empezado el itinerario: micro-lección vista, ejecución iniciada o formación activa.' },
    { n: 2, letra: 'L', titulo: 'Ejecuta con apoyo', texto: `Cuestionario aprobado con un ${umbral} % o más y ${ejecuciones} ${ejecuciones === 1 ? 'ejecución completada' : 'ejecuciones completadas'}.` },
    { n: 3, letra: 'U', titulo: 'Autónomo', texto: 'Nivel L, observación aprobada por un supervisor y última ejecución sin consultas en pasos críticos.' },
    { n: 4, letra: 'O', titulo: 'Puede formar a otros', texto: 'Nivel U y validado como formador por un jefe o un experto.' },
  ]

  return (
    <div className="columna" style={{ gap: 16 }}>
      <Tarjeta titulo="Datos de la empresa" icono={<Building2 size={18} />}>
        <div className="adm-form-rejilla">
          <Campo etiqueta="Nombre" ayuda="Aparece en la pantalla de acceso de la app.">
            <Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={200} />
          </Campo>
          <Campo etiqueta="Sector">
            <Entrada value={sector} onChange={(e) => setSector(e.target.value)} maxLength={200} placeholder="Metalmecánica, alimentación…" />
          </Campo>
        </div>
      </Tarjeta>

      <Tarjeta titulo="Reglas ILUO" icono={<Iluo nivel={4} tamano={18} />}
        acciones={<Boton variante="fantasma" tamano="pequeno" icono={<RotateCcw />} onClick={porDefecto}>Valores por defecto</Boton>}>
        <div className="adm-regla">
          <div>
            <h4>Ejecuciones para alcanzar L</h4>
            <p>Además de aprobar el cuestionario de la versión vigente, la persona debe completar este número de ejecuciones
              en modo planta. Más ejecuciones dan más seguridad, pero alargan el paso a «ejecuta con apoyo».</p>
          </div>
          <div className="valor-regla">
            <Entrada type="number" min={1} max={100} value={ejecuciones} onChange={(e) => setEjecuciones(Number(e.target.value))} />
            <span className="unidad">ejecuciones</span>
          </div>
        </div>
        <div className="adm-regla">
          <div>
            <h4>Umbral del cuestionario</h4>
            <p>Porcentaje mínimo de aciertos para aprobar el cuestionario de una instrucción. Las preguntas las genera la IA y
              las aprueba un experto del departamento.</p>
          </div>
          <div className="valor-regla">
            <input className="adm-deslizador" type="range" min={50} max={100} step={5} value={umbral}
              onChange={(e) => setUmbral(Number(e.target.value))} aria-label="Umbral del cuestionario" />
            <span className="adm-porcentaje">{umbral} %</span>
          </div>
        </div>
        <div className="adm-regla">
          <div>
            <h4>Validez de cada nivel</h4>
            <p>Pasado este tiempo el nivel caduca y la persona aparece en las reevaluaciones de su jefe. Al publicar una nueva
              versión de una instrucción, quien tenga nivel en esa tarea queda marcado para reevaluación.</p>
          </div>
          <div className="valor-regla">
            <Entrada type="number" min={1} max={120} value={meses} onChange={(e) => setMeses(Number(e.target.value))} />
            <span className="unidad">meses</span>
          </div>
        </div>
      </Tarjeta>

      <Tarjeta titulo="Así quedan los niveles" icono={<Layers size={18} />}>
        <div className="adm-escala-iluo">
          {escala.map((e) => (
            <div key={e.n} className="adm-paso-iluo">
              <div className="fila">
                <Iluo nivel={e.n} tamano={30} />
                <span className="letra">{e.letra}</span>
                <span className="negrita">{e.titulo}</span>
              </div>
              <p>{e.texto}</p>
            </div>
          ))}
        </div>
        <div className="pequeno apagado mt-2">Cada nivel caduca a los {meses} {meses === 1 ? 'mes' : 'meses'}.</div>
      </Tarjeta>

      <div className="fila" style={{ justifyContent: 'flex-end', position: 'sticky', bottom: 12 }}>
        {cambiado && <span className="pequeno apagado">Hay cambios sin guardar</span>}
        <Boton disabled={!cambiado} onClick={() => cargar(datos)}>Descartar</Boton>
        <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={!cambiado || !valido} onClick={guardar}>
          Guardar cambios
        </Boton>
      </div>
    </div>
  )
}
