// Administración · Registro de actividad: sentencias xAPI (exportables para un LRS) y
// auditoría de los cambios de administración, con filtros y detalle plegable.

import { useEffect, useState, type ReactNode } from 'react'
import {
  Activity, Award, BadgeCheck, Camera, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CirclePlay, ClipboardCheck,
  Download, Eye, FileText, Lightbulb, MessageSquare, ScrollText, Search, ShieldCheck, Upload, Video, X, XCircle,
} from 'lucide-react'
import { fecha, get, hace } from '../../api'
import {
  Avatar, Boton, Cabecera, Entrada, ErrorCarga, Esqueleto, Etiqueta, Pestanas, Selector, Tarjeta, Vacio, useAvisarError,
  useAvisos, useDatos,
} from '../../ui'
import { consulta, type FilaAuditoria, type PaginaAuditoria, type PaginaXapi, type SentenciaXapi } from './tipos'
import './admin.css'

type Tono = 'verde' | 'amarillo' | 'azul' | 'rojo' | ''

const ICONO_VERBO: Record<string, [ReactNode, Tono]> = {
  pregunto: [<MessageSquare />, 'azul'],
  respondio: [<MessageSquare />, 'azul'],
  inicio: [<CirclePlay />, 'azul'],
  completo: [<CheckCircle2 />, 'verde'],
  abandono: [<XCircle />, 'rojo'],
  vio: [<Eye />, ''],
  intento: [<ClipboardCheck />, 'amarillo'],
  aprobo: [<BadgeCheck />, 'verde'],
  suspendio: [<XCircle />, 'rojo'],
  confirmo: [<CheckCircle2 />, 'verde'],
  aporto: [<Lightbulb />, 'amarillo'],
  valido: [<BadgeCheck />, 'verde'],
  rechazo: [<XCircle />, 'rojo'],
  publico: [<FileText />, 'azul'],
  capturo: [<Video />, 'amarillo'],
  observo: [<Eye />, 'azul'],
  certifico: [<Award />, 'amarillo'],
  subio: [<Upload />, 'azul'],
  fotografio: [<Camera />, ''],
}

const NOMBRE_OBJETO: Record<string, string> = {
  sesion: 'Sesión', tarea: 'Tarea', documento: 'Documento', instruccion: 'Instrucción', paso: 'Paso',
  ejecucion: 'Ejecución', microleccion: 'Micro-lección', cuestionario: 'Cuestionario', aportacion: 'Aportación',
  consulta: 'Consulta', captura: 'Captura', observacion: 'Observación', formacion: 'Formación', laguna: 'Laguna',
}

/** Nombre legible de una acción de auditoría: «crear_departamento» → «Crear departamento». */
function nombreAccion(accion: string): string {
  const t = accion.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

type IdPestana = 'xapi' | 'auditoria'

export default function Registro() {
  const [pestana, setPestana] = useState<IdPestana>('xapi')
  return (
    <>
      <Cabecera
        antetitulo={<><ScrollText size={14} /> Administración</>}
        titulo="Registro de actividad"
        subtitulo="Lo que ocurre en CidIA en formato xAPI, listo para un LRS, y los cambios de administración con quién los hizo."
      />
      <Pestanas<IdPestana>
        activa={pestana}
        onCambio={setPestana}
        pestanas={[
          { id: 'xapi', texto: 'Actividad (xAPI)', icono: <Activity size={16} /> },
          { id: 'auditoria', texto: 'Auditoría', icono: <ShieldCheck size={16} /> },
        ]}
      />
      {pestana === 'xapi' ? <Actividad /> : <Auditoria />}
    </>
  )
}

/** Texto con espera: solo cambia cuando se deja de escribir. */
function useRetardado(valor: string, ms = 300) {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const t = setTimeout(() => setV(valor.trim()), ms)
    return () => clearTimeout(t)
  }, [valor, ms])
  return v
}

function Paginacion({ pagina, paginas, total, unidad, onPagina }: {
  pagina: number; paginas: number; total: number; unidad: [string, string]; onPagina: (p: number) => void
}) {
  return (
    <div className="adm-paginacion">
      <span>{total.toLocaleString('es-ES')} {total === 1 ? unidad[0] : unidad[1]}</span>
      <div className="fila" style={{ gap: 6 }}>
        <Boton tamano="pequeno" icono={<ChevronLeft />} disabled={pagina <= 1} onClick={() => onPagina(pagina - 1)}>Anterior</Boton>
        <span>Página {pagina} de {paginas}</span>
        <Boton tamano="pequeno" disabled={pagina >= paginas} onClick={() => onPagina(pagina + 1)}>Siguiente <ChevronRight /></Boton>
      </div>
    </div>
  )
}

function Fechas({ desde, hasta, setDesde, setHasta }: {
  desde: string; hasta: string; setDesde: (v: string) => void; setHasta: (v: string) => void
}) {
  return (
    <>
      <span className="etiqueta-fecha">Desde</span>
      <Entrada type="date" className="entrada fecha" value={desde} max={hasta || undefined} onChange={(e) => setDesde(e.target.value)} aria-label="Desde" />
      <span className="etiqueta-fecha">hasta</span>
      <Entrada type="date" className="entrada fecha" value={hasta} min={desde || undefined} onChange={(e) => setHasta(e.target.value)} aria-label="Hasta" />
    </>
  )
}

function Json({ datos }: { datos: unknown }) {
  return <pre className="adm-json">{JSON.stringify(datos, null, 2)}</pre>
}

// ------------------------------------------------------------------ actividad xAPI

function Actividad() {
  const [actor, setActor] = useState('')
  const [objeto, setObjeto] = useState('')
  const [verbo, setVerbo] = useState('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [pagina, setPagina] = useState(1)
  const [abierta, setAbierta] = useState<string | null>(null)
  const [exportando, setExportando] = useState(false)
  const actorR = useRetardado(actor)
  const objetoR = useRetardado(objeto)
  const avisar = useAvisos()
  const avisarError = useAvisarError()

  const filtros = { actor: actorR, objeto: objetoR, verbo, desde, hasta }
  const clave = JSON.stringify(filtros)
  useEffect(() => setPagina(1), [clave])
  const { datos, error, recargar, cargando } = useDatos(
    (s) => get<PaginaXapi>(`/api/admin/xapi${consulta({ ...filtros, pagina, por_pagina: 40 })}`, s), [clave, pagina])
  const hayFiltros = !!(actor || objeto || verbo || desde || hasta)

  const exportar = async () => {
    setExportando(true)
    try {
      const lista = await get<unknown[]>(`/api/admin/xapi/exportar${consulta(filtros)}`)
      const blob = new Blob([JSON.stringify(lista, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `cidia-xapi-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 2000)
      avisar(`${lista.length.toLocaleString('es-ES')} sentencias exportadas`)
    } catch (e) {
      avisarError(e)
    } finally {
      setExportando(false)
    }
  }

  return (
    <>
      <div className="adm-filtros">
        <div className="entrada-icono">
          <Search />
          <Entrada placeholder="Persona" value={actor} onChange={(e) => setActor(e.target.value)} />
        </div>
        <Selector value={verbo} onChange={(e) => setVerbo(e.target.value)} vacio="Todas las acciones"
          opciones={(datos?.verbos ?? []).map((v) => ({ valor: v.clave, texto: v.nombre }))} />
        <div className="entrada-icono">
          <Search />
          <Entrada placeholder="Objeto: tarea, documento, nombre…" value={objeto} onChange={(e) => setObjeto(e.target.value)} />
        </div>
        <Fechas desde={desde} hasta={hasta} setDesde={setDesde} setHasta={setHasta} />
        {hayFiltros && (
          <Boton variante="fantasma" icono={<X />} onClick={() => { setActor(''); setObjeto(''); setVerbo(''); setDesde(''); setHasta('') }}>
            Limpiar
          </Boton>
        )}
        <span className="crece" />
        <Boton icono={<Download />} cargando={exportando} onClick={exportar} disabled={!datos?.total}
          title="Descarga las sentencias xAPI completas (con los filtros aplicados) para cargarlas en un LRS">
          Exportar JSON
        </Boton>
      </div>

      <Tarjeta relleno={false}>
        {error && !datos ? (
          <ErrorCarga error={error} reintentar={recargar} />
        ) : !datos ? (
          <div className="columna" style={{ padding: 18 }}>
            {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="fila"><Esqueleto alto={34} ancho={34} /><Esqueleto alto={18} ancho={`${50 + (i % 3) * 12}%`} /></div>)}
          </div>
        ) : !datos.sentencias.length ? (
          <Vacio icono={<Activity />} titulo={hayFiltros ? 'Nada coincide con los filtros' : 'Aún no hay actividad'}>
            {hayFiltros ? 'Prueba con otras fechas o quita algún filtro.' : 'Cada consulta, ejecución, evaluación o aportación dejará aquí su sentencia xAPI.'}
          </Vacio>
        ) : (
          <ul className="adm-actividad" style={{ opacity: cargando ? 0.6 : 1 }}>
            {datos.sentencias.map((s) => (
              <Evento key={s.id} s={s} abierta={abierta === s.id} onAlternar={() => setAbierta(abierta === s.id ? null : s.id)} />
            ))}
          </ul>
        )}
        {datos && datos.total > 0 && (
          <Paginacion pagina={datos.pagina} paginas={datos.paginas} total={datos.total} unidad={['sentencia', 'sentencias']} onPagina={setPagina} />
        )}
      </Tarjeta>
    </>
  )
}

function Evento({ s, abierta, onAlternar }: { s: SentenciaXapi; abierta: boolean; onAlternar: () => void }) {
  const [icono, tono] = ICONO_VERBO[s.verbo] ?? [<Activity />, '' as Tono]
  const r = s.resultado ?? {}
  const exito = typeof r.success === 'boolean' ? (r.success as boolean) : null
  const nota = typeof r.score === 'number' ? Math.round((r.score as number) * 100) : null
  return (
    <li className="adm-evento">
      <div className={`adm-evento-icono ${tono}`}>{icono}</div>
      <div className="adm-evento-texto">
        <div className="frase">
          <strong>{s.actor_nombre ?? 'Alguien'}</strong> {s.verbo_texto} <strong>{s.objeto_nombre ?? NOMBRE_OBJETO[s.objeto_tipo] ?? s.objeto_tipo}</strong>
        </div>
        <div className="adm-evento-meta">
          <Etiqueta>{NOMBRE_OBJETO[s.objeto_tipo] ?? s.objeto_tipo}</Etiqueta>
          {exito !== null && <Etiqueta tono={exito ? 'verde' : 'roja'}>{exito ? 'superado' : 'no superado'}</Etiqueta>}
          {nota !== null && <Etiqueta tono="amarilla">{nota} %</Etiqueta>}
          <span title={fecha(s.momento, true)}>{hace(s.momento)}</span>
          <span>·</span>
          <span>{fecha(s.momento, true)}</span>
          <button className="boton fantasma pequeno" style={{ height: 24, padding: '0 6px' }} onClick={onAlternar} aria-expanded={abierta}>
            <ChevronDown style={{ transform: abierta ? 'rotate(180deg)' : undefined, transition: 'transform 160ms' }} />
            {abierta ? 'Ocultar' : 'Ver sentencia'}
          </button>
        </div>
        {abierta && <Json datos={s.sentencia} />}
      </div>
    </li>
  )
}

// ------------------------------------------------------------------ auditoría

function Auditoria() {
  const [usuario, setUsuario] = useState('')
  const [texto, setTexto] = useState('')
  const [accion, setAccion] = useState('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [pagina, setPagina] = useState(1)
  const [abierta, setAbierta] = useState<number | null>(null)
  const usuarioR = useRetardado(usuario)
  const textoR = useRetardado(texto)

  const filtros = { usuario: usuarioR, texto: textoR, accion, desde, hasta }
  const clave = JSON.stringify(filtros)
  useEffect(() => setPagina(1), [clave])
  const { datos, error, recargar, cargando } = useDatos(
    (s) => get<PaginaAuditoria>(`/api/admin/auditoria${consulta({ ...filtros, pagina, por_pagina: 40 })}`, s), [clave, pagina])
  const hayFiltros = !!(usuario || texto || accion || desde || hasta)

  return (
    <>
      <div className="adm-filtros">
        <div className="entrada-icono">
          <Search />
          <Entrada placeholder="Quién" value={usuario} onChange={(e) => setUsuario(e.target.value)} />
        </div>
        <Selector value={accion} onChange={(e) => setAccion(e.target.value)} vacio="Todos los cambios"
          opciones={(datos?.acciones ?? []).map((a) => ({ valor: a, texto: nombreAccion(a) }))} />
        <div className="entrada-icono">
          <Search />
          <Entrada placeholder="Buscar en el detalle" value={texto} onChange={(e) => setTexto(e.target.value)} />
        </div>
        <Fechas desde={desde} hasta={hasta} setDesde={setDesde} setHasta={setHasta} />
        {hayFiltros && (
          <Boton variante="fantasma" icono={<X />} onClick={() => { setUsuario(''); setTexto(''); setAccion(''); setDesde(''); setHasta('') }}>
            Limpiar
          </Boton>
        )}
      </div>

      <Tarjeta relleno={false}>
        {error && !datos ? (
          <ErrorCarga error={error} reintentar={recargar} />
        ) : !datos ? (
          <div className="columna" style={{ padding: 18 }}>
            {[0, 1, 2, 3, 4].map((i) => <div key={i} className="fila"><Esqueleto alto={34} ancho={34} /><Esqueleto alto={18} ancho="60%" /></div>)}
          </div>
        ) : !datos.filas.length ? (
          <Vacio icono={<ShieldCheck />} titulo={hayFiltros ? 'Nada coincide con los filtros' : 'Sin cambios registrados'}>
            {hayFiltros ? 'Prueba con otras fechas o quita algún filtro.' : 'Cada cambio en la organización, las cuentas o los modelos quedará anotado aquí.'}
          </Vacio>
        ) : (
          <ul className="adm-actividad" style={{ opacity: cargando ? 0.6 : 1 }}>
            {datos.filas.map((f) => (
              <FilaCambio key={f.id} f={f} abierta={abierta === f.id} onAlternar={() => setAbierta(abierta === f.id ? null : f.id)} />
            ))}
          </ul>
        )}
        {datos && datos.total > 0 && (
          <Paginacion pagina={datos.pagina} paginas={datos.paginas} total={datos.total} unidad={['cambio', 'cambios']} onPagina={setPagina} />
        )}
      </Tarjeta>
    </>
  )
}

function valorLegible(v: unknown): string {
  if (v === null || v === undefined || v === '') return 'vacío'
  if (typeof v === 'boolean') return v ? 'sí' : 'no'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function FilaCambio({ f, abierta, onAlternar }: { f: FilaAuditoria; abierta: boolean; onAlternar: () => void }) {
  const cambios = (f.detalle?.cambios ?? null) as Record<string, [unknown, unknown]> | null
  return (
    <li className="adm-evento">
      <Avatar nombre={f.usuario_nombre ?? 'Sistema'} tamano="p" />
      <div className="adm-evento-texto">
        <div className="frase"><strong>{f.usuario_nombre ?? 'Sistema'}</strong> · {f.texto}</div>
        {cambios && Object.keys(cambios).length > 0 && (
          <table className="adm-cambios">
            <tbody>
              {Object.entries(cambios).map(([campo, par]) => (
                <tr key={campo}>
                  <td>{campo}</td>
                  {Array.isArray(par) ? (
                    <td><span className="antes">{valorLegible(par[0])}</span> → <span className="despues">{valorLegible(par[1])}</span></td>
                  ) : <td>{valorLegible(par)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="adm-evento-meta">
          <Etiqueta title={f.accion}>{nombreAccion(f.accion)}</Etiqueta>
          <span title={fecha(f.momento, true)}>{hace(f.momento)}</span>
          <span>·</span>
          <span>{fecha(f.momento, true)}</span>
          {f.detalle && (
            <button className="boton fantasma pequeno" style={{ height: 24, padding: '0 6px' }} onClick={onAlternar} aria-expanded={abierta}>
              <ChevronDown style={{ transform: abierta ? 'rotate(180deg)' : undefined, transition: 'transform 160ms' }} />
              {abierta ? 'Ocultar' : 'Ver detalle'}
            </button>
          )}
        </div>
        {abierta && <Json datos={f.detalle} />}
      </div>
    </li>
  )
}
