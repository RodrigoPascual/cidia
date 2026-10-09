// Bandeja del jefe: aportaciones pendientes de su departamento. Cada una se valida (se publica
// como pregunta frecuente con autor y validador), se corrige en línea o se rechaza con un motivo.

import { useMemo, useState, type KeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Building2, Check, CheckCircle2, HelpCircle, Inbox, Layers, Mic, PartyPopper, Pencil, Save, Tag, Wrench, X,
} from 'lucide-react'
import { ErrorApi, get, hace, post, put, urlServidor } from '../../api'
import { useSesion } from '../../sesion'
import {
  Area, Avatar, Aviso, Boton, Cabecera, Dato, Entrada, ErrorCarga, Esqueleto, Etiqueta, Modal, Selector, Tarjeta, Vacio,
  useAvisarError, useAvisos, useDatos,
} from '../../ui'
import { AreaAuto, EditorEtiquetas, Plegable, useSondeo } from './comun'
import { mmss, nombreTarea, veces, type Aportacion, type Opciones, type RespuestaLagunas, type RespuestaPendientes } from './tipos'
import './aportaciones.css'

export default function Validar() {
  const { perfil } = useSesion()
  const bandeja = useDatos((s) => get<RespuestaPendientes>('/api/aportaciones/pendientes', s))
  const opciones = useDatos((s) => get<Opciones>('/api/aportaciones/opciones', s))
  const lagunas = useDatos((s) => get<RespuestaLagunas>('/api/lagunas?estado=abierta&limite=3', s))
  const [saliendo, setSaliendo] = useState<Set<number>>(new Set())
  const navegar = useNavigate()

  const lista = bandeja.datos?.aportaciones ?? []
  const pendientes = lista.filter((a) => a.estado === 'pendiente').length
  useSondeo(lista.some((a) => a.estado === 'procesando'), bandeja.recargar, 4000, bandeja.datos)

  /** Quita la tarjeta con una pequeña animación y actualiza el resumen. */
  function retirar(id: number, como: 'validada' | 'rechazada') {
    setSaliendo((s) => new Set(s).add(id))
    setTimeout(() => {
      bandeja.setDatos((d) => d && {
        aportaciones: d.aportaciones.filter((a) => a.id !== id),
        resumen: {
          ...d.resumen,
          pendientes: Math.max(0, d.resumen.pendientes - 1),
          validadas_30d: d.resumen.validadas_30d + (como === 'validada' ? 1 : 0),
          rechazadas_30d: d.resumen.rechazadas_30d + (como === 'rechazada' ? 1 : 0),
        },
      })
      if (como === 'validada') lagunas.recargar()
    }, 280)
  }

  function actualizar(ap: Aportacion) {
    bandeja.setDatos((d) => d && { ...d, aportaciones: d.aportaciones.map((a) => (a.id === ap.id ? ap : a)) })
  }

  const departamento = perfil?.rol === 'admin' ? 'Toda la planta' : perfil?.departamento?.nombre
  return (
    <>
      <Cabecera
        antetitulo={<><Inbox size={14} /> Mi equipo</>}
        titulo={<>Aportaciones pendientes{departamento ? <span className="apagado apo-titulo-dep"> · {departamento}</span> : null}</>}
        subtitulo="Lo que ha resuelto tu equipo. Al validarlo se publica como pregunta frecuente y el copiloto lo citará con su autor y contigo como validador."
        acciones={bandeja.datos && pendientes > 0 && <Etiqueta tono="amarilla">{pendientes} por revisar</Etiqueta>}
      />

      {bandeja.datos && (
        <div className="rejilla c3 mb-3">
          <Dato icono={<Inbox />} valor={bandeja.datos.resumen.pendientes + bandeja.datos.resumen.procesando} etiqueta="Por revisar" />
          <Dato icono={<CheckCircle2 />} tono="verde" valor={bandeja.datos.resumen.validadas_30d} etiqueta="Validadas en los últimos 30 días" />
          <Link to="/lagunas" className="apo-dato-enlace">
            <Dato icono={<HelpCircle />} tono="alerta" valor={lagunas.datos?.contadores.abierta ?? '·'} etiqueta="Lagunas abiertas" />
          </Link>
        </div>
      )}

      {bandeja.cargando && !bandeja.datos ? (
        <div className="columna">{[0, 1].map((i) => <Esqueleto key={i} alto={260} />)}</div>
      ) : bandeja.error ? (
        <Tarjeta><ErrorCarga error={bandeja.error} reintentar={bandeja.recargar} /></Tarjeta>
      ) : lista.length === 0 ? (
        <Tarjeta className="apo-celebracion">
          <Vacio icono={<PartyPopper />} titulo="¡Bandeja al día!"
            accion={<Boton variante="secundario" icono={<HelpCircle />} onClick={() => navegar('/lagunas')}>Ver las lagunas del equipo</Boton>}>
            No hay aportaciones esperando tu revisión.
            {bandeja.datos && bandeja.datos.resumen.validadas_30d > 0
              ? ` Este mes has publicado ${bandeja.datos.resumen.validadas_30d}: son ${bandeja.datos.resumen.validadas_30d} respuestas más que el copiloto ya sabe dar.`
              : ' Cuando alguien de tu equipo comparta una solución, aparecerá aquí.'}
          </Vacio>
        </Tarjeta>
      ) : (
        <div className="columna apo-bandeja">
          {lista.map((ap) => (
            <TarjetaRevision key={ap.id} ap={ap} opciones={opciones.datos} saliendo={saliendo.has(ap.id)}
              esAdmin={perfil?.rol === 'admin'} onCambio={actualizar} onRevisada={retirar}
              onDesfasada={bandeja.recargar} />
          ))}
        </div>
      )}

      {lagunas.datos && lagunas.datos.lagunas.length > 0 && (
        <div className="apo-lagunas-resumen mt-3">
          <div className="fila entre envolver mb-1">
            <strong className="fila"><HelpCircle size={17} /> Lo que tu equipo pregunta y el copiloto no sabe</strong>
            <Link to="/lagunas" className="pequeno">Ver todas las lagunas</Link>
          </div>
          {lagunas.datos.lagunas.map((l) => (
            <div key={l.id} className="pequeno">«{l.pregunta}» <span className="apagado">· {veces(l.frecuencia)}</span></div>
          ))}
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------------ tarjeta de revisión

type Campo = 'titulo' | 'problema' | 'causa' | 'solucion'
interface Borrador {
  titulo: string
  problema: string
  causa: string
  solucion: string
  etiquetas: string[]
  nivel_minimo: number
  tarea_id: number | null
}

const MOTIVOS = [
  'Ya está documentado en una instrucción.',
  'La solución no es correcta o no es segura.',
  'Falta información para que otros puedan aplicarla.',
  'No es de este departamento.',
]

function borradorDe(ap: Aportacion): Borrador {
  return {
    titulo: ap.titulo ?? '', problema: ap.problema ?? '', causa: ap.causa ?? '', solucion: ap.solucion ?? '',
    etiquetas: [...ap.etiquetas], nivel_minimo: ap.nivel_minimo ?? 1, tarea_id: ap.tarea?.id ?? null,
  }
}

function TarjetaRevision({ ap, opciones, saliendo, esAdmin, onCambio, onRevisada, onDesfasada }: {
  ap: Aportacion; opciones: Opciones | null; saliendo: boolean; esAdmin: boolean
  onCambio: (a: Aportacion) => void; onRevisada: (id: number, como: 'validada' | 'rechazada') => void
  onDesfasada: () => void
}) {
  const avisar = useAvisos()
  const avisarErrorApi = useAvisarError()
  /** Si otra persona ya la revisó o su autor la retiró (409/404), se avisa y se recarga la bandeja. */
  const avisarError = (e: unknown) => {
    avisarErrorApi(e)
    if (e instanceof ErrorApi && (e.estado === 409 || e.estado === 404)) {
      setRechazo(null)
      onDesfasada()
    }
  }
  const [editando, setEditando] = useState(false)
  const [foco, setFoco] = useState<Campo | null>(null)
  const [b, setB] = useState<Borrador>(() => borradorDe(ap))
  const [ocupado, setOcupado] = useState<'guardar' | 'validar' | 'rechazar' | null>(null)
  const [rechazo, setRechazo] = useState<string | null>(null) // null: modal cerrado

  const tareas = useMemo(
    () => (opciones?.tareas ?? []).filter((t) => !ap.departamento || t.departamento_id === ap.departamento.id),
    [opciones, ap.departamento],
  )
  const niveles = opciones?.niveles ?? []

  if (ap.estado === 'procesando') {
    return (
      <Tarjeta className="apo-revision" relleno={false}>
        <div className="fila">
          <Avatar nombre={ap.autor?.nombre} />
          <div className="crece">
            <div className="negrita">{ap.autor?.nombre}</div>
            <div className="diminuto apagado">CidIA está ordenando su aportación… · {hace(ap.creada)}</div>
          </div>
        </div>
        <div className="mt-2 columna"><Esqueleto alto={18} ancho="55%" /><Esqueleto alto={60} /></div>
      </Tarjeta>
    )
  }

  const sinOrdenar = !ap.problema && !ap.causa
  const solucion = editando ? b.solucion : ap.solucion ?? ''
  const propia = ap.es_mia && !esAdmin
  const motivoBloqueo = propia
    ? 'Es tuya: la tiene que validar otro responsable.'
    : !solucion.trim() ? 'Añade la solución antes de validar.' : null

  function editar(campo?: Campo) {
    if (!editando) setB(borradorDe(ap))
    setEditando(true)
    setFoco(campo ?? 'titulo')
  }

  /** Solo se envían los campos que han cambiado. */
  function cambios(): Partial<Borrador> {
    const original = borradorDe(ap)
    const c: Partial<Borrador> = {}
    for (const k of Object.keys(b) as (keyof Borrador)[]) {
      if (JSON.stringify(b[k]) !== JSON.stringify(original[k])) (c as Record<string, unknown>)[k] = b[k]
    }
    return c
  }

  async function guardar() {
    const c = cambios()
    if (!Object.keys(c).length) { setEditando(false); return }
    setOcupado('guardar')
    try {
      const nueva = await put<Aportacion>(`/api/aportaciones/${ap.id}`, c)
      onCambio(nueva)
      setEditando(false)
      avisar('Cambios guardados.')
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }

  async function validar() {
    setOcupado('validar')
    try {
      await post(`/api/aportaciones/${ap.id}/validar`, editando ? cambios() : {})
      avisar(`Publicada. El copiloto ya puede responderlo citando a ${ap.autor?.nombre ?? 'su autor'}.`)
      onRevisada(ap.id, 'validada')
    } catch (e) {
      avisarError(e)
      setOcupado(null)
    }
  }

  async function rechazar() {
    if (!rechazo || rechazo.trim().length < 5) return
    setOcupado('rechazar')
    try {
      await post(`/api/aportaciones/${ap.id}/rechazar`, { motivo: rechazo.trim() })
      setRechazo(null)
      avisar('Aportación rechazada. Su autor verá el motivo.', 'info')
      onRevisada(ap.id, 'rechazada')
    } catch (e) {
      avisarError(e)
      setOcupado(null)
    }
  }

  /** Props para que un texto se pueda editar con un clic o con el teclado (Intro o espacio). */
  const editable = (campo: Campo) => editando ? {} : {
    role: 'button', tabIndex: 0, title: 'Pulsa para editar',
    onClick: () => editar(campo),
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); editar(campo) }
    },
  }

  const bloque = (campo: Exclude<Campo, 'titulo'>, titulo: string, vacio: string, destacado?: boolean) => (
    <div className={`apo-bloque ${destacado ? 'destacado' : ''} ${editando ? 'editando' : 'editable'}`} {...editable(campo)}>
      <div className="apo-bloque-titulo">{titulo}</div>
      {editando ? (
        <AreaAuto value={b[campo]} autoFocus={foco === campo} maxLength={8000}
          onChange={(e) => setB({ ...b, [campo]: e.target.value })} placeholder={vacio} />
      ) : ap[campo] ? (
        <div className="pre">{ap[campo]}</div>
      ) : (
        <div className="apagado pequeno">{vacio}</div>
      )}
    </div>
  )

  const tarea = editando ? tareas.find((t) => t.id === b.tarea_id) ?? null : ap.tarea
  return (
    <div className={`tarjeta apo-revision ${saliendo ? 'saliendo' : ''}`}>
      <div className="apo-revision-cabecera">
        <Avatar nombre={ap.autor?.nombre} />
        <div className="crece">
          <span className="negrita">{ap.autor?.nombre ?? 'Alguien del equipo'}</span>
          <span className="apagado pequeno">
            {ap.autor?.nivel ? ` · ${ap.autor.nivel.toLowerCase()}` : ''} · {hace(ap.creada)}
          </span>
          {ap.via === 'voz' && (
            <span className="apo-voz-meta"><Mic /> nota de voz{ap.duracion_audio ? ` de ${mmss(ap.duracion_audio)}` : ''}</span>
          )}
        </div>
        {ap.es_mia && <Etiqueta>Tuya</Etiqueta>}
      </div>

      {ap.laguna && (
        <div className="apo-respondia"><HelpCircle /> Responde a una pregunta pendiente: «{ap.laguna.pregunta}» · {veces(ap.laguna.frecuencia)}</div>
      )}

      {ap.via === 'voz' && ap.audio_url && (
        <audio controls preload="none" src={urlServidor(ap.audio_url)} className="apo-audio-control" />
      )}
      {(ap.transcripcion || ap.texto_original) && (
        <Plegable titulo={ap.via === 'voz' ? 'Ver la transcripción' : 'Ver el texto original'}>
          {ap.transcripcion && <div className="pre pequeno">{ap.transcripcion}</div>}
          {ap.texto_original && (
            <div className={`pre pequeno ${ap.transcripcion ? 'mt-1' : ''}`}>
              {ap.transcripcion && <span className="negrita">Texto añadido: </span>}{ap.texto_original}
            </div>
          )}
        </Plegable>
      )}
      {ap.via === 'voz' && !ap.transcripcion && (
        <Aviso tono="amarillo">No se ha podido transcribir la nota: escúchala y escribe tú la solución.</Aviso>
      )}
      {sinOrdenar && !(ap.via === 'voz' && !ap.transcripcion) && !editando && (
        <Aviso tono="amarillo">CidIA no ha podido ordenarla del todo: revisa el problema, la causa y la solución.</Aviso>
      )}

      {editando ? (
        <Entrada className="apo-titulo-edicion" value={b.titulo} maxLength={300} autoFocus={foco === 'titulo'}
          onChange={(e) => setB({ ...b, titulo: e.target.value })} placeholder="Título de la pregunta frecuente" />
      ) : (
        <h3 className="apo-revision-titulo editable" {...editable('titulo')}>
          {ap.titulo || 'Sin título'}
        </h3>
      )}

      <div className="apo-ficha">
        {bloque('problema', 'Problema', 'Qué pasaba')}
        {bloque('causa', 'Causa', 'Por qué pasaba (opcional)')}
        {bloque('solucion', 'Solución', 'Qué hay que hacer', true)}
      </div>

      {editando ? (
        <div className="apo-edicion-etiquetas">
          <label className="etiqueta-campo"><Layers size={14} /> Nivel mínimo
            <Selector value={b.nivel_minimo} onChange={(e) => setB({ ...b, nivel_minimo: Number(e.target.value) })}
              opciones={(niveles.length ? niveles : [1, 2, 3, 4].map((n) => ({ orden: n, nombre: `Nivel ${n}` })))
                .map((n) => ({ valor: n.orden, texto: `${n.orden} · ${n.nombre}` }))} />
          </label>
          <label className="etiqueta-campo"><Wrench size={14} /> Tarea
            <Selector value={b.tarea_id ?? ''} vacio="Ninguna en concreto"
              onChange={(e) => setB({ ...b, tarea_id: e.target.value ? Number(e.target.value) : null })}
              opciones={tareas.map((t) => ({ valor: t.id, texto: nombreTarea(t) }))} />
          </label>
          <div className="apo-edicion-libres">
            <span className="etiqueta-campo"><Tag size={14} /> Palabras clave</span>
            <EditorEtiquetas valor={b.etiquetas} onCambio={(v) => setB({ ...b, etiquetas: v })} />
          </div>
        </div>
      ) : (
        <div className="fila envolver apo-etiquetas">
          {ap.departamento?.nombre && <Etiqueta icono={<Building2 />}>{ap.departamento.nombre}</Etiqueta>}
          <Etiqueta icono={<Layers />} title="Nivel mínimo para encontrarla">
            Nivel {ap.nivel_minimo ?? 1}{ap.nivel_nombre ? ` · ${ap.nivel_nombre}` : ''}
          </Etiqueta>
          {tarea && <Etiqueta icono={<Wrench />}>{nombreTarea(tarea)}</Etiqueta>}
          {ap.etiquetas.map((e) => <Etiqueta key={e} icono={<Tag />}>{e}</Etiqueta>)}
        </div>
      )}

      <div className="apo-revision-pie">
        <Boton variante="verde" icono={<Check />} cargando={ocupado === 'validar'} disabled={!!ocupado || !!motivoBloqueo}
          title={motivoBloqueo ?? 'Publicar como pregunta frecuente'} onClick={validar}>
          {editando ? 'Guardar y validar' : 'Validar'}
        </Boton>
        {editando ? (
          <>
            <Boton icono={<Save />} cargando={ocupado === 'guardar'} disabled={!!ocupado} onClick={guardar}>Guardar cambios</Boton>
            <Boton variante="fantasma" disabled={!!ocupado} onClick={() => { setEditando(false); setB(borradorDe(ap)) }}>Cancelar</Boton>
          </>
        ) : (
          <Boton icono={<Pencil />} disabled={!!ocupado} onClick={() => editar()}>Editar</Boton>
        )}
        <span className="crece" />
        {motivoBloqueo && <span className="diminuto apagado apo-bloqueo">{motivoBloqueo}</span>}
        <Boton variante="peligro" icono={<X />} disabled={!!ocupado} onClick={() => setRechazo('')}>Rechazar</Boton>
      </div>

      <Modal abierto={rechazo !== null} titulo="Rechazar aportación" onCerrar={() => setRechazo(null)}
        pie={<>
          <Boton onClick={() => setRechazo(null)}>Cancelar</Boton>
          <Boton variante="peligro" icono={<X />} cargando={ocupado === 'rechazar'}
            disabled={(rechazo ?? '').trim().length < 5} onClick={rechazar}>Rechazar</Boton>
        </>}>
        <p className="apagado">
          {ap.autor?.nombre ?? 'Su autor'} verá este motivo junto a su aportación. Explícalo con claridad y en positivo: así la próxima será mejor.
        </p>
        <div className="fila envolver mb-2">
          {MOTIVOS.map((m) => (
            <button key={m} type="button" className={`apo-motivo ${rechazo === m ? 'activo' : ''}`} onClick={() => setRechazo(m)}>{m}</button>
          ))}
        </div>
        <Area value={rechazo ?? ''} rows={3} maxLength={2000} autoFocus placeholder="Motivo del rechazo"
          onChange={(e) => setRechazo(e.target.value)} />
        {(rechazo ?? '').trim().length > 0 && (rechazo ?? '').trim().length < 5 && (
          <div className="diminuto apagado mt-1">Escribe un motivo algo más largo.</div>
        )}
      </Modal>
    </div>
  )
}
