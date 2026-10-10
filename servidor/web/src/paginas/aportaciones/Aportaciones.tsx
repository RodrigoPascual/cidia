// Aportaciones: cualquier persona cuenta, por escrito o con una nota de voz, algo que ha resuelto.
// Su jefe lo valida y desde ese momento el copiloto sabe responderlo a los demás, citándola.
// También muestra las «preguntas pendientes» de su departamento para que quien lo sepa responda.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowRight, BookOpenCheck, CheckCircle2, HelpCircle, Lightbulb, Mic, MessageSquare, PenLine, Send, Trash2, Wrench, X,
} from 'lucide-react'
import { enviarFormulario, fecha, get, hace, post, del, urlServidor } from '../../api'
import {
  Area, Aviso, Boton, Cabecera, Campo, ErrorCarga, Esqueleto, Etiqueta, Modal, Selector, Tarjeta, Vacio,
  useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import { ContenidoPublicado, EtiquetaEstado, FichaAportacion, Plegable, useSondeo } from './comun'
import { GrabadorNota, type Nota } from './GrabadorNota'
import {
  mmss, nombreTarea, veces, type Aportacion, type Opciones, type PreguntaPendiente, type RespuestaMias,
} from './tipos'
import './aportaciones.css'

const MIN_TEXTO = 15

export default function Aportaciones() {
  const avisar = useAvisos()
  const mias = useDatos((s) => get<RespuestaMias>('/api/aportaciones/mias', s))
  const preguntas = useDatos((s) => get<{ lagunas: PreguntaPendiente[] }>('/api/lagunas/abiertas-de-mi-departamento', s))
  const opciones = useDatos((s) => get<Opciones>('/api/aportaciones/opciones', s))
  const [laguna, setLaguna] = useState<PreguntaPendiente | null>(null)
  const [params, setParams] = useSearchParams()
  const formulario = useRef<HTMLDivElement>(null)

  // Mientras alguna se está ordenando, se consulta de nuevo: cada 3 s al principio y cada 10 s
  // si tarda más de un minuto (el servidor puede estar ocupado con un vídeo).
  const enProceso = mias.datos?.aportaciones.filter((a) => a.estado === 'procesando') ?? []
  const tardando = enProceso.some((a) => Date.now() - new Date(a.creada).getTime() > 60_000)
  useSondeo(enProceso.length > 0, mias.recargar, tardando ? 10_000 : 3000, mias.datos)

  // Enlace directo a una pregunta: /aportaciones?laguna=12 (lo usa «Pedir a alguien que la responda»).
  useEffect(() => {
    const id = Number(params.get('laguna'))
    if (!id || !preguntas.datos) return
    const p = preguntas.datos.lagunas.find((l) => l.id === id)
    if (p && !p.mi_respuesta) responder(p)
    else if (p) avisar('Ya respondiste a esa pregunta: tu respuesta está en revisión.', 'info')
    else avisar('Esa pregunta ya no está pendiente: alguien la respondió o se cerró.', 'info')
    params.delete('laguna')
    setParams(params, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preguntas.datos])

  function responder(p: PreguntaPendiente) {
    setLaguna(p)
    requestAnimationFrame(() => formulario.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  function alEnviar(ap: Aportacion) {
    mias.setDatos((d) => d && {
      aportaciones: [ap, ...d.aportaciones],
      resumen: { ...d.resumen, [ap.estado]: (d.resumen[ap.estado] ?? 0) + 1 },
    })
    // Una consulta de seguimiento que ya estuviera en marcha traería la lista de antes: se
    // cancela y se pide de nuevo (recargar aborta la anterior).
    mias.recargar()
    if (laguna) {
      // La tarjeta de la pregunta cambia al momento a «Tu respuesta está en revisión» (la recarga
      // del servidor puede tardar unos segundos).
      const id = laguna.id
      preguntas.setDatos((d) => d && {
        lagunas: d.lagunas.map((l) => (l.id === id
          ? { ...l, mi_respuesta: { id: ap.id, estado: ap.estado }, respuestas_en_revision: l.respuestas_en_revision + 1 }
          : l)),
      })
      preguntas.recargar()
    }
    setLaguna(null)
  }

  function alRetirar(id: number) {
    // Si respondía a una pregunta, esa pregunta vuelve a poder responderse al momento.
    preguntas.setDatos((d) => d && {
      lagunas: d.lagunas.map((l) => (l.mi_respuesta?.id === id
        ? { ...l, mi_respuesta: null, respuestas_en_revision: Math.max(0, l.respuestas_en_revision - 1) }
        : l)),
    })
    mias.setDatos((d) => {
      const quitada = d?.aportaciones.find((a) => a.id === id)
      if (!d || !quitada) return d
      return {
        aportaciones: d.aportaciones.filter((a) => a.id !== id),
        resumen: { ...d.resumen, [quitada.estado]: Math.max(0, d.resumen[quitada.estado] - 1) },
      }
    })
    mias.recargar() // cancela una consulta de seguimiento en marcha, que aún la traería
    preguntas.recargar() // si respondía a una pregunta, vuelve a poder responderse
  }

  return (
    <>
      <Cabecera
        antetitulo={<><Lightbulb size={14} /> Aportaciones</>}
        titulo="Comparte lo que has resuelto"
        subtitulo="Lo que hoy te ha costado resolver, mañana se lo puedes ahorrar a un compañero. Tu responsable lo revisa y el copiloto lo citará con tu nombre."
      />

      <div ref={formulario}>
        <NuevaAportacion
          tareas={opciones.datos?.tareas ?? []}
          laguna={laguna}
          onQuitarLaguna={() => setLaguna(null)}
          onEnviada={alEnviar}
        />
      </div>

      <PreguntasPendientes
        cargando={preguntas.cargando && !preguntas.datos}
        error={preguntas.error}
        reintentar={preguntas.recargar}
        lista={preguntas.datos?.lagunas ?? []}
        seleccionada={laguna?.id ?? null}
        onResponder={responder}
      />

      <MisAportaciones
        datos={mias.datos}
        cargando={mias.cargando && !mias.datos}
        error={mias.error}
        reintentar={mias.recargar}
        onRetirada={alRetirar}
      />
    </>
  )
}

// ------------------------------------------------------------------ nueva aportación

type Modo = 'elegir' | 'texto' | 'voz'

function NuevaAportacion({ tareas, laguna, onQuitarLaguna, onEnviada }: {
  tareas: Opciones['tareas']; laguna: PreguntaPendiente | null; onQuitarLaguna: () => void; onEnviada: (a: Aportacion) => void
}) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const [modo, setModo] = useState<Modo>('elegir')
  const [texto, setTexto] = useState('')
  const [tareaId, setTareaId] = useState('')
  const [nota, setNota] = useState<Nota | null>(null)
  const [enviando, setEnviando] = useState(false)
  const areaTexto = useRef<HTMLTextAreaElement>(null)

  // La URL de la nota grabada vive mientras la nota esté aquí: se libera al cambiarla o al salir.
  useEffect(() => () => { if (nota) URL.revokeObjectURL(nota.url) }, [nota])

  // Al elegir «Yo sé la respuesta» se abre el formulario con la pregunta enlazada.
  useEffect(() => {
    if (!laguna) return
    if (laguna.tarea && tareas.some((t) => t.id === laguna.tarea?.id)) setTareaId(String(laguna.tarea.id))
    if (modo === 'elegir') setModo('texto')
    setTimeout(() => areaTexto.current?.focus({ preventScroll: true }), 350)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [laguna])

  const textoValido = texto.trim().length >= MIN_TEXTO
  const puedeEnviar = modo === 'voz' ? !!nota : textoValido

  function reiniciar() {
    setModo('elegir')
    setTexto('')
    setTareaId('')
    setNota(null)
  }

  async function enviar() {
    if (!puedeEnviar) return
    setEnviando(true)
    try {
      let ap: Aportacion
      if (modo === 'voz' && nota) {
        const f = new FormData()
        const ext = nota.blob.type.includes('ogg') ? 'ogg' : nota.blob.type.includes('mp4') ? 'm4a' : 'webm'
        f.append('audio', nota.blob, `nota-de-voz.${ext}`)
        f.append('duracion', String(nota.segundos))
        if (texto.trim()) f.append('texto', texto.trim())
        if (tareaId) f.append('tarea_id', tareaId)
        if (laguna) f.append('laguna_id', String(laguna.id))
        ap = await enviarFormulario<Aportacion>('/api/aportaciones', f)
      } else {
        ap = await post<Aportacion>('/api/aportaciones', {
          texto: texto.trim(), tarea_id: tareaId ? Number(tareaId) : null, laguna_id: laguna?.id ?? null,
        })
      }
      avisar('¡Gracias! CidIA lo está ordenando y tu responsable lo revisará.')
      reiniciar()
      onEnviada(ap)
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
    }
  }

  const selectorTarea = tareas.length > 0 && (
    <Campo etiqueta={<><Wrench size={14} /> ¿Con qué tarea tiene que ver?</>} ayuda="Opcional. Ayuda a que el copiloto lo encuentre cuando alguien esté con esa tarea.">
      <Selector value={tareaId} onChange={(e) => setTareaId(e.target.value)} vacio="Ninguna en concreto"
        opciones={tareas.map((t) => ({ valor: t.id, texto: nombreTarea(t) }))} />
    </Campo>
  )

  return (
    <Tarjeta className="apo-hero" relleno={false}>
      <div className="apo-hero-cabecera">
        <div className="apo-hero-icono"><Lightbulb /></div>
        <div>
          <h2>¿Has resuelto algo que otros deberían saber?</h2>
          <div className="apagado">Cuéntalo en un minuto: qué pasaba, por qué y cómo lo arreglaste. CidIA lo ordena por ti.</div>
        </div>
      </div>

      {laguna && (
        <div className="apo-respondes">
          <HelpCircle />
          <div className="crece">
            <div className="diminuto apagado">Respondes a una pregunta pendiente</div>
            <div className="negrita">«{laguna.pregunta}»</div>
          </div>
          <Boton variante="fantasma" tamano="pequeno" icono={<X />} onClick={onQuitarLaguna} aria-label="No enlazar con esta pregunta" />
        </div>
      )}

      {modo === 'elegir' && (
        <div className="apo-opciones">
          <button type="button" className="apo-opcion" onClick={() => setModo('texto')}>
            <span className="apo-opcion-icono"><PenLine /></span>
            <span>
              <span className="negrita">Escribirlo</span>
              <span className="pequeno apagado">Unas líneas bastan</span>
            </span>
            <ArrowRight className="apo-opcion-flecha" />
          </button>
          <div className="apo-opcion apo-opcion-voz">
            <GrabadorNota nota={nota} compacto onCambio={(n) => { setNota(n); if (n) setModo('voz') }} />
          </div>
        </div>
      )}

      {modo !== 'elegir' && (
        <div className="apo-formulario">
          <div className="apo-conmutador" role="tablist">
            <button type="button" role="tab" aria-selected={modo === 'texto'} className={modo === 'texto' ? 'activo' : ''}
              onClick={() => setModo('texto')}><PenLine /> Escribir</button>
            <button type="button" role="tab" aria-selected={modo === 'voz'} className={modo === 'voz' ? 'activo' : ''}
              onClick={() => setModo('voz')}><Mic /> Nota de voz</button>
          </div>

          {modo === 'texto' ? (
            <Campo>
              <textarea ref={areaTexto} className="area" value={texto} rows={6} maxLength={8000} onChange={(e) => setTexto(e.target.value)}
                placeholder={'Por ejemplo: «La prensa 3 se atascaba al cambiar de molde porque el sensor S4 quedaba sucio. '
                  + 'Lo limpié con aire y reinicié el ciclo en modo manual.»'} />
              <div className="apo-contador diminuto apagado">
                {texto.trim().length > 0 && !textoValido ? 'Cuéntalo con algo más de detalle' : ''}
                <span>{texto.length} / 8000</span>
              </div>
            </Campo>
          ) : (
            <>
              <div className="apo-voz-panel"><GrabadorNota nota={nota} onCambio={setNota} /></div>
              {nota && (
                <Campo etiqueta="¿Quieres añadir algo por escrito?">
                  <Area value={texto} rows={2} maxLength={8000} onChange={(e) => setTexto(e.target.value)}
                    placeholder="Opcional: un código, una medida, el nombre de una pieza…" />
                </Campo>
              )}
            </>
          )}

          {selectorTarea}

          <div className="apo-formulario-pie">
            <Boton variante="fantasma" onClick={() => { reiniciar(); onQuitarLaguna() }} disabled={enviando}>Cancelar</Boton>
            <Boton variante="primario" icono={<Send />} cargando={enviando} disabled={!puedeEnviar} onClick={enviar}>
              Enviar aportación
            </Boton>
          </div>
        </div>
      )}
    </Tarjeta>
  )
}

// ------------------------------------------------------------------ preguntas pendientes

function PreguntasPendientes({ cargando, error, reintentar, lista, seleccionada, onResponder }: {
  cargando: boolean; error: unknown; reintentar: () => void; lista: PreguntaPendiente[]; seleccionada: number | null
  onResponder: (p: PreguntaPendiente) => void
}) {
  const [todas, setTodas] = useState(false)
  const visibles = todas ? lista : lista.slice(0, 4)
  return (
    <section className="mt-3">
      <div className="apo-seccion-titulo">
        <h2><HelpCircle /> Preguntas pendientes en tu departamento</h2>
        {lista.length > 0 && <Etiqueta tono="naranja">{lista.length}</Etiqueta>}
      </div>
      <p className="apagado pequeno apo-seccion-sub">
        Son preguntas de tus compañeros que el copiloto todavía no sabe responder. Si sabes la respuesta, compártela.
      </p>
      {cargando ? (
        <div className="rejilla c2">{[0, 1].map((i) => <Esqueleto key={i} alto={112} />)}</div>
      ) : error ? (
        <Tarjeta><ErrorCarga error={error} reintentar={reintentar} /></Tarjeta>
      ) : lista.length === 0 ? (
        <Tarjeta>
          <Vacio icono={<CheckCircle2 />} titulo="No hay preguntas pendientes">
            El copiloto está respondiendo con respaldo todo lo que pregunta tu departamento. Si algún día no sabe algo, aparecerá aquí.
          </Vacio>
        </Tarjeta>
      ) : (
        <>
          <div className="rejilla c2">
            {visibles.map((p) => (
              <div key={p.id} className={`tarjeta apo-pregunta ${seleccionada === p.id ? 'seleccionada' : ''}`}>
                <div className="apo-pregunta-texto">«{p.pregunta}»</div>
                <div className="fila envolver diminuto apagado">
                  <span>Preguntada {veces(p.frecuencia)}{p.ultima_vez && <> · última {hace(p.ultima_vez)}</>}</span>
                  {p.tarea && <Etiqueta icono={<Wrench />}>{nombreTarea(p.tarea)}</Etiqueta>}
                </div>
                <div className="apo-pregunta-pie">
                  {p.mi_respuesta ? (
                    <Etiqueta tono="verde" icono={<CheckCircle2 />}>Tu respuesta está en revisión</Etiqueta>
                  ) : (
                    <>
                      {p.respuestas_en_revision > 0 && <Etiqueta tono="azul">Ya hay una respuesta en revisión</Etiqueta>}
                      <Boton variante={seleccionada === p.id ? 'oscuro' : 'secundario'} tamano="pequeno" icono={<Lightbulb />}
                        onClick={() => onResponder(p)}>
                        {seleccionada === p.id ? 'Respondiendo…' : 'Yo sé la respuesta'}
                      </Boton>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
          {lista.length > 4 && (
            <div className="centro mt-2">
              <Boton variante="fantasma" tamano="pequeno" onClick={() => setTodas((t) => !t)}>
                {todas ? 'Ver menos' : `Ver las ${lista.length} preguntas`}
              </Boton>
            </div>
          )}
        </>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ mis aportaciones

function MisAportaciones({ datos, cargando, error, reintentar, onRetirada }: {
  datos: RespuestaMias | null; cargando: boolean; error: unknown; reintentar: () => void; onRetirada: (id: number) => void
}) {
  const [abierta, setAbierta] = useState<number | null>(null)
  const lista = datos?.aportaciones ?? []
  // La más reciente (también la que se acaba de enviar) se muestra desplegada.
  const primera = lista[0]?.id
  useEffect(() => { if (primera !== undefined) setAbierta(primera) }, [primera])

  const resumen = datos?.resumen
  return (
    <section className="mt-4">
      <div className="apo-seccion-titulo">
        <h2><BookOpenCheck /> Mis aportaciones</h2>
        {resumen && lista.length > 0 && (
          <div className="fila envolver">
            {resumen.validada > 0 && <Etiqueta tono="verde">{resumen.validada} {resumen.validada === 1 ? 'validada' : 'validadas'}</Etiqueta>}
            {resumen.pendiente + resumen.procesando > 0 && (
              <Etiqueta tono="amarilla">{resumen.pendiente + resumen.procesando} en revisión</Etiqueta>
            )}
          </div>
        )}
      </div>
      {cargando ? (
        <div className="columna">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={68} />)}</div>
      ) : error ? (
        <Tarjeta><ErrorCarga error={error} reintentar={reintentar} /></Tarjeta>
      ) : lista.length === 0 ? (
        <Tarjeta>
          <Vacio icono={<Lightbulb />} titulo="Todavía no has compartido nada">
            Tu primera aportación puede ahorrarle una parada a un compañero. Cuenta algo que hayas resuelto hace poco.
          </Vacio>
        </Tarjeta>
      ) : (
        <div className="columna">
          {lista.map((ap) => (
            <TarjetaMia key={ap.id} ap={ap} abierta={abierta === ap.id}
              onAlternar={() => setAbierta((a) => (a === ap.id ? -1 : ap.id))} onRetirada={onRetirada} />
          ))}
        </div>
      )}
    </section>
  )
}

/** Pregunta con la que probar lo publicado: la de la laguna que respondía o, si no, su problema. */
function preguntaDePrueba(ap: Aportacion): string {
  if (ap.laguna) return ap.laguna.pregunta
  const problema = (ap.problema ?? '').trim().replace(/[.\s]+$/, '')
  if (problema && problema.length <= 200) return `${problema}. ¿Qué hago?`
  return ap.titulo ?? ap.documento?.titulo ?? ''
}

function TarjetaMia({ ap, abierta, onAlternar, onRetirada }: {
  ap: Aportacion; abierta: boolean; onAlternar: () => void; onRetirada: (id: number) => void
}) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const [verPublicado, setVerPublicado] = useState(false)
  const [retirando, setRetirando] = useState(false)

  const titulo = ap.estado === 'procesando' ? 'Ordenando tu aportación…' : ap.titulo || 'Aportación sin título'
  const meta = useMemo(() => {
    const partes = [`Enviada ${hace(ap.creada)}`]
    if (ap.via === 'voz') partes.push(`nota de voz${ap.duracion_audio ? ` de ${mmss(ap.duracion_audio)}` : ''}`)
    if (ap.tarea) partes.push(nombreTarea(ap.tarea))
    return partes.join(' · ')
  }, [ap])

  async function retirar() {
    const ok = await confirmar('Retirar aportación', 'Se borrará y tu responsable ya no la verá. ¿Quieres retirarla?', true)
    if (!ok) return
    setRetirando(true)
    try {
      await del(`/api/aportaciones/${ap.id}`)
      avisar('Aportación retirada.')
      onRetirada(ap.id)
    } catch (e) {
      avisarError(e)
      setRetirando(false)
    }
  }

  return (
    <div className={`tarjeta apo-mia estado-${ap.estado} ${abierta ? 'abierta' : ''}`}>
      <button type="button" className="apo-mia-cabecera" onClick={onAlternar} aria-expanded={abierta}>
        <span className="apo-mia-icono">{ap.via === 'voz' ? <Mic /> : <PenLine />}</span>
        <span className="crece">
          <span className="apo-mia-titulo">{titulo}</span>
          <span className="diminuto apagado">{meta}</span>
        </span>
        <EtiquetaEstado estado={ap.estado} />
      </button>

      {abierta && (
        <div className="apo-mia-cuerpo">
          {ap.estado === 'procesando' && (
            <Aviso>CidIA está transcribiendo y ordenando tu aportación. Tardará unos segundos.</Aviso>
          )}
          {ap.estado === 'pendiente' && (
            <Aviso tono="amarillo">Tu responsable la revisará pronto. Mientras tanto puedes retirarla si te has equivocado.</Aviso>
          )}
          {ap.estado === 'validada' && (
            <Aviso tono="exito" titulo={`Validada por ${ap.revisada_por ?? 'tu responsable'}${ap.validada_en ? ` el ${fecha(ap.validada_en)}` : ''}`}>
              Ya forma parte del conocimiento de tu departamento: el copiloto la citará con tu nombre. ¡Gracias!
            </Aviso>
          )}
          {ap.estado === 'rechazada' && (
            <Aviso tono="alerta" titulo={`No se ha publicado${ap.revisada_por ? ` · lo revisó ${ap.revisada_por}` : ''}`}>
              {ap.motivo_rechazo ? <>Motivo: «{ap.motivo_rechazo}»</> : 'No se indicó el motivo.'}
            </Aviso>
          )}

          {ap.laguna && (
            <div className="apo-respondia"><HelpCircle /> Respondía a «{ap.laguna.pregunta}»</div>
          )}

          <FichaAportacion ap={ap} />

          {ap.etiquetas.length > 0 && (
            <div className="fila envolver">{ap.etiquetas.map((e) => <Etiqueta key={e}>{e}</Etiqueta>)}</div>
          )}

          {ap.via === 'voz' && ap.audio_url && (
            <div className="apo-audio">
              <audio controls preload="none" src={urlServidor(ap.audio_url)} className="apo-audio-control" />
            </div>
          )}
          {ap.via === 'voz' && ap.estado !== 'procesando' && !ap.transcripcion && (
            <div className="pequeno apagado">No se ha podido transcribir la nota: tu responsable la escuchará.</div>
          )}
          {(ap.transcripcion || (ap.via === 'texto' && ap.texto_original)) && ap.estado !== 'procesando' && (
            <Plegable titulo={ap.via === 'voz' ? 'Ver lo que dijiste (transcripción)' : 'Ver lo que escribiste'}>
              <div className="pre pequeno">{ap.transcripcion ?? ap.texto_original}</div>
              {ap.via === 'voz' && ap.texto_original && <div className="pre pequeno mt-1">{ap.texto_original}</div>}
            </Plegable>
          )}

          <div className="apo-mia-acciones">
            {ap.estado === 'validada' && ap.documento && (
              <>
                <Boton variante="secundario" tamano="pequeno" icono={<BookOpenCheck />} onClick={() => setVerPublicado(true)}>
                  Ver lo publicado
                </Boton>
                {ap.documento.estado === 'listo' && (
                  <Link to={`/copiloto?pregunta=${encodeURIComponent(preguntaDePrueba(ap))}`} className="boton fantasma pequeno">
                    <MessageSquare /> Pruébalo en el copiloto
                  </Link>
                )}
              </>
            )}
            {(ap.estado === 'pendiente' || ap.estado === 'procesando') && (
              <Boton variante="peligro" tamano="pequeno" icono={<Trash2 />} cargando={retirando} onClick={retirar}>
                Retirar
              </Boton>
            )}
          </div>
        </div>
      )}

      {ap.documento && (
        <Modal abierto={verPublicado} titulo={ap.documento.titulo} onCerrar={() => setVerPublicado(false)}
          pie={<Boton onClick={() => setVerPublicado(false)}>Cerrar</Boton>}>
          <div className="fila envolver mb-2">
            <Etiqueta tono="amarilla" icono={<BookOpenCheck />}>Pregunta frecuente</Etiqueta>
            <Etiqueta>Aportada por ti</Etiqueta>
            {ap.revisada_por && <Etiqueta tono="verde">Validada por {ap.revisada_por}</Etiqueta>}
          </div>
          {ap.documento.estado !== 'listo' && (
            <div className="mb-2"><Aviso>Se está incorporando al conocimiento: en unos segundos el copiloto podrá citarla.</Aviso></div>
          )}
          {ap.documento.contenido ? <ContenidoPublicado texto={ap.documento.contenido} /> : <FichaAportacion ap={ap} />}
        </Modal>
      )}
      {dialogo}
    </div>
  )
}
