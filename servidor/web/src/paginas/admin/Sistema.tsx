// Administración · Sistema: estado de los servicios del servidor CidIA (se recarga cada 10 s).

import { useEffect, useState, type ReactNode } from 'react'
import { BookOpen, Brain, Cpu, Database, FileText, Mic, RefreshCw, Server, Timer } from 'lucide-react'
import { get, hace } from '../../api'
import { BarraProgreso, Boton, Cabecera, ErrorCarga, Esqueleto, Etiqueta, Tarjeta, Vacio, useDatos } from '../../ui'
import './admin.css'

interface EstadoServicio { ok: boolean; error?: string; modelos?: string[]; motor?: string }
interface Trabajo { id: number; tipo: string; estado: string; progreso: number; mensaje: string | null; creado: string }
interface Estado {
  version: string
  motor_conocimiento: string
  servicios: { base_datos: EstadoServicio; modelos: EstadoServicio; voz: EstadoServicio; conocimiento: EstadoServicio }
  documentos: Record<string, number>
  trabajos: Trabajo[]
}

const INTERVALO = 10_000

const ESTADOS_DOC: { clave: string; texto: string; color: string }[] = [
  { clave: 'listo', texto: 'Listos para consultar', color: 'var(--verde)' },
  { clave: 'procesando', texto: 'Procesándose', color: 'var(--acento)' },
  { clave: 'borrador', texto: 'Borradores', color: 'var(--pizarra-2)' },
  { clave: 'error', texto: 'Con error', color: 'var(--alerta)' },
]

const ESTADO_TRABAJO: Record<string, { texto: string; tono?: 'verde' | 'amarilla' | 'roja' | 'azul' }> = {
  pendiente: { texto: 'En cola', tono: 'azul' },
  en_curso: { texto: 'En curso', tono: 'amarilla' },
  completado: { texto: 'Completado', tono: 'verde' },
  error: { texto: 'Error', tono: 'roja' },
}

const NOMBRE_TRABAJO: Record<string, string> = {
  indexar: 'Indexar documento', indexar_documento: 'Indexar documento', captura_video: 'Procesar vídeo',
  microlecciones: 'Generar micro-lecciones', preguntas: 'Generar preguntas',
}

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
        subtitulo="Estado de los servicios del servidor CidIA. Se actualiza solo cada 10 segundos."
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
          <div className="rejilla c4">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} alto={150} />)}</div>
          <Esqueleto alto={160} />
        </div>
      ) : (
        <Contenido e={datos} />
      )}
    </>
  )
}

function Contenido({ e }: { e: Estado }) {
  const s = e.servicios
  const todoBien = Object.values(s).every((x) => x.ok)
  const totalDocs = Object.values(e.documentos).reduce((a, b) => a + b, 0)
  const otrosEstados = Object.keys(e.documentos).filter((k) => !ESTADOS_DOC.some((d) => d.clave === k))

  return (
    <div className="columna" style={{ gap: 16 }}>
      <Tarjeta>
        <div className="adm-version">
          <div className="fila">
            <span className={`punto ${todoBien ? '' : 'mal'}`} />
            <span className="grande">{todoBien ? 'Todo funciona' : 'Hay servicios con problemas'}</span>
          </div>
          <span className="apagado">CidIA <strong className="mono">{e.version}</strong></span>
          <span className="apagado">Motor de conocimiento: <strong>{MOTOR[e.motor_conocimiento] ?? e.motor_conocimiento}</strong></span>
        </div>
      </Tarjeta>

      <div className="rejilla c4">
        <Servicio icono={<Database />} titulo="Base de datos" estado={s.base_datos} detalle="PostgreSQL con pgvector" />
        <Servicio icono={<Brain />} titulo="Modelos" estado={s.modelos}
          detalle={s.modelos.ok ? `${s.modelos.modelos?.length ?? 0} descargados en el servidor` : 'Servidor de modelos (Ollama)'}>
          {s.modelos.ok && !!s.modelos.modelos?.length && (
            <div className="adm-chips">
              {s.modelos.modelos.map((m) => <Etiqueta key={m} icono={<Cpu />}><span className="mono">{m}</span></Etiqueta>)}
            </div>
          )}
        </Servicio>
        <Servicio icono={<Mic />} titulo="Voz" estado={s.voz} detalle="Transcripción de notas de voz y preguntas" />
        <Servicio icono={<BookOpen />} titulo="Conocimiento" estado={s.conocimiento}
          detalle={`Motor ${MOTOR[s.conocimiento.motor ?? e.motor_conocimiento] ?? e.motor_conocimiento}`} />
      </div>

      <div className="rejilla c2" style={{ alignItems: 'start' }}>
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
                {ESTADOS_DOC.map((d) => (
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
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead><tr><th>Trabajo</th><th>Estado</th><th>Progreso</th><th>Cuándo</th></tr></thead>
                <tbody>
                  {e.trabajos.map((t) => {
                    const est = ESTADO_TRABAJO[t.estado] ?? { texto: t.estado }
                    return (
                      <tr key={t.id}>
                        <td>
                          <div className="negrita">{NOMBRE_TRABAJO[t.tipo] ?? t.tipo.replace(/_/g, ' ')}</div>
                          {t.mensaje && <div className="diminuto apagado recortar" style={{ maxWidth: 260 }} title={t.mensaje}>{t.mensaje}</div>}
                        </td>
                        <td><Etiqueta tono={est.tono}>{est.texto}</Etiqueta></td>
                        <td style={{ minWidth: 90 }}><BarraProgreso valor={t.progreso} tono={t.estado === 'en_curso' ? 'amarilla' : undefined} /></td>
                        <td className="pequeno apagado" style={{ whiteSpace: 'nowrap' }}>{hace(t.creado)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      </div>
    </div>
  )
}

function Servicio({ icono, titulo, estado, detalle, children }: {
  icono: ReactNode; titulo: string; estado: EstadoServicio; detalle: string; children?: ReactNode
}) {
  return (
    <Tarjeta>
      <div className="adm-servicio">
        <div className="adm-servicio-cabecera">
          <div className="adm-servicio-icono">{icono}</div>
          <div className="crece">
            <h3>{titulo}</h3>
            <div className={`estado ${estado.ok ? 'ok' : 'mal'}`}>
              <span className={`punto ${estado.ok ? '' : 'mal'}`} />{estado.ok ? 'Funciona' : 'No responde'}
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
