// Administración · Sistema: estado real de los servicios del servidor CidIA (se recarga cada 10 s).

import { useEffect, useState, type ReactNode } from 'react'
import { BookOpen, Brain, Cpu, Database, FileText, FolderOpen, Mic, RefreshCw, Server, Timer, TriangleAlert } from 'lucide-react'
import { fecha, get, hace } from '../../api'
import { BarraProgreso, Boton, Cabecera, ErrorCarga, Esqueleto, Etiqueta, Tarjeta, Vacio, useDatos } from '../../ui'
import './admin.css'

interface EstadoServicio {
  ok: boolean
  error?: string | null
  ms?: number
  modelos?: string[]
  motor?: string
  en_uso?: Record<string, string | null>
  faltan?: Record<string, string>
  fragmentos?: number
  pgvector?: string | null
  configurado?: boolean
}
interface Trabajo { id: number; tipo: string; estado: string; progreso: number; mensaje: string | null; creado: string; actualizado?: string | null }
interface Estado {
  version: string
  motor_conocimiento: string
  servicios: {
    base_datos: EstadoServicio; modelos: EstadoServicio; voz: EstadoServicio; conocimiento: EstadoServicio
    espacio?: EstadoServicio
  }
  documentos: Record<string, number>
  cola?: { pendientes: number; en_curso: number; errores_24h: number }
  trabajos: Trabajo[]
}

const INTERVALO = 10_000
const VISIBLES = 8

const ESTADOS_DOC: { clave: string; texto: string; color: string }[] = [
  { clave: 'listo', texto: 'Listos para consultar', color: 'var(--verde)' },
  { clave: 'procesando', texto: 'Procesándose', color: 'var(--acento)' },
  { clave: 'borrador', texto: 'Borradores', color: 'var(--pizarra-2)' },
  { clave: 'error', texto: 'Con error', color: 'var(--alerta)' },
  { clave: 'obsoleto', texto: 'Versiones sustituidas', color: 'var(--linea)' },
]

const ESTADO_TRABAJO: Record<string, { texto: string; tono?: 'verde' | 'amarilla' | 'roja' | 'azul' }> = {
  pendiente: { texto: 'En cola', tono: 'azul' },
  en_curso: { texto: 'En curso', tono: 'amarilla' },
  completado: { texto: 'Completado', tono: 'verde' },
  error: { texto: 'Error', tono: 'roja' },
}

/** Nombre legible de cada tipo de trabajo en segundo plano (ver `trabajos.encolar` en el gateway). */
const NOMBRE_TRABAJO: Record<string, string> = {
  indexar: 'Indexar documento', indexar_documento: 'Indexar documento',
  captura_video: 'Procesar vídeo', captura_audio: 'Procesar audio', captura_entrevista: 'Procesar entrevista',
  procesar_aportacion: 'Ordenar aportación', microlecciones: 'Generar micro-lecciones',
  generar_preguntas: 'Generar preguntas de evaluación', preguntas: 'Generar preguntas de evaluación',
  memoria_extraer: 'Actualizar la memoria personal', semilla_demo: 'Cargar los datos de demostración',
}

const TIPO_MODELO: Record<string, string> = { chat: 'Chat', embeddings: 'Búsqueda', vision: 'Visión' }

const MOTOR: Record<string, string> = { pgvector: 'propio (PostgreSQL + pgvector)', weknora: 'WeKnora' }

export default function Sistema() {
  const { datos, error, recargar, cargando } = useDatos((s) => get<Estado>('/api/sistema/estado', s), [])
  const [actualizado, setActualizado] = useState<number | null>(null)
  const [, setReloj] = useState(0)

  // Recarga periódica (sin parpadeo: se conservan los datos anteriores mientras llegan los nuevos).
  useEffect(() => {
    const t = setInterval(recargar, INTERVALO)
    return () => clearInterval(t)
  }, [recargar])
  useEffect(() => { if (datos) setActualizado(Date.now()) }, [datos])
  useEffect(() => {
    const t = setInterval(() => setReloj((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [])

  const segundos = actualizado ? Math.max(0, Math.round((Date.now() - actualizado) / 1000)) : null

  return (
    <>
      <Cabecera
        antetitulo={<><Server size={14} /> Administración</>}
        titulo="Sistema"
        subtitulo="Estado real de los servicios del servidor CidIA, comprobado ahora mismo. Se actualiza solo cada 10 segundos."
        acciones={<>
          {error && datos ? <Etiqueta tono="roja">No se ha podido actualizar</Etiqueta>
            : segundos !== null && <span className="pequeno apagado">{segundos < 2 ? 'Actualizado ahora' : `Actualizado hace ${segundos} s`}</span>}
          <Boton icono={<RefreshCw className={cargando ? 'girando' : ''} />} onClick={recargar}>Actualizar</Boton>
        </>}
      />

      {error && !datos ? (
        <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
      ) : !datos ? (
        <div className="columna" style={{ gap: 16 }}>
          <Esqueleto alto={70} />
          <div className="rejilla adm-servicios">{[0, 1, 2, 3, 4].map((i) => <Esqueleto key={i} alto={150} />)}</div>
          <Esqueleto alto={160} />
        </div>
      ) : (
        <Contenido e={datos} />
      )}
    </>
  )
}

function Contenido({ e }: { e: Estado }) {
  const [todos, setTodos] = useState(false)
  const s = e.servicios
  // Un servicio opcional sin configurar (el espacio de trabajo) no es un fallo.
  const lista = [s.base_datos, s.modelos, s.voz, s.conocimiento, ...(s.espacio ? [s.espacio] : [])]
  const conProblemas = lista.filter((x) => !x.ok).length
  const totalDocs = Object.values(e.documentos).reduce((a, b) => a + b, 0)
  const otrosEstados = Object.keys(e.documentos).filter((k) => !ESTADOS_DOC.some((d) => d.clave === k))
  const enUso = s.modelos.en_uso ?? {}
  const faltan = s.modelos.faltan ?? {}

  return (
    <div className="columna" style={{ gap: 16 }}>
      <Tarjeta>
        <div className="adm-version">
          <div className="fila">
            <span className={`punto ${conProblemas ? 'mal' : ''}`} />
            <span className="grande">
              {conProblemas ? `${conProblemas === 1 ? 'Hay un servicio' : `Hay ${conProblemas} servicios`} con problemas` : 'Todo funciona'}
            </span>
          </div>
          <span className="apagado">CidIA <strong className="mono">{e.version}</strong></span>
          <span className="apagado">Motor de conocimiento: <strong>{MOTOR[e.motor_conocimiento] ?? e.motor_conocimiento}</strong></span>
          {e.cola && (
            <span className="apagado">
              Trabajos: <strong>{e.cola.en_curso}</strong> en curso · <strong>{e.cola.pendientes}</strong> en cola
              {e.cola.errores_24h > 0 && <> · <strong style={{ color: 'var(--alerta)' }}>{e.cola.errores_24h}</strong> con error en 24 h</>}
            </span>
          )}
        </div>
      </Tarjeta>

      <div className="rejilla adm-servicios">
        <Servicio icono={<Database />} titulo="Base de datos" estado={s.base_datos} detalle="PostgreSQL con pgvector" />
        <Servicio icono={<Brain />} titulo="Modelos" estado={s.modelos}
          detalle={s.modelos.modelos ? `${s.modelos.modelos.length} descargados en el servidor` : 'Servidor de modelos (Ollama)'}>
          {Object.keys(enUso).length > 0 && (
            <div className="adm-en-uso">
              {Object.entries(enUso).map(([tipo, ref]) => (
                <div key={tipo} className={faltan[tipo] ? 'falta' : ''}>
                  <span>{TIPO_MODELO[tipo] ?? tipo}</span>
                  <span className="mono" title={faltan[tipo] ? `${ref}: no está descargado en el servidor` : ref ?? undefined}>
                    {ref ?? 'ninguno permitido'}{faltan[tipo] ? ' · falta' : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
          {!Object.keys(enUso).length && s.modelos.ok && !!s.modelos.modelos?.length && (
            <div className="adm-chips">
              {s.modelos.modelos.map((m) => <Etiqueta key={m} icono={<Cpu />}><span className="mono">{m}</span></Etiqueta>)}
            </div>
          )}
        </Servicio>
        <Servicio icono={<Mic />} titulo="Voz" estado={s.voz} detalle="Transcripción de notas de voz y preguntas" />
        <Servicio icono={<BookOpen />} titulo="Conocimiento" estado={s.conocimiento}
          detalle={s.conocimiento.fragmentos !== undefined
            ? `${s.conocimiento.fragmentos.toLocaleString('es-ES')} fragmentos indexados${s.conocimiento.pgvector ? ` · pgvector ${s.conocimiento.pgvector}` : ''}`
            : `Motor ${MOTOR[s.conocimiento.motor ?? e.motor_conocimiento] ?? e.motor_conocimiento}`} />
        {s.espacio && (
          <Servicio icono={<FolderOpen />} titulo="Espacio de trabajo" estado={s.espacio}
            detalle={s.espacio.configurado === false
              ? 'No está configurado en este servidor: la consola del agente no aparece.'
              : 'Contenedores sin red para las órdenes del agente'} />
        )}
      </div>

      <div className="rejilla adm-sistema-pie">
        <Tarjeta titulo="Documentos por estado" icono={<FileText size={18} />}>
          {!totalDocs ? (
            <div className="apagado pequeno">Aún no hay documentos. Los jefes y la administración los suben desde «Documentos».</div>
          ) : (
            <>
              <div className="fila entre mb-1"><span className="negrita">{totalDocs.toLocaleString('es-ES')} documentos</span></div>
              <div className="adm-barra-estados" role="img" aria-label="Reparto de documentos por estado">
                {ESTADOS_DOC.map((d) => {
                  const n = e.documentos[d.clave] ?? 0
                  return n ? <div key={d.clave} style={{ width: `${(100 * n) / totalDocs}%`, background: d.color }} title={`${d.texto}: ${n}`} /> : null
                })}
              </div>
              <div className="adm-leyenda">
                {ESTADOS_DOC.filter((d) => d.clave !== 'obsoleto' || e.documentos[d.clave]).map((d) => (
                  <span key={d.clave}><i style={{ background: d.color }} />{d.texto} <strong>{e.documentos[d.clave] ?? 0}</strong></span>
                ))}
                {otrosEstados.map((k) => <span key={k}><i style={{ background: 'var(--linea)' }} />{k} <strong>{e.documentos[k]}</strong></span>)}
              </div>
            </>
          )}
        </Tarjeta>

        <Tarjeta titulo="Trabajos recientes" icono={<Timer size={18} />} relleno={false}>
          {!e.trabajos.length ? (
            <Vacio icono={<Timer />} titulo="Sin trabajos">Aquí aparecerán el indexado de documentos, el procesado de vídeos y la generación de contenidos.</Vacio>
          ) : (
            <ul className="adm-trabajos">
              {(todos ? e.trabajos : e.trabajos.slice(0, VISIBLES)).map((t) => {
                const est = ESTADO_TRABAJO[t.estado] ?? { texto: t.estado }
                const activo = t.estado === 'pendiente' || t.estado === 'en_curso'
                return (
                  <li key={t.id}>
                    <div className="crece" style={{ minWidth: 0 }}>
                      <div className="negrita recortar">{NOMBRE_TRABAJO[t.tipo] ?? t.tipo.replace(/_/g, ' ')}</div>
                      {/* El mensaje de un trabajo terminado es su último paso («Indexando»): solo se muestra si sigue o falló. */}
                      {t.mensaje && (activo || t.estado === 'error') && (
                        <div className={`diminuto recortar ${t.estado === 'error' ? 'adm-error-trabajo' : 'apagado'}`} title={t.mensaje}>
                          {t.estado === 'error' && <TriangleAlert size={12} />} {t.mensaje}
                        </div>
                      )}
                      {activo && <div className="mt-1"><BarraProgreso valor={t.progreso} tono={t.estado === 'en_curso' ? 'amarilla' : undefined} /></div>}
                    </div>
                    <Etiqueta tono={est.tono}>{est.texto}</Etiqueta>
                    <span className="pequeno apagado adm-cuando" title={fecha(t.creado, true)}>{hace(t.creado)}</span>
                  </li>
                )
              })}
              {e.trabajos.length > VISIBLES && (
                <li className="adm-trabajos-mas">
                  <Boton variante="fantasma" tamano="pequeno" onClick={() => setTodos((v) => !v)}>
                    {todos ? 'Ver menos' : `Ver los ${e.trabajos.length} últimos`}
                  </Boton>
                </li>
              )}
            </ul>
          )}
        </Tarjeta>
      </div>
    </div>
  )
}

function Servicio({ icono, titulo, estado, detalle, children }: {
  icono: ReactNode; titulo: string; estado: EstadoServicio; detalle: string; children?: ReactNode
}) {
  const sinConfigurar = estado.configurado === false
  return (
    <Tarjeta>
      <div className="adm-servicio">
        <div className="adm-servicio-cabecera">
          <div className="adm-servicio-icono">{icono}</div>
          <div className="crece">
            <h3>{titulo}</h3>
            <div className={`estado ${sinConfigurar ? 'neutro' : estado.ok ? 'ok' : 'mal'}`}>
              <span className={`punto ${sinConfigurar ? 'gris' : estado.ok ? '' : 'mal'}`} />
              {sinConfigurar ? 'Sin configurar' : estado.ok ? 'Funciona' : 'Con problemas'}
              {!sinConfigurar && estado.ms !== undefined && (
                <span className="adm-ms" title="Lo que ha tardado en responder">
                  {estado.ms < 1000 ? `${estado.ms} ms` : `${(estado.ms / 1000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} s`}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="pequeno apagado">{detalle}</div>
        {!estado.ok && estado.error && <div className="error" title={estado.error}>{estado.error}</div>}
        {children}
      </div>
    </Tarjeta>
  )
}
