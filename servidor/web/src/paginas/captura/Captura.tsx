// Captura del conocimiento del experto por tres vías (vídeo narrado, nota de voz y entrevista
// guiada) y lista de mis capturas con su progreso en vivo (sondeo cada 3 s mientras se procesan).

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight, BookOpen, Check, Clapperboard, FileAudio, ListChecks, MessagesSquare, Mic, RotateCcw, Send,
  Trash2, Upload, Video,
} from 'lucide-react'
import { del, get, hace, post, subir, urlServidor } from '../../api'
import {
  BarraProgreso, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Tarjeta, Vacio,
  ZonaSubida, useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import SelectorTarea, { useTareas } from '../instrucciones/SelectorTarea'
import { textoTarea } from '../instrucciones/tipos'
import GrabadorVoz from './GrabadorVoz'
import RevisarFicha from './RevisarFicha'
import { enProceso, mmss, NOMBRE_TIPO, type Captura } from './tipos'
import './captura.css'

const EXT_VIDEO = /\.(mp4|mov|m4v|webm|mkv|avi|3gp|mpe?g|wmv)$/i
const EXT_AUDIO = /\.(webm|weba|ogg|oga|opus|mp3|wav|m4a|aac|flac|amr)$/i
const TEMAS_ENTREVISTA = ['Objetivo', 'Preparación', 'Pasos', 'Puntos críticos', 'Errores típicos', 'Trucos', 'Calidad']

interface NotaGrabada { blob: Blob; url: string; segundos: number }

export default function PaginaCaptura() {
  const navegar = useNavigate()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const tareas = useTareas()
  const lista = useDatos((s) => get<Captura[]>('/api/captura', s), [])
  const [tareaId, setTareaId] = useState('')
  const [titulo, setTitulo] = useState('')
  const [subida, setSubida] = useState<{ nombre: string; pct: number; tipo: 'video' | 'audio' } | null>(null)
  const [nota, setNota] = useState<NotaGrabada | null>(null)
  const [iniciando, setIniciando] = useState(false)
  const [ficha, setFicha] = useState<number | null>(null)
  const entradaAudio = useRef<HTMLInputElement>(null)
  const { setDatos } = lista

  const tarea = tareas.datos?.find((t) => String(t.id) === tareaId) ?? null
  const sinTareas = !tareas.cargando && !tareas.error && !tareas.datos?.length

  // Sondeo mientras haya capturas en proceso, y aviso cuando una termina.
  const hayActivas = !!lista.datos?.some(enProceso)
  const estados = useRef<Record<number, string>>({})
  useEffect(() => {
    if (!hayActivas) return
    const t = setInterval(() => {
      get<Captura[]>('/api/captura').then(setDatos).catch(() => { /* se reintenta en el siguiente ciclo */ })
    }, 3000)
    return () => clearInterval(t)
  }, [hayActivas, setDatos])
  useEffect(() => {
    for (const c of lista.datos ?? []) {
      const antes = estados.current[c.id]
      if (antes && antes !== c.estado && (antes === 'procesando' || antes === 'subida')) {
        if (c.estado === 'borrador_listo') avisar(`El borrador de «${c.titulo ?? NOMBRE_TIPO[c.tipo]}» está listo para revisar.`)
        if (c.estado === 'error') avisar(`No se ha podido procesar «${c.titulo ?? NOMBRE_TIPO[c.tipo]}».`, 'error')
      }
      estados.current[c.id] = c.estado
    }
  }, [lista.datos, avisar])

  // Libera la URL del audio grabado al cambiarlo o al salir.
  useEffect(() => () => { if (nota) URL.revokeObjectURL(nota.url) }, [nota])

  function anadir(c: Captura) {
    setDatos((prev) => [c, ...(prev ?? []).filter((x) => x.id !== c.id)])
  }

  function formulario(fichero: Blob, nombre: string): FormData {
    const fd = new FormData()
    fd.append('fichero', fichero, nombre)
    if (tareaId) fd.append('tarea_id', tareaId)
    if (titulo.trim()) fd.append('titulo', titulo.trim())
    return fd
  }

  async function enviar(tipo: 'video' | 'audio', fichero: Blob, nombre: string) {
    if (subida) {
      // Una subida cada vez: la barra de progreso es una sola y el segundo fichero pisaría al primero.
      avisar('Espera a que termine la subida en curso.', 'info')
      return false
    }
    setSubida({ nombre, pct: 0, tipo })
    try {
      const c = await subir<Captura>(`/api/captura/${tipo}`, formulario(fichero, nombre),
        (pct) => setSubida({ nombre, pct, tipo }))
      anadir(c)
      avisar(tipo === 'video' ? 'Vídeo recibido. CidIA está preparando el borrador de la instrucción.'
        : 'Nota recibida. CidIA la está transcribiendo y ordenando.')
      setTitulo('')
      return true
    } catch (e) {
      avisarError(e)
      return false
    } finally {
      setSubida(null)
    }
  }

  function elegirVideo(ficheros: File[]) {
    const f = ficheros[0]
    if (!f.type.startsWith('video/') && !EXT_VIDEO.test(f.name)) {
      avisar('Elige un fichero de vídeo (MP4, MOV, WebM…).', 'error')
      return
    }
    enviar('video', f, f.name)
  }

  function elegirAudio(f: File | undefined) {
    if (!f) return
    if (!f.type.startsWith('audio/') && !EXT_AUDIO.test(f.name)) {
      avisar('Elige un fichero de audio (MP3, M4A, WAV, OGG…).', 'error')
      return
    }
    enviar('audio', f, f.name)
  }

  async function enviarNota() {
    if (!nota) return
    const ext = nota.blob.type.includes('ogg') ? 'ogg' : nota.blob.type.includes('mp4') ? 'm4a' : 'webm'
    if (await enviar('audio', nota.blob, `nota-de-voz.${ext}`)) setNota(null)
  }

  async function empezarEntrevista() {
    if (!tareaId && !titulo.trim()) {
      avisar('Elige la tarea o escribe el tema de la entrevista.', 'error')
      return
    }
    setIniciando(true)
    try {
      const c = await post<Captura>('/api/captura/entrevista', tareaId ? { tarea_id: Number(tareaId) } : { tema: titulo.trim() })
      navegar(`/captura/entrevista/${c.id}`)
    } catch (e) {
      avisarError(e)
      setIniciando(false)
    }
  }

  async function reintentar(c: Captura) {
    try {
      anadir(await post<Captura>(`/api/captura/${c.id}/reintentar`))
      avisar('Lo volvemos a intentar.', 'info')
    } catch (e) {
      avisarError(e)
    }
  }

  async function borrar(c: Captura) {
    const ok = await confirmar('Borrar la captura', (
      <>
        <p>Se borrará «{c.titulo ?? NOMBRE_TIPO[c.tipo]}» y, si no está publicado, el borrador que generó.</p>
        <p className="mb-1">Lo que ya esté publicado se conserva.</p>
      </>
    ), true)
    if (!ok) return
    try {
      await del(`/api/captura/${c.id}`)
      setDatos((prev) => (prev ?? []).filter((x) => x.id !== c.id))
      avisar('Captura borrada')
    } catch (e) {
      avisarError(e)
    }
  }

  function abrirBorrador(c: Captura) {
    if (c.borrador?.tipo === 'instruccion') navegar(`/instrucciones/${c.borrador.id}`)
    else if (c.borrador?.tipo === 'ficha') setFicha(c.id)
  }

  const subiendoVideo = subida?.tipo === 'video'
  const subiendoAudio = subida?.tipo === 'audio'

  return (
    <>
      <Cabecera
        antetitulo={<><Clapperboard size={14} />Conocimiento</>}
        titulo="Captura"
        subtitulo="Graba la tarea mientras la explicas, deja una nota de voz o deja que el copiloto te entreviste. CidIA prepara el borrador y tú decides qué se publica."
      />

      <Tarjeta className="cap-tarea">
        <div className="cap-tarea-fila">
          <div className="cap-paso-numero">1</div>
          <Campo etiqueta="¿Sobre qué tarea?" ayuda={tarea ? `${tarea.departamento ?? ''}${tarea.publicada ? ` · versión vigente v${tarea.publicada.version}` : ' · todavía sin instrucción publicada'}` : 'Si es una tarea que aún no existe, CidIA la creará en tu departamento.'}>
            {tareas.error ? <ErrorCarga error={tareas.error} reintentar={tareas.recargar} /> : (
              <SelectorTarea tareas={tareas.datos} valor={tareaId} onCambio={setTareaId} cargando={tareas.cargando}
                vacio="Tarea nueva o tema libre" id="cap-tarea" />
            )}
          </Campo>
          <Campo etiqueta={tareaId ? 'Título (opcional)' : 'Nombre de la tarea o tema'}>
            <Entrada value={titulo} maxLength={300} onChange={(e) => setTitulo(e.target.value)}
              placeholder={tareaId ? `Por ejemplo: ${tarea?.nombre ?? 'cambio de turno'}, versión de noche` : 'Por ejemplo: cambio de bobina de la línea 3'} />
          </Campo>
        </div>
        {sinTareas && (
          <div className="pequeno apagado">Tu departamento aún no tiene tareas dadas de alta: puedes capturar igualmente con un tema libre.</div>
        )}
      </Tarjeta>

      <div className="cap-paso-titulo"><div className="cap-paso-numero">2</div><h2>Elige cómo contarlo</h2></div>
      <div className="rejilla c3 cap-vias">
        <Tarjeta className="cap-via">
          <div className="cap-via-icono video"><Video /></div>
          <h3>Grabar o subir un vídeo</h3>
          <p>Grábate con el móvil haciendo la tarea y explicándola en voz alta. CidIA la convierte en pasos con imagen y clip.</p>
          <div className="cap-via-accion">
            {subiendoVideo ? (
              <div className="cap-subiendo">
                <div className="fila entre pequeno"><span className="recortar negrita">{subida.nombre}</span><span>{subida.pct} %</span></div>
                <BarraProgreso valor={subida.pct} tono="amarilla" />
                <div className="pequeno apagado">{subida.pct < 100 ? 'Subiendo el vídeo…' : 'Recibido, preparando…'} No cierres esta página.</div>
              </div>
            ) : (
              <div className={subida ? 'cap-bloqueada' : undefined} aria-disabled={!!subida}>
                <ZonaSubida acepta="video/*" onFicheros={elegirVideo} texto="Arrastra el vídeo o haz clic para elegirlo"
                  detalle="MP4, MOV o WebM. Mejor en horizontal y con buena luz." />
              </div>
            )}
          </div>
        </Tarjeta>

        <Tarjeta className="cap-via">
          <div className="cap-via-icono voz"><Mic /></div>
          <h3>Nota de voz</h3>
          <p>Para lo que no se ve con las manos: trucos, averías, criterios. CidIA la ordena en una ficha que revisas antes de publicar.</p>
          <div className="cap-via-accion">
            {subiendoAudio ? (
              <div className="cap-subiendo">
                <div className="fila entre pequeno"><span className="recortar negrita">{subida.nombre}</span><span>{subida.pct} %</span></div>
                <BarraProgreso valor={subida.pct} />
              </div>
            ) : nota ? (
              <div className="cap-nota">
                <div className="fila pequeno negrita"><FileAudio size={16} />Nota de {mmss(nota.segundos)}</div>
                <audio controls src={nota.url} className="cap-audio" />
                <div className="fila">
                  <Boton tamano="pequeno" icono={<RotateCcw />} onClick={() => setNota(null)}>Descartar</Boton>
                  <Boton variante="primario" tamano="pequeno" icono={<Send />} onClick={enviarNota}>Enviar nota</Boton>
                </div>
              </div>
            ) : (
              <>
                <GrabadorVoz ocupado={!!subida} ayuda="Hasta 10 minutos. Habla con calma, como si se lo contaras a un compañero."
                  onAudio={(blob, segundos) => setNota({ blob, segundos, url: URL.createObjectURL(blob) })} />
                <button type="button" className="cap-enlace" disabled={!!subida} onClick={() => entradaAudio.current?.click()}>
                  <Upload size={14} />o sube un audio
                </button>
                <input ref={entradaAudio} type="file" hidden accept="audio/*"
                  onChange={(e) => { elegirAudio(e.target.files?.[0]); e.target.value = '' }} />
              </>
            )}
          </div>
        </Tarjeta>

        <Tarjeta className="cap-via">
          <div className="cap-via-icono entrevista"><MessagesSquare /></div>
          <h3>Entrevista guiada</h3>
          <p>El copiloto te pregunta, una cosa cada vez, y se adapta a lo que cuentas. Puedes responder escribiendo o por voz.</p>
          <div className="cap-temas">
            {TEMAS_ENTREVISTA.map((t) => <span key={t}>{t}</span>)}
          </div>
          <div className="cap-via-accion">
            <Boton variante="oscuro" bloque icono={<ArrowRight />} onClick={empezarEntrevista} cargando={iniciando}>
              Empezar entrevista
            </Boton>
          </div>
        </Tarjeta>
      </div>

      <Tarjeta titulo="Mis capturas" icono={<ListChecks size={18} />} className="mt-3"
        acciones={hayActivas && <span className="pequeno apagado">Actualizando cada 3 s…</span>}>
        {lista.error ? <ErrorCarga error={lista.error} reintentar={lista.recargar} />
          : lista.cargando && !lista.datos ? (
            <div className="columna">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={64} />)}</div>
          ) : !lista.datos?.length ? (
            <Vacio icono={<Clapperboard />} titulo="Todavía no has capturado nada">
              Empieza por la tarea que más dudas genera: grábala explicándola en voz alta o deja que el copiloto te entreviste.
            </Vacio>
          ) : (
            <div className="cap-lista">
              {lista.datos.map((c) => (
                <FilaCaptura key={c.id} c={c} onRevisar={() => abrirBorrador(c)} onBorrar={() => borrar(c)}
                  onReintentar={() => reintentar(c)} onContinuar={() => navegar(`/captura/entrevista/${c.id}`)} />
              ))}
            </div>
          )}
      </Tarjeta>

      <RevisarFicha capturaId={ficha} onCerrar={() => setFicha(null)} onCambio={anadir} />
      {dialogo}
    </>
  )
}

function EstadoCaptura({ c }: { c: Captura }) {
  if (c.estado === 'subida') return <Etiqueta tono="azul">En cola</Etiqueta>
  if (c.estado === 'procesando') return <Etiqueta tono="amarilla">Procesando</Etiqueta>
  if (c.estado === 'en_curso') return <Etiqueta tono="azul">En curso</Etiqueta>
  if (c.estado === 'error') return <Etiqueta tono="roja">Error</Etiqueta>
  if (!c.borrador) return <Etiqueta>Borrador descartado</Etiqueta>
  if (c.borrador.estado === 'publicada') return <Etiqueta tono="verde" icono={<Check />}>Publicada</Etiqueta>
  if (c.borrador?.estado === 'obsoleta') return <Etiqueta tono="oscura">Obsoleta</Etiqueta>
  return <Etiqueta tono="naranja">Por revisar</Etiqueta>
}

function FilaCaptura({ c, onRevisar, onBorrar, onReintentar, onContinuar }: {
  c: Captura; onRevisar: () => void; onBorrar: () => void; onReintentar: () => void; onContinuar: () => void
}) {
  const icono = c.tipo === 'video' ? <Video /> : c.tipo === 'audio' ? <Mic /> : <MessagesSquare />
  const activa = enProceso(c)
  const indice = c.fases.findIndex((f) => f.clave === c.fase)
  const esFicha = c.borrador?.tipo === 'ficha'
  const publicado = c.borrador?.estado === 'publicada' || c.borrador?.estado === 'obsoleta'
  return (
    <div className={`cap-fila ${activa ? 'activa' : ''}`}>
      {c.miniatura_url ? <img className="cap-miniatura" src={urlServidor(c.miniatura_url)} alt="" />
        : <div className={`cap-miniatura icono ${c.tipo}`}>{icono}</div>}
      <div className="crece">
        <div className="fila envolver cap-fila-titulo">
          <span className="negrita recortar">{c.titulo ?? NOMBRE_TIPO[c.tipo]}</span>
          <EstadoCaptura c={c} />
        </div>
        <div className="pequeno apagado cap-fila-meta">
          <span>{NOMBRE_TIPO[c.tipo]}</span>
          {c.tarea && <span>{textoTarea(c.tarea)}</span>}
          {c.duracion ? <span>{mmss(c.duracion)}</span> : null}
          {c.entrevista && c.estado === 'en_curso' && <span>{c.entrevista.respuestas} respuestas</span>}
          <span>{hace(c.creada)}</span>
        </div>
        {activa && (
          <div className="cap-progreso">
            <div className="cap-fases">
              {c.fases.filter((f) => f.clave !== 'listo').map((f, i) => (
                <span key={f.clave} className={`cap-fase ${i < indice ? 'hecha' : i === indice ? 'actual' : ''}`}>
                  {i < indice && <Check size={12} />}{f.texto}
                </span>
              ))}
            </div>
            <BarraProgreso valor={c.progreso} tono="amarilla" />
          </div>
        )}
        {c.estado === 'error' && c.mensaje && <div className="cap-error pequeno">{c.mensaje}</div>}
        {c.estado === 'borrador_listo' && c.origen_borrador === 'segmentos' && !publicado && (
          <div className="pequeno apagado mt-1">El modelo no pudo proponer los pasos: el borrador sigue los cambios de plano del vídeo.</div>
        )}
      </div>
      <div className="cap-fila-acciones">
        {c.estado === 'borrador_listo' && c.borrador && (
          <Boton variante={publicado ? 'secundario' : 'primario'} tamano="pequeno"
            icono={esFicha ? <BookOpen /> : <ListChecks />} onClick={onRevisar}>
            {publicado ? (esFicha ? 'Ver ficha' : 'Ver instrucción') : 'Revisar borrador'}
          </Boton>
        )}
        {c.estado === 'en_curso' && (
          <Boton variante="primario" tamano="pequeno" icono={<ArrowRight />} onClick={onContinuar}>Continuar</Boton>
        )}
        {c.estado === 'error' && (
          <Boton tamano="pequeno" icono={<RotateCcw />} onClick={onReintentar}>Reintentar</Boton>
        )}
        {!activa && (
          <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} onClick={onBorrar} aria-label="Borrar la captura" title="Borrar" />
        )}
      </div>
    </div>
  )
}
