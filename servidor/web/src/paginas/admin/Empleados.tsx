// Administración · Empleados: cuentas, roles, contraseñas (se muestran una sola vez) y
// formaciones en otros departamentos.

import { useEffect, useMemo, useState } from 'react'
import {
  CalendarClock, CheckCircle2, Copy, GraduationCap, KeyRound, Lock, Plus, Save, Search, ShieldCheck, UserCheck, UserCog,
  UserPlus, UserX, Users, XCircle,
} from 'lucide-react'
import { fecha, get, hace, post, put } from '../../api'
import {
  Aviso, Avatar, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Interruptor, Modal, Pestanas, Selector,
  Tarjeta, Vacio, useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import {
  NOMBRE_ROL_ADMIN, consulta, type Empleado, type Formacion, type ListaEmpleados, type Organizacion, type Rol,
} from './tipos'
import './admin.css'

const TONO_ROL: Record<Rol, 'oscura' | 'azul' | undefined> = { admin: 'oscura', jefe: 'azul', empleado: undefined }

interface ClaveMostrada { titulo: string; nombre: string; usuario: string; contrasena: string }

/** ¿Hay otro diálogo abierto encima? (contraseña o confirmación sobre el panel de la persona).
 *  Escape llega a todos los Modal abiertos: así solo se cierra el de arriba. */
function hayDialogoEncima(): boolean {
  return document.querySelectorAll('.velo').length > 1
}

export default function Empleados() {
  const [texto, setTexto] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [dep, setDep] = useState('')
  const [rol, setRol] = useState('')
  const [estado, setEstado] = useState<'activos' | 'inactivos' | 'todos'>('activos')
  const [panel, setPanel] = useState<{ id: number | null } | null>(null)
  const [clave, setClave] = useState<ClaveMostrada | null>(null)

  // Búsqueda con una pequeña espera para no pedir en cada tecla.
  useEffect(() => {
    const t = setTimeout(() => setBusqueda(texto.trim()), 280)
    return () => clearTimeout(t)
  }, [texto])

  const qs = consulta({
    texto: busqueda, departamento_id: dep, rol,
    activo: estado === 'todos' ? undefined : estado === 'activos',
  })
  const lista = useDatos((s) => get<ListaEmpleados>(`/api/admin/empleados${qs}`, s), [qs])
  const org = useDatos((s) => get<Organizacion>('/api/admin/organizacion', s).catch(() => null), [])
  const soloLectura = lista.datos?.solo_lectura ?? false
  const filtrando = !!(busqueda || dep || rol || estado !== 'activos')

  return (
    <>
      <Cabecera
        antetitulo={<><UserCog size={14} /> Administración</>}
        titulo="Empleados"
        subtitulo="Cuentas, roles y formaciones. Las contraseñas las genera CidIA y se muestran una sola vez."
        acciones={!soloLectura && (
          <Boton variante="primario" icono={<UserPlus />} onClick={() => setPanel({ id: null })}>Nueva persona</Boton>
        )}
      />

      <div className="adm-filtros">
        <div className="entrada-icono">
          <Search />
          <Entrada placeholder="Buscar por nombre, usuario o correo" value={texto} onChange={(e) => setTexto(e.target.value)} />
        </div>
        <Selector value={dep} onChange={(e) => setDep(e.target.value)} vacio="Todos los departamentos"
          opciones={(org.datos?.departamentos ?? []).map((d) => ({ valor: d.id, texto: d.nombre }))} />
        <Selector value={rol} onChange={(e) => setRol(e.target.value)} vacio="Todos los roles"
          opciones={(Object.keys(NOMBRE_ROL_ADMIN) as Rol[]).map((r) => ({ valor: r, texto: NOMBRE_ROL_ADMIN[r] }))} />
        <Selector value={estado} onChange={(e) => setEstado(e.target.value as typeof estado)}
          opciones={[{ valor: 'activos', texto: 'Activas' }, { valor: 'inactivos', texto: 'Desactivadas' }, { valor: 'todos', texto: 'Todas' }]} />
      </div>

      {soloLectura && <div className="mb-2"><Aviso>Ves a las personas de tu departamento en modo lectura. Los cambios los hace la administración.</Aviso></div>}

      <Tarjeta relleno={false}>
        {lista.error && !lista.datos ? (
          <ErrorCarga error={lista.error} reintentar={lista.recargar} />
        ) : !lista.datos ? (
          <div className="columna" style={{ padding: 18 }}>
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="fila"><Esqueleto alto={36} ancho={36} /><Esqueleto alto={18} ancho="30%" /><Esqueleto alto={18} ancho="20%" /></div>
            ))}
          </div>
        ) : !lista.datos.empleados.length ? (
          <Vacio icono={<Users />} titulo={filtrando ? 'Nadie coincide con la búsqueda' : 'Aún no hay personas'}
            accion={filtrando
              ? <Boton onClick={() => { setTexto(''); setDep(''); setRol(''); setEstado('activos') }}>Quitar filtros</Boton>
              : !soloLectura && <Boton variante="primario" icono={<UserPlus />} onClick={() => setPanel({ id: null })}>Dar de alta a la primera</Boton>}>
            {filtrando ? 'Prueba con otro nombre o quita algún filtro.' : 'Da de alta a las personas de la planta y asígnales departamento, nivel y puesto.'}
          </Vacio>
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla adm-tabla apilable">
              <thead>
                <tr>
                  <th>Persona</th><th>Departamento</th><th>Nivel</th><th>Puesto</th><th>Rol</th><th>Estado</th><th>Último acceso</th>
                </tr>
              </thead>
              <tbody>
                {lista.datos.empleados.map((e) => (
                  <tr key={e.id} className={`pulsable ${e.activo ? '' : 'inactivo'}`} onClick={() => setPanel({ id: e.id })}>
                    <td className="ancho-movil">
                      <div className="adm-persona">
                        <Avatar nombre={e.nombre} iniciales={e.iniciales} />
                        <div style={{ minWidth: 0 }}>
                          <div className="nombre recortar">{e.nombre}</div>
                          <div className="sub recortar">
                            <span className="mono">{e.usuario}</span>
                            {e.origen_identidad !== 'local' && <> · <Lock size={11} /> {e.origen_identidad.toUpperCase()}</>}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      {e.departamento
                        ? <span className="adm-dep"><span className="adm-color" style={{ background: e.departamento.color ?? undefined }} />{e.departamento.nombre}</span>
                        : <span className="apagado">Sin departamento</span>}
                      {e.formaciones_activas > 0 && (
                        <div className="diminuto apagado mt-1"><GraduationCap size={12} /> {e.formaciones_activas} {e.formaciones_activas === 1 ? 'formación' : 'formaciones'}</div>
                      )}
                    </td>
                    <td className="oculto-movil">{e.nivel ? e.nivel.nombre : <span className="apagado">-</span>}</td>
                    <td className="oculto-movil">{e.puesto ? e.puesto.nombre : <span className="apagado">-</span>}</td>
                    <td>
                      <div className="etiquetas">
                        <Etiqueta tono={TONO_ROL[e.rol]}>{NOMBRE_ROL_ADMIN[e.rol]}</Etiqueta>
                        {e.es_experto && <Etiqueta tono="amarilla">Experto</Etiqueta>}
                      </div>
                    </td>
                    <td>{e.activo ? <Etiqueta tono="verde">Activa</Etiqueta> : <Etiqueta tono="roja">Desactivada</Etiqueta>}</td>
                    <td className="oculto-movil pequeno apagado" title={fecha(e.ultimo_acceso, true)}>
                      {e.ultimo_acceso ? hace(e.ultimo_acceso) : 'Nunca'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {lista.datos && lista.datos.total > 0 && (
          <div className="adm-paginacion">
            <span>{lista.datos.total} {lista.datos.total === 1 ? 'persona' : 'personas'}</span>
            {lista.cargando && <span>Actualizando…</span>}
          </div>
        )}
      </Tarjeta>

      {panel && (
        <PanelEmpleado
          id={panel.id}
          org={org.datos}
          soloLectura={soloLectura}
          onCerrar={() => { if (!clave && !hayDialogoEncima()) setPanel(null) }}
          onCambio={lista.recargar}
          onCreado={(emp, contrasena) => {
            lista.recargar()
            setPanel({ id: emp.id })
            if (contrasena) setClave({ titulo: 'Contraseña inicial', nombre: emp.nombre, usuario: emp.usuario, contrasena })
          }}
          onClave={setClave}
        />
      )}
      {clave && <ModalClave clave={clave} onCerrar={() => setClave(null)} />}
    </>
  )
}

// ------------------------------------------------------------------ contraseña de un solo uso

function ModalClave({ clave, onCerrar }: { clave: ClaveMostrada; onCerrar: () => void }) {
  const avisar = useAvisos()
  const [copiada, setCopiada] = useState(false)
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(clave.contrasena)
      setCopiada(true)
      avisar('Contraseña copiada')
    } catch {
      avisar('No se ha podido copiar: selecciónala y cópiala a mano.', 'error')
    }
  }
  return (
    <Modal abierto titulo={clave.titulo} onCerrar={onCerrar}
      pie={<>
        <Boton icono={copiada ? <CheckCircle2 /> : <Copy />} onClick={copiar}>{copiada ? 'Copiada' : 'Copiar'}</Boton>
        <Boton variante="primario" onClick={onCerrar}>Ya la he guardado</Boton>
      </>}>
      <p className="apagado">Contraseña de <strong>{clave.nombre}</strong> (usuario <span className="mono">{clave.usuario}</span>):</p>
      <div className="adm-clave">{clave.contrasena}</div>
      <div className="mt-2">
        <Aviso tono="amarillo" titulo="Solo se muestra ahora">
          CidIA no guarda la contraseña en claro y no podrá enseñártela otra vez. Entrégasela a la persona en mano: la primera
          vez que entre, CidIA le pedirá que la cambie por una suya.
        </Aviso>
      </div>
    </Modal>
  )
}

// ------------------------------------------------------------------ panel de alta y edición

function PanelEmpleado({ id, org, soloLectura, onCerrar, onCambio, onCreado, onClave }: {
  id: number | null; org: Organizacion | null; soloLectura: boolean; onCerrar: () => void; onCambio: () => void
  onCreado: (e: Empleado, contrasena: string | null) => void; onClave: (c: ClaveMostrada) => void
}) {
  const detalle = useDatos((s) => (id ? get<Empleado>(`/api/admin/empleados/${id}`, s) : Promise.resolve(null)), [id])
  const [pestana, setPestana] = useState<'datos' | 'formaciones'>('datos')
  const emp = detalle.datos

  const titulo = id === null ? 'Nueva persona' : emp ? emp.nombre : 'Cargando…'
  return (
    <Modal abierto ancho titulo={titulo} onCerrar={onCerrar}>
      {id !== null && (
        <Pestanas<'datos' | 'formaciones'>
          activa={pestana}
          onCambio={setPestana}
          pestanas={[
            { id: 'datos', texto: 'Datos y acceso', icono: <UserCog size={16} /> },
            { id: 'formaciones', texto: 'Formaciones', icono: <GraduationCap size={16} />, contador: emp?.formaciones_activas || undefined },
          ]}
        />
      )}
      {id !== null && detalle.error ? (
        <ErrorCarga error={detalle.error} reintentar={detalle.recargar} />
      ) : id !== null && !emp ? (
        <div className="columna"><Esqueleto alto={40} /><Esqueleto alto={40} /><Esqueleto alto={40} /></div>
      ) : pestana === 'datos' || id === null ? (
        <FormEmpleado key={emp?.id ?? 'nuevo'} emp={emp ?? undefined} org={org} soloLectura={soloLectura}
          onGuardado={(e) => { detalle.setDatos({ ...e, formaciones: emp?.formaciones }); onCambio() }}
          onCreado={onCreado} onClave={onClave} />
      ) : emp ? (
        <Formaciones emp={emp} org={org} soloLectura={soloLectura} onCambio={() => { detalle.recargar(); onCambio() }} />
      ) : null}
    </Modal>
  )
}

function FormEmpleado({ emp, org, soloLectura, onGuardado, onCreado, onClave }: {
  emp?: Empleado; org: Organizacion | null; soloLectura: boolean; onGuardado: (e: Empleado) => void
  onCreado: (e: Empleado, contrasena: string | null) => void; onClave: (c: ClaveMostrada) => void
}) {
  const nivelBase = org?.niveles[0]?.id
  const [usuario, setUsuario] = useState(emp?.usuario ?? '')
  const [nombre, setNombre] = useState(emp?.nombre ?? '')
  const [email, setEmail] = useState(emp?.email ?? '')
  const [dep, setDep] = useState(emp?.departamento ? String(emp.departamento.id) : '')
  const [puesto, setPuesto] = useState(emp?.puesto ? String(emp.puesto.id) : '')
  const [nivel, setNivel] = useState(emp?.nivel ? String(emp.nivel.id) : nivelBase ? String(nivelBase) : '')
  const [rol, setRol] = useState<Rol>(emp?.rol ?? 'empleado')
  const [experto, setExperto] = useState(emp?.es_experto ?? false)
  const [origen, setOrigen] = useState<'local' | 'ldap' | 'oidc'>(emp?.origen_identidad ?? 'local')
  const [guardando, setGuardando] = useState(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  // Al elegir un nombre se propone un usuario (nombre.apellido) si aún no se ha escrito.
  const [usuarioTocado, setUsuarioTocado] = useState(false)
  useEffect(() => {
    if (emp || usuarioTocado) return
    const partes = nombre.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9 ]/g, '').split(' ').filter(Boolean)
    setUsuario(partes.slice(0, 2).join('.'))
  }, [nombre, emp, usuarioTocado])

  const puestos = useMemo(() => org?.departamentos.find((d) => String(d.id) === dep)?.puestos ?? [], [org, dep])
  // Sin la organización (p. ej. un jefe en modo lectura) se muestran al menos los valores actuales.
  const opcionesDep = org
    ? org.departamentos.map((d) => ({ valor: d.id, texto: d.nombre }))
    : emp?.departamento ? [{ valor: emp.departamento.id, texto: emp.departamento.nombre }] : []
  const opcionesPuesto = org
    ? puestos.map((p) => ({ valor: p.id, texto: p.nombre }))
    : emp?.puesto ? [{ valor: emp.puesto.id, texto: emp.puesto.nombre }] : []
  const opcionesNivel = org
    ? org.niveles.map((n) => ({ valor: n.id, texto: `${n.orden} · ${n.nombre}` }))
    : emp?.nivel ? [{ valor: emp.nivel.id, texto: `${emp.nivel.orden} · ${emp.nivel.nombre}` }] : []
  // Si cambia el departamento, el puesto anterior deja de valer (solo cuando ya se conoce la organización).
  useEffect(() => {
    if (org && puesto && !puestos.some((p) => String(p.id) === puesto)) setPuesto('')
  }, [org, puestos, puesto])

  const cuerpo = () => ({
    nombre, email, rol, es_experto: experto,
    departamento_id: dep ? Number(dep) : null,
    puesto_id: puesto ? Number(puesto) : null,
    nivel_id: nivel ? Number(nivel) : null,
  })

  const guardar = async () => {
    setGuardando(true)
    try {
      if (emp) {
        const r = await put<Empleado>(`/api/admin/empleados/${emp.id}`, cuerpo())
        avisar('Cambios guardados')
        onGuardado(r)
      } else {
        const r = await post<{ empleado: Empleado; contrasena_inicial: string | null }>('/api/admin/empleados',
          { ...cuerpo(), usuario, origen_identidad: origen })
        avisar(`${r.empleado.nombre} ya tiene cuenta en CidIA`)
        onCreado(r.empleado, r.contrasena_inicial)
      }
    } catch (e) {
      avisarError(e)
    } finally {
      setGuardando(false)
    }
  }

  const restablecer = async () => {
    if (!emp) return
    const ok = await confirmar('¿Restablecer la contraseña?',
      <>Se generará una contraseña temporal para {emp.nombre} y se cerrarán sus sesiones abiertas. La actual dejará de funcionar.</>)
    if (!ok) return
    try {
      const r = await post<{ contrasena_temporal: string; usuario: string }>(`/api/admin/empleados/${emp.id}/contrasena`)
      onClave({ titulo: 'Contraseña temporal', nombre: emp.nombre, usuario: r.usuario, contrasena: r.contrasena_temporal })
    } catch (e) {
      avisarError(e)
    }
  }

  const cambiarEstado = async () => {
    if (!emp) return
    if (emp.activo) {
      const ok = await confirmar('¿Desactivar la cuenta?',
        <>{emp.nombre} no podrá entrar en CidIA y se cerrarán sus sesiones. Su historial, aportaciones y niveles ILUO se conservan.</>, true)
      if (!ok) return
    }
    try {
      const r = await post<Empleado>(`/api/admin/empleados/${emp.id}/${emp.activo ? 'desactivar' : 'activar'}`)
      avisar(r.activo ? 'Cuenta reactivada' : 'Cuenta desactivada')
      onGuardado(r)
    } catch (e) {
      avisarError(e)
    }
  }

  const deshabilitado = soloLectura
  const valido = nombre.trim() && (emp || usuario.trim()) && !(rol === 'jefe' && !dep)

  return (
    <>
      {emp && (
        <div className="fila envolver mb-2" style={{ gap: 14 }}>
          <Avatar nombre={emp.nombre} iniciales={emp.iniciales} tamano="g" />
          <div className="crece">
            <div className="fila envolver" style={{ gap: 6 }}>
              <Etiqueta tono={TONO_ROL[emp.rol]}>{NOMBRE_ROL_ADMIN[emp.rol]}</Etiqueta>
              {emp.es_experto && <Etiqueta tono="amarilla">Experto</Etiqueta>}
              {emp.activo ? <Etiqueta tono="verde">Activa</Etiqueta> : <Etiqueta tono="roja">Desactivada</Etiqueta>}
              <Etiqueta icono={emp.origen_identidad === 'local' ? <ShieldCheck /> : <Lock />}>{emp.origen_texto}</Etiqueta>
            </div>
            <div className="pequeno apagado mt-1">
              Alta {fecha(emp.creado)} · {emp.ultimo_acceso ? `último acceso ${hace(emp.ultimo_acceso)}` : 'aún no ha entrado'}
            </div>
          </div>
        </div>
      )}

      <div className="adm-form-rejilla">
        <Campo etiqueta="Nombre y apellidos">
          <Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus={!emp} maxLength={150}
            placeholder="Luis García" disabled={deshabilitado} />
        </Campo>
        <Campo etiqueta="Usuario" ayuda={emp ? 'No se puede cambiar: identifica a la persona en el registro.' : 'Con el que inicia sesión. Sin tildes ni espacios.'}>
          <Entrada value={usuario} disabled={!!emp} maxLength={80} className="entrada mono" placeholder="luis.garcia"
            onChange={(e) => { setUsuario(e.target.value.toLowerCase()); setUsuarioTocado(true) }} />
        </Campo>
        <Campo etiqueta="Correo electrónico">
          <Entrada type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200}
            placeholder="luis.garcia@empresa.es" disabled={deshabilitado} />
        </Campo>
        <Campo etiqueta="Rol">
          <Selector value={rol} onChange={(e) => setRol(e.target.value as Rol)} disabled={deshabilitado}
            opciones={(Object.keys(NOMBRE_ROL_ADMIN) as Rol[]).map((r) => ({ valor: r, texto: NOMBRE_ROL_ADMIN[r] }))} />
        </Campo>
        <Campo etiqueta="Departamento" ayuda={rol === 'jefe' && !dep ? 'Un jefe de equipo necesita un departamento.' : undefined}>
          <Selector value={dep} onChange={(e) => setDep(e.target.value)} vacio="Sin departamento" disabled={deshabilitado}
            opciones={opcionesDep} />
        </Campo>
        <Campo etiqueta="Puesto">
          <Selector value={puesto} onChange={(e) => setPuesto(e.target.value)} disabled={deshabilitado || !dep}
            vacio={dep ? 'Sin puesto concreto' : 'Elige antes un departamento'}
            opciones={opcionesPuesto} />
        </Campo>
        <Campo etiqueta="Nivel" ayuda="Decide qué documentos de su departamento puede encontrar.">
          <Selector value={nivel} onChange={(e) => setNivel(e.target.value)} disabled={deshabilitado}
            opciones={opcionesNivel} />
        </Campo>
        {!emp && (
          <Campo etiqueta="Origen de la identidad" ayuda={origen === 'local'
            ? 'CidIA genera una contraseña inicial que verás una sola vez.'
            : 'La contraseña la gestiona el directorio de la empresa: CidIA no genera ninguna.'}>
            <Selector value={origen} onChange={(e) => setOrigen(e.target.value as typeof origen)}
              opciones={[
                { valor: 'local', texto: 'Cuenta de CidIA' },
                { valor: 'ldap', texto: 'Directorio de la empresa (LDAP)' },
                { valor: 'oidc', texto: 'Inicio de sesión único (OIDC)' },
              ]} />
          </Campo>
        )}
        <div className="completo mb-2">
          <Interruptor activo={experto} onCambio={setExperto} deshabilitado={deshabilitado}
            etiqueta={<span><strong>Experto</strong> <span className="apagado pequeno">· puede capturar su saber, preparar instrucciones y aprobar preguntas de evaluación de su departamento</span></span>} />
        </div>
      </div>

      {!deshabilitado && (
        <div className="fila envolver" style={{ justifyContent: 'flex-end', borderTop: '1px solid var(--linea-suave)', paddingTop: 14 }}>
          {emp && (
            <>
              <Boton variante={emp.activo ? 'peligro' : 'verde'} icono={emp.activo ? <UserX /> : <UserCheck />} onClick={cambiarEstado}>
                {emp.activo ? 'Desactivar' : 'Reactivar'}
              </Boton>
              <Boton icono={<KeyRound />} onClick={restablecer} disabled={!emp.contrasena_gestionable}
                title={emp.contrasena_gestionable ? undefined : 'La contraseña se gestiona en el directorio de la empresa'}>
                Restablecer contraseña
              </Boton>
              <span className="crece" />
            </>
          )}
          <Boton variante="primario" icono={emp ? <Save /> : <UserPlus />} cargando={guardando} disabled={!valido} onClick={guardar}>
            {emp ? 'Guardar cambios' : 'Crear cuenta'}
          </Boton>
        </div>
      )}
      {dialogo}
    </>
  )
}

// ------------------------------------------------------------------ formaciones

const ESTADO_FORMACION: Record<Formacion['estado'], { texto: string; tono: 'verde' | 'azul' | 'roja' }> = {
  activa: { texto: 'En curso', tono: 'azul' },
  completada: { texto: 'Completada', tono: 'verde' },
  cancelada: { texto: 'Cancelada', tono: 'roja' },
}

function Formaciones({ emp, org, soloLectura, onCambio }: {
  emp: Empleado; org: Organizacion | null; soloLectura: boolean; onCambio: () => void
}) {
  const [dep, setDep] = useState('')
  const [puesto, setPuesto] = useState('')
  const [fin, setFin] = useState('')
  const [enviando, setEnviando] = useState(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  const formaciones = emp.formaciones ?? []
  const ocupados = new Set(formaciones.filter((f) => f.estado === 'activa').map((f) => f.departamento.id))
  const destinos = (org?.departamentos ?? []).filter((d) => d.id !== emp.departamento?.id && !ocupados.has(d.id))
  const puestos = org?.departamentos.find((d) => String(d.id) === dep)?.puestos ?? []
  const hoy = new Date().toISOString().slice(0, 10)

  const asignar = async () => {
    setEnviando(true)
    try {
      await post(`/api/admin/empleados/${emp.id}/formaciones`, {
        departamento_id: Number(dep), puesto_id: puesto ? Number(puesto) : null, fin_previsto: fin || null,
      })
      avisar('Formación asignada')
      setDep(''); setPuesto(''); setFin('')
      onCambio()
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
    }
  }
  const cerrar = async (f: Formacion, accion: 'completar' | 'cancelar') => {
    if (accion === 'cancelar') {
      const ok = await confirmar('¿Cancelar la formación?',
        <>{emp.nombre} dejará de encontrar el material de formación de {f.departamento.nombre}. Su historial se conserva.</>, true)
      if (!ok) return
    }
    try {
      await post(`/api/admin/formaciones/${f.id}/${accion}`)
      avisar(accion === 'completar' ? 'Formación completada' : 'Formación cancelada')
      onCambio()
    } catch (e) {
      avisarError(e)
    }
  }

  return (
    <div className="columna" style={{ gap: 16 }}>
      <Aviso>
        Mientras una formación está activa, la persona encuentra el <strong>material de formación</strong> de ese departamento y
        sus tareas aparecen en su itinerario, sin ver el resto de documentos internos.
      </Aviso>

      {!formaciones.length ? (
        <Vacio icono={<GraduationCap />} titulo="Sin formaciones">
          {emp.nombre} no se ha formado en otros departamentos. Asígnale una para que aprenda un puesto nuevo.
        </Vacio>
      ) : (
        <div>
          {formaciones.map((f) => {
            const e = ESTADO_FORMACION[f.estado]
            return (
              <div key={f.id} className="adm-formacion">
                <span className="adm-color" style={{ background: f.departamento.color ?? undefined, width: 14, height: 14 }} />
                <div className="crece">
                  <div className="negrita">{f.departamento.nombre}{f.puesto && <span className="apagado"> · {f.puesto.nombre}</span>}</div>
                  <div className="pequeno apagado">
                    Desde {fecha(f.inicio)}{f.fin_previsto && <> · <CalendarClock size={12} /> fin previsto {fecha(f.fin_previsto)}</>}
                  </div>
                </div>
                <Etiqueta tono={e.tono}>{e.texto}</Etiqueta>
                {f.estado === 'activa' && !soloLectura && (
                  <div className="fila" style={{ gap: 6 }}>
                    <Boton tamano="pequeno" variante="verde" icono={<CheckCircle2 />} onClick={() => cerrar(f, 'completar')}>Completar</Boton>
                    <Boton tamano="pequeno" variante="peligro" icono={<XCircle />} onClick={() => cerrar(f, 'cancelar')}>Cancelar</Boton>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {!soloLectura && (
        <Tarjeta titulo="Asignar una formación" icono={<Plus size={18} />}>
          {!destinos.length ? (
            <div className="apagado pequeno">No hay otros departamentos disponibles: ya se está formando en todos o solo existe el suyo.</div>
          ) : (
            <>
              <div className="adm-form-rejilla">
                <Campo etiqueta="Departamento">
                  <Selector value={dep} onChange={(e) => { setDep(e.target.value); setPuesto('') }} vacio="Elige departamento"
                    opciones={destinos.map((d) => ({ valor: d.id, texto: d.nombre }))} />
                </Campo>
                <Campo etiqueta="Puesto (opcional)" ayuda="Si eliges uno, su itinerario se centra en las tareas de ese puesto.">
                  <Selector value={puesto} onChange={(e) => setPuesto(e.target.value)} disabled={!dep} vacio="Todo el departamento"
                    opciones={puestos.map((p) => ({ valor: p.id, texto: p.nombre }))} />
                </Campo>
                <Campo etiqueta="Fin previsto (opcional)">
                  <Entrada type="date" min={hoy} value={fin} onChange={(e) => setFin(e.target.value)} />
                </Campo>
              </div>
              <div className="fila" style={{ justifyContent: 'flex-end' }}>
                <Boton variante="primario" icono={<GraduationCap />} cargando={enviando} disabled={!dep} onClick={asignar}>
                  Asignar formación
                </Boton>
              </div>
            </>
          )}
        </Tarjeta>
      )}
      {dialogo}
    </div>
  )
}
