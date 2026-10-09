// «Observar en el puesto» (jefes): se elige persona y tarea y se marca, paso a paso, si lo hace
// bien mientras trabaja. Lista grande y táctil para usarla de pie en la planta; los pasos
// críticos van en rojo. Al terminar se aprueba o no y el nivel ILUO se recalcula.

import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ClipboardList, Eye, MessageSquarePlus, ShieldAlert, ThumbsDown,
  ThumbsUp, Users, XCircle,
} from 'lucide-react'
import { fecha, get, post } from '../../api'
import { useSesion } from '../../sesion'
import {
  Area, Aviso, Avatar, BarraProgreso, Boton, Campo, ErrorCarga, Esqueleto, Etiqueta, Iluo, Selector, Tarjeta,
  useAvisarError, useDatos,
} from '../../ui'
import type { Matriz } from '../progreso/tipos'
import type { ObservacionSugerida, Plantilla, ResultadoObservacion } from './tipos'

interface Marca { ok: boolean | null; nota: string; conNota: boolean }

// ------------------------------------------------------------------ elegir persona y tarea

function Eleccion({ sugeridas, onAbrir }: { sugeridas: ObservacionSugerida[]; onAbrir: (u: number, t: number) => void }) {
  const { perfil } = useSesion()
  const esAdmin = perfil?.rol === 'admin'
  const [depId, setDepId] = useState<number | null>(null)
  const [usuario, setUsuario] = useState('')
  const [tarea, setTarea] = useState('')
  const { datos: m, error, recargar } = useDatos(
    (s) => get<Matriz>(`/api/progreso/equipo${depId ? `?departamento_id=${depId}` : ''}`, s), [depId])
  const personas = (m?.personas ?? []).filter((p) => p.id !== perfil?.id)
  const nivel = useMemo(() => {
    const c = m?.celdas.find((x) => String(x.usuario_id) === usuario && String(x.tarea_id) === tarea)
    return c?.nivel ?? 0
  }, [m, usuario, tarea])

  return (
    <div className="rejilla c2" style={{ alignItems: 'start' }}>
      <Tarjeta titulo="Sugerencias" icono={<Eye size={18} />}
        acciones={<span className="pequeno apagado">{sugeridas.length}</span>}>
        {sugeridas.length === 0 ? (
          <div className="pequeno apagado">
            Nadie de tu equipo está esperando una observación. Aparecen aquí las personas con nivel L, que ya ejecutan con
            apoyo y necesitan la observación en el puesto para llegar a U.
          </div>
        ) : (
          <div className="columna" style={{ gap: 6 }}>
            {sugeridas.map((s) => (
              <button key={`${s.usuario_id}-${s.tarea_id}`} className="ev-sugerencia" onClick={() => onAbrir(s.usuario_id, s.tarea_id)}>
                <Avatar nombre={s.nombre} tamano="p" />
                <div className="crece" style={{ minWidth: 0 }}>
                  <div className="negrita pequeno recortar">{s.nombre}</div>
                  <div className="diminuto apagado recortar">{s.tarea}{s.desde ? ` · en L desde el ${fecha(s.desde)}` : ''}</div>
                </div>
                <Iluo nivel={s.nivel} tamano={24} />
              </button>
            ))}
          </div>
        )}
      </Tarjeta>

      <Tarjeta titulo="Elegir persona y tarea" icono={<Users size={18} />}>
        {error ? <ErrorCarga error={error} reintentar={recargar} /> : !m ? <Esqueleto alto={150} /> : (
          <>
            {esAdmin && m.departamentos.length > 0 && (
              <Campo etiqueta="Departamento">
                <Selector value={m.departamento?.id ?? ''} onChange={(e) => { setDepId(Number(e.target.value)); setUsuario(''); setTarea('') }}
                  opciones={m.departamentos.map((d) => ({ valor: d.id, texto: d.nombre }))} />
              </Campo>
            )}
            {(!personas.length || !m.tareas.length) && (
              <div className="pequeno apagado mb-2">
                {!m.tareas.length
                  ? 'Este departamento todavía no tiene tareas. Se crean en Organización, dentro de cada puesto.'
                  : 'Este departamento todavía no tiene personas a las que observar.'}
              </div>
            )}
            <Campo etiqueta="Persona">
              <Selector value={usuario} onChange={(e) => setUsuario(e.target.value)} vacio="Elige a quién vas a observar"
                opciones={personas.map((p) => ({ valor: p.id, texto: `${p.nombre}${p.en_formacion ? ' (en formación)' : ''}` }))} />
            </Campo>
            <Campo etiqueta="Tarea">
              <Selector value={tarea} onChange={(e) => setTarea(e.target.value)} vacio="Elige la tarea"
                opciones={m.tareas.map((t) => ({ valor: t.id, texto: `${t.codigo ? `${t.codigo} · ` : ''}${t.nombre}` }))} />
            </Campo>
            {usuario && tarea && nivel < 2 && (
              <div className="pequeno apagado mb-2">
                Todavía no tiene el nivel L en esta tarea. Puedes observarle igualmente: la observación quedará como evidencia.
              </div>
            )}
            <Boton variante="primario" bloque icono={<ClipboardList />} disabled={!usuario || !tarea}
              onClick={() => onAbrir(Number(usuario), Number(tarea))}>
              Abrir la lista de comprobación
            </Boton>
          </>
        )}
      </Tarjeta>
    </div>
  )
}

// ------------------------------------------------------------------ lista de comprobación

function Lista({ usuarioId, tareaId, onVolver, onHecha }: {
  usuarioId: number; tareaId: number; onVolver: () => void; onHecha: () => void
}) {
  const navegar = useNavigate()
  const avisarError = useAvisarError()
  const { datos: pl, error, recargar } = useDatos(
    (s) => get<Plantilla>(`/api/evaluacion/observacion/plantilla?usuario_id=${usuarioId}&tarea_id=${tareaId}`, s),
    [usuarioId, tareaId])
  const [marcas, setMarcas] = useState<Record<number, Marca>>({})
  const [comentario, setComentario] = useState('')
  const [enviando, setEnviando] = useState<'si' | 'no' | null>(null)
  const [resultado, setResultado] = useState<ResultadoObservacion | null>(null)

  if (error) {
    return (
      <Tarjeta>
        <ErrorCarga error={error} reintentar={recargar} />
        <div className="centro mb-2"><Boton variante="fantasma" icono={<ArrowLeft />} onClick={onVolver}>Elegir otra persona</Boton></div>
      </Tarjeta>
    )
  }
  if (!pl) return <div className="columna" style={{ gap: 12 }}><Esqueleto alto={110} /><Esqueleto alto={90} /><Esqueleto alto={90} /></div>

  const marca = (id: number): Marca => marcas[id] ?? { ok: null, nota: '', conNota: false }
  const poner = (id: number, c: Partial<Marca>) => setMarcas((m) => ({ ...m, [id]: { ...marca(id), ...c } }))
  const marcados = pl.lista.filter((p) => marca(p.paso_id).ok !== null).length
  const criticoMal = pl.lista.some((p) => p.critico && marca(p.paso_id).ok === false)
  const completa = marcados === pl.lista.length

  async function enviar(aprobada: boolean) {
    if (!pl) return
    setEnviando(aprobada ? 'si' : 'no')
    try {
      const r = await post<ResultadoObservacion>('/api/evaluacion/observaciones', {
        usuario_id: usuarioId, tarea_id: tareaId, instruccion_id: pl.instruccion.id, aprobada, comentario,
        lista: pl.lista.map((p) => ({ paso_id: p.paso_id, ok: marca(p.paso_id).ok, nota: marca(p.paso_id).nota || null })),
      })
      setResultado(r)
      onHecha()
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(null)
    }
  }

  if (resultado) {
    const o = resultado.observacion
    return (
      <div className="ev-estrecho">
        <Tarjeta>
          <div className="ev-intro">
            <div className={`ev-intro-icono ${o.aprobada ? 'verde' : 'roja'}`}>{o.aprobada ? <CheckCircle2 /> : <XCircle />}</div>
            <h2>{o.aprobada ? 'Observación aprobada' : 'Observación no superada'}</h2>
            <p className="apagado">{pl.persona.nombre} · {pl.tarea.nombre}: {o.pasos_ok} de {o.pasos} pasos bien hechos.</p>
            {resultado.nivel.subio ? (
              <Aviso tono="exito" titulo={`${pl.persona.nombre} sube al nivel ${resultado.nivel.letra}`}>
                <span className="fila" style={{ gap: 10 }}><Iluo nivel={resultado.nivel.nivel} tamano={26} /> {resultado.nivel.nombre}</span>
              </Aviso>
            ) : (
              <div className="fila" style={{ gap: 10, justifyContent: 'center' }}>
                <Iluo nivel={resultado.nivel.nivel} tamano={26} /> <span className="pequeno">Nivel actual: {resultado.nivel.nombre}</span>
              </div>
            )}
            {resultado.siguiente && <div className="pequeno apagado mt-1">Siguiente paso: {resultado.siguiente}</div>}
            <div className="fila envolver mt-2" style={{ gap: 8, justifyContent: 'center' }}>
              <Boton variante="primario" icono={<Eye />} onClick={onVolver}>Observar a otra persona</Boton>
              <Boton icono={<Users />} onClick={() => navegar('/equipo')}>Ver la matriz del equipo</Boton>
            </div>
          </div>
        </Tarjeta>
      </div>
    )
  }

  return (
    <div className="ev-observacion">
      <Tarjeta>
        <div className="fila envolver entre" style={{ gap: 12 }}>
          <div className="fila" style={{ gap: 12, minWidth: 0 }}>
            <Avatar nombre={pl.persona.nombre} />
            <div style={{ minWidth: 0 }}>
              <div className="negrita">{pl.persona.nombre}</div>
              <div className="pequeno apagado">
                {pl.tarea.nombre} · {[pl.instruccion.codigo, `v${pl.instruccion.version}`].filter(Boolean).join(' ')}
              </div>
            </div>
          </div>
          <div className="fila" style={{ gap: 10 }}>
            <Iluo nivel={pl.nivel.nivel} tamano={30} caducado={pl.nivel.caducado} />
            <Boton variante="fantasma" tamano="pequeno" icono={<ArrowLeft />} onClick={onVolver}>Cambiar</Boton>
          </div>
        </div>
        <div className="mt-2">
          <div className="fila entre diminuto apagado mb-1"><span>Pasos marcados</span><span>{marcados} de {pl.lista.length}</span></div>
          <BarraProgreso valor={(marcados / pl.lista.length) * 100} />
        </div>
        {pl.tarea.riesgos_prl && <Aviso tono="alerta" titulo="Riesgos de la tarea">{pl.tarea.riesgos_prl}</Aviso>}
        {pl.previas.length > 0 && (
          <div className="diminuto apagado mt-1">
            Observaciones anteriores: {pl.previas.map((o) => `${fecha(o.fecha)} (${o.aprobada ? 'aprobada' : 'no superada'})`).join(' · ')}
          </div>
        )}
      </Tarjeta>

      <div className="columna" style={{ gap: 10 }}>
        {pl.lista.map((p) => {
          const m = marca(p.paso_id)
          return (
            <div key={p.paso_id} className={`ev-paso ${p.critico ? 'critico' : ''} ${m.ok === true ? 'bien' : m.ok === false ? 'mal' : ''}`}>
              <div className="ev-paso-cuerpo">
                <div className="ev-paso-numero">{m.ok === true ? <Check size={18} /> : p.orden}</div>
                <div className="crece" style={{ minWidth: 0 }}>
                  <div className="fila envolver" style={{ gap: 6 }}>
                    <span className="ev-paso-titulo">{p.titulo}</span>
                    {p.critico && <Etiqueta tono="roja" icono={<ShieldAlert />}>Crítico</Etiqueta>}
                    {p.seguridad && <Etiqueta tono="naranja" icono={<AlertTriangle />}>Seguridad</Etiqueta>}
                  </div>
                  {p.texto && <div className="pequeno apagado mt-1">{p.texto}</div>}
                  {p.criterio && <div className="pequeno mt-1"><span className="negrita">Cómo comprobarlo:</span> {p.criterio}</div>}
                </div>
              </div>
              <div className="ev-paso-acciones">
                <button className={`ev-boton-marca bien ${m.ok === true ? 'activo' : ''}`} aria-pressed={m.ok === true}
                  onClick={() => poner(p.paso_id, { ok: m.ok === true ? null : true })}>
                  <ThumbsUp /> Bien
                </button>
                <button className={`ev-boton-marca mal ${m.ok === false ? 'activo' : ''}`} aria-pressed={m.ok === false}
                  onClick={() => poner(p.paso_id, { ok: m.ok === false ? null : false, conNota: true })}>
                  <ThumbsDown /> Mal
                </button>
                {!m.conNota && (
                  <button className="ev-boton-nota" onClick={() => poner(p.paso_id, { conNota: true })} aria-label="Añadir nota">
                    <MessageSquarePlus />
                  </button>
                )}
              </div>
              {m.conNota && (
                <textarea className="area ev-nota-paso" rows={2} value={m.nota} placeholder="Nota (qué ha fallado, qué mejorar…)"
                  onChange={(e) => poner(p.paso_id, { nota: e.target.value })} />
              )}
            </div>
          )
        })}
      </div>

      <Tarjeta>
        <Campo etiqueta="Comentario final" ayuda={`${pl.persona.nombre} lo verá en su pasaporte.`}>
          <Area value={comentario} onChange={(e) => setComentario(e.target.value)} rows={3}
            placeholder="Cómo lo ha hecho, qué debe reforzar…" />
        </Campo>
        {criticoMal && (
          <Aviso tono="alerta">Hay un paso crítico mal hecho: la observación no se puede aprobar.</Aviso>
        )}
        {!completa && <div className="pequeno apagado mt-1">Marca todos los pasos para terminar ({pl.lista.length - marcados} sin marcar).</div>}
        <div className="ev-botones-finales mt-2">
          <Boton variante="peligro" tamano="grande" icono={<XCircle />} disabled={!completa} cargando={enviando === 'no'}
            onClick={() => enviar(false)}>No superada</Boton>
          <Boton variante="verde" tamano="grande" icono={<CheckCircle2 />} disabled={!completa || criticoMal}
            cargando={enviando === 'si'} onClick={() => enviar(true)}>Aprobar</Boton>
        </div>
      </Tarjeta>
    </div>
  )
}

export default function Observar({ sugeridas, onCambio }: { sugeridas: ObservacionSugerida[]; onCambio: () => void }) {
  const [params, setParams] = useSearchParams()
  const usuario = Number(params.get('usuario')) || null
  const tarea = Number(params.get('tarea')) || null
  const abrir = (u: number, t: number) => setParams({ pestana: 'observar', usuario: String(u), tarea: String(t) })
  const volver = () => setParams({ pestana: 'observar' })
  if (usuario && tarea) return <Lista key={`${usuario}-${tarea}`} usuarioId={usuario} tareaId={tarea} onVolver={volver} onHecha={onCambio} />
  return <Eleccion sugeridas={sugeridas} onAbrir={abrir} />
}
