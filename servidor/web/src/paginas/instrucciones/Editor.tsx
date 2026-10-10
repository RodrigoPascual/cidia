// Editor de una instrucción de trabajo.
//  · Borrador: pasos reordenables (imagen, clip, texto, criterio de aceptación y marcas de crítico
//    y seguridad), datos generales, vídeo original con salto a cada paso y publicación.
//  · Publicada u obsoleta: vista de solo lectura, nueva versión e historial con diferencias.

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CopyPlus, FileText,
  Film, HardHat, History, ImageIcon, ImagePlus, ListChecks, Loader2, PlayCircle, Plus, Quote, Save, Send, ShieldAlert,
  Trash2, User, UserCheck, Video, Wrench,
} from 'lucide-react'
import { del, enviarFormulario, fecha, get, post, put, urlServidor } from '../../api'
import { useSesion } from '../../sesion'
import {
  Area, Aviso, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Interruptor, Tarjeta, TextoFormato,
  Vacio, useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import Historial from './Historial'
import { ESTADOS, mmss, textoTarea, type Instruccion, type Paso, type Segmento } from './tipos'
import './instrucciones.css'

interface PasoEdicion extends Paso {
  clave: string // identifica el paso en la lista aunque aún no tenga id
}

interface Edicion {
  id: number // instrucción a la que pertenece esta copia local
  titulo: string
  codigo: string
  resumen: string
  riesgos: string
  epis: string
  herramientas: string
  pasos: PasoEdicion[]
}

let contadorClaves = 0
const nuevaClave = () => `nuevo-${++contadorClaves}`

function aEdicion(ins: Instruccion): Edicion {
  return {
    id: ins.id,
    titulo: ins.titulo,
    codigo: ins.codigo ?? '',
    resumen: ins.resumen,
    riesgos: ins.riesgos,
    epis: ins.epis,
    herramientas: ins.herramientas,
    pasos: (ins.pasos ?? []).map((p) => ({ ...p, clave: `p${p.id}` })),
  }
}

type Ocupado = null | 'guardar' | 'publicar' | 'version' | 'imagen' | 'borrar'

export default function Editor() {
  const { id } = useParams()
  const navegar = useNavigate()
  const { perfil } = useSesion()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const { datos: ins, error, cargando, recargar, setDatos } = useDatos((s) => get<Instruccion>(`/api/instrucciones/${id}`, s), [id])
  const [ed, setEd] = useState<Edicion | null>(null)
  const [sel, setSel] = useState(0)
  const [sucio, setSucio] = useState(false)
  const [ocupado, setOcupado] = useState<Ocupado>(null)
  const [historial, setHistorial] = useState(false)
  const video = useRef<HTMLVideoElement>(null)
  const tarjetaVideo = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const guardarRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (ins) {
      setEd(aEdicion(ins))
      setSucio(false)
    }
  }, [ins])
  useEffect(() => setSel(0), [id])

  // Aviso del navegador si se cierra la pestaña con cambios sin guardar; Ctrl+S guarda.
  useEffect(() => {
    if (!sucio) return
    const alSalir = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', alSalir)
    return () => window.removeEventListener('beforeunload', alSalir)
  }, [sucio])
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        guardarRef.current()
      }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [])

  if (error) return <ErrorCarga error={error} reintentar={recargar} />
  // Al saltar a otra versión se muestra el esqueleto hasta que llega (y no la versión anterior).
  if (!ins || !ed || ed.id !== ins.id || (cargando && String(ins.id) !== id)) return <EsqueletoEditor />

  const editable = !!ins.editable
  const total = ed.pasos.length
  const indice = Math.min(sel, Math.max(0, total - 1))
  const paso = ed.pasos[indice]
  const estado = ESTADOS[ins.estado]

  // ------------------------------------------------------------------ edición local

  // En pantallas estrechas la lista de pasos queda encima del paso: al elegir uno se baja hasta él.
  function elegir(i: number) {
    setSel(i)
    if (window.matchMedia('(max-width: 1080px)').matches) {
      requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
  }

  function cambiar<K extends keyof Edicion>(campo: K, valor: Edicion[K]) {
    setEd((e) => (e ? { ...e, [campo]: valor } : e))
    setSucio(true)
  }

  function cambiarPaso(i: number, cambios: Partial<PasoEdicion>) {
    setEd((e) => (e ? { ...e, pasos: e.pasos.map((p, j) => (j === i ? { ...p, ...cambios } : p)) } : e))
    setSucio(true)
  }

  function mover(i: number, d: -1 | 1) {
    const j = i + d
    if (j < 0 || j >= total) return
    setEd((e) => {
      if (!e) return e
      const pasos = [...e.pasos]
      ;[pasos[i], pasos[j]] = [pasos[j], pasos[i]]
      return { ...e, pasos }
    })
    setSel(j)
    setSucio(true)
  }

  function anadir() {
    const nuevo: PasoEdicion = {
      id: null, clave: nuevaClave(), orden: total + 1, titulo: '', texto: '', es_critico: false, es_seguridad: false,
      criterio_aceptacion: '', imagen_url: null, clip_url: null, t_inicio: null, t_fin: null,
    }
    const donde = total ? indice + 1 : 0
    setEd((e) => (e ? { ...e, pasos: [...e.pasos.slice(0, donde), nuevo, ...e.pasos.slice(donde)] } : e))
    setSel(donde)
    setSucio(true)
  }

  async function quitar(i: number) {
    const p = ed!.pasos[i]
    const ok = await confirmar('Quitar el paso', `Se quitará el paso ${i + 1}${p.titulo ? ` «${p.titulo}»` : ''} de este borrador. `
      + 'El cambio se aplica al guardar.', true)
    if (!ok) return
    setEd((e) => (e ? { ...e, pasos: e.pasos.filter((_, j) => j !== i) } : e))
    setSel(Math.max(0, Math.min(i, total - 2)))
    setSucio(true)
  }

  // ------------------------------------------------------------------ servidor

  async function guardar(silencioso = false): Promise<Instruccion | null> {
    if (!ed || !ins) return null
    if (!ed.titulo.trim()) {
      avisar('La instrucción necesita un título.', 'error')
      return null
    }
    setOcupado('guardar')
    try {
      const r = await put<Instruccion>(`/api/instrucciones/${ins.id}`, {
        titulo: ed.titulo, codigo: ed.codigo, resumen: ed.resumen, riesgos: ed.riesgos, epis: ed.epis,
        herramientas: ed.herramientas,
        pasos: ed.pasos.map((p) => ({
          id: p.id, titulo: p.titulo, texto: p.texto, es_critico: p.es_critico, es_seguridad: p.es_seguridad,
          criterio_aceptacion: p.criterio_aceptacion,
        })),
      })
      setDatos(r)
      if (!silencioso) avisar('Cambios guardados')
      return r
    } catch (e) {
      avisarError(e)
      return null
    } finally {
      setOcupado(null)
    }
  }
  guardarRef.current = () => { if (editable && sucio && !ocupado) guardar() }

  async function publicar() {
    if (!ed || !ins) return
    if (!total) {
      avisar('Añade al menos un paso antes de publicar.', 'error')
      return
    }
    const sinTitulo = ed.pasos.findIndex((p) => !p.titulo.trim())
    if (sinTitulo >= 0) {
      setSel(sinTitulo)
      avisar(`El paso ${sinTitulo + 1} no tiene título.`, 'error')
      return
    }
    const autorEsOtro = ins.autor && ins.autor.id !== perfil?.id
    const ok = await confirmar(`Publicar la versión ${ins.version}`, (
      <>
        <p>«{ed.titulo}» pasará a ser la instrucción vigente de <strong>{ins.tarea.nombre}</strong>
          {ins.vigente ? <> y la versión {ins.vigente.version} quedará obsoleta</> : null}. Al publicarla:</p>
        <ul className="ins-lista-confirmar">
          <li>Se indexará en el conocimiento de {ins.tarea.departamento ?? 'su departamento'}: el copiloto la usará y la citará.</li>
          <li>Se prepararán las micro-lecciones y las preguntas de evaluación a partir de sus pasos.</li>
          <li>Quien tenga nivel ILUO en esta tarea quedará marcado para reevaluarse con la nueva versión.</li>
        </ul>
        <p className="mb-1">Figurarás como revisor{autorEsOtro ? ` y ${ins.autor!.nombre} como autor` : ''}.</p>
      </>
    ))
    if (!ok) return
    if (sucio && !(await guardar(true))) return
    setOcupado('publicar')
    try {
      const r = await post<Instruccion>(`/api/instrucciones/${ins.id}/publicar`)
      setDatos(r)
      const n = r.reevaluaciones ?? 0
      avisar(`Versión ${r.version} publicada.${n ? ` ${n} ${n === 1 ? 'persona deberá' : 'personas deberán'} reevaluarse.` : ''}`)
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }

  async function nuevaVersion() {
    if (!ins) return
    setOcupado('version')
    try {
      const r = await post<Instruccion>(`/api/instrucciones/${ins.id}/nueva-version`)
      avisar(r.ya_existia ? `Ya había un borrador (v${r.version}): lo abrimos.` : `Versión ${r.version} creada como borrador.`)
      navegar(`/instrucciones/${r.id}`)
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }

  async function borrar() {
    if (!ins) return
    const ok = await confirmar('Eliminar el borrador', `Se eliminará la versión ${ins.version} en borrador de «${ins.titulo}». `
      + 'Las versiones publicadas no se tocan. Esta acción no se puede deshacer.', true)
    if (!ok) return
    setOcupado('borrar')
    try {
      await del(`/api/instrucciones/${ins.id}`)
      setSucio(false)
      avisar('Borrador eliminado')
      navegar('/instrucciones')
    } catch (e) {
      avisarError(e)
      setOcupado(null)
    }
  }

  async function cambiarImagen(i: number, f: File) {
    if (!ins || !ed) return
    if (!/\.(jpe?g|png|webp)$/i.test(f.name)) {
      avisar('Elige una imagen JPG, PNG o WebP.', 'error')
      return
    }
    let pasoId = ed.pasos[i].id
    if (pasoId === null || sucio) {
      const r = await guardar(true) // el paso necesita existir en el servidor
      if (!r) return
      pasoId = r.pasos?.[i]?.id ?? null
    }
    if (pasoId === null) return
    setOcupado('imagen')
    const fd = new FormData()
    fd.append('fichero', f)
    try {
      setDatos(await enviarFormulario<Instruccion>(`/api/instrucciones/${ins.id}/pasos/${pasoId}/imagen`, fd))
      avisar('Imagen cambiada')
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }

  // Salir por un enlace del propio editor (miga, historial) sin perder cambios por descuido. La barra
  // lateral no se puede interceptar con BrowserRouter: para eso queda la barra de cambios sin guardar.
  async function irA(ruta: string) {
    if (sucio && !(await confirmar('Cambios sin guardar', 'Hay cambios sin guardar en este borrador. ¿Salir sin guardarlos?', true))) return
    setSucio(false)
    navegar(ruta)
  }

  function verEnVideo(t: number) {
    const v = video.current
    if (!v) return
    tarjetaVideo.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    v.currentTime = t
    v.play().catch(() => { /* el navegador puede pedir un clic antes de reproducir */ })
  }

  // ------------------------------------------------------------------ vista

  const acciones = editable ? (
    <>
      <Boton variante="fantasma" icono={<History />} onClick={() => setHistorial(true)}>Historial</Boton>
      <Boton variante="peligro" icono={<Trash2 />} onClick={borrar} cargando={ocupado === 'borrar'} disabled={!!ocupado}>Eliminar</Boton>
      <Boton icono={<Save />} onClick={() => guardar()} cargando={ocupado === 'guardar'} disabled={!sucio || !!ocupado}>Guardar</Boton>
      <Boton variante="verde" icono={<Send />} onClick={publicar} cargando={ocupado === 'publicar'} disabled={!!ocupado}>
        Publicar versión {ins.version}
      </Boton>
    </>
  ) : (
    <>
      <Boton icono={<History />} onClick={() => setHistorial(true)}>Historial{ins.n_versiones ? ` (${ins.n_versiones})` : ''}</Boton>
      {ins.borrador_existente ? (
        <Boton variante="primario" icono={<ArrowRight />} onClick={() => navegar(`/instrucciones/${ins.borrador_existente!.id}`)}>
          Abrir el borrador v{ins.borrador_existente.version}
        </Boton>
      ) : (
        <Boton variante="primario" icono={<CopyPlus />} onClick={nuevaVersion} cargando={ocupado === 'version'}>
          Crear nueva versión
        </Boton>
      )}
    </>
  )

  return (
    <div className="ins-editor-pagina">
      <Cabecera
        antetitulo={<>
          <ListChecks size={14} />
          <Link to="/instrucciones" className="ins-miga"
            onClick={(e) => { if (sucio) { e.preventDefault(); irA('/instrucciones') } }}>Instrucciones</Link>
          {' · '}{textoTarea(ins.tarea)}
        </>}
        titulo={<>{ed.codigo && <span className="ins-titulo-codigo">{ed.codigo}</span>}{ed.titulo || 'Sin título'}</>}
        subtitulo={
          <div className="ins-subtitulo">
            <Etiqueta tono={estado.tono}>{estado.texto}</Etiqueta>
            <Etiqueta tono="oscura">Versión {ins.version}</Etiqueta>
            {ins.tarea.departamento && <span>{ins.tarea.departamento}</span>}
            {ins.autor && <span><User />Autor: {ins.autor.nombre}</span>}
            {ins.revisor && <span><UserCheck />Revisor: {ins.revisor.nombre}</span>}
            <span>{ins.publicada_en ? `Publicada el ${fecha(ins.publicada_en)}` : `Creada el ${fecha(ins.creada)}`}</span>
            {sucio && <Etiqueta tono="naranja">Cambios sin guardar</Etiqueta>}
          </div>
        }
        acciones={acciones}
      />

      {ins.estado === 'publicada' && (
        <Aviso tono="exito" titulo="Versión vigente">
          El copiloto la usa y la cita, y el modo planta la muestra paso a paso. Para cambiarla, crea una nueva versión: esta se conservará en el historial.
        </Aviso>
      )}
      {ins.estado === 'obsoleta' && (
        <Aviso tono="amarillo" titulo="Versión obsoleta">
          Se conserva como historial y ya no se usa.
          {ins.vigente && <> La vigente es la <Link to={`/instrucciones/${ins.vigente.id}`}>versión {ins.vigente.version}</Link>.</>}
        </Aviso>
      )}
      {editable && ins.captura_id && (
        <Aviso tono="amarillo" titulo="Borrador preparado por CidIA">
          Se ha generado a partir de una captura. Revisa cada paso (texto, imagen y clip), marca los críticos y de seguridad y publícalo cuando esté listo. Nada llega al copiloto hasta que se publica.
        </Aviso>
      )}

      <div className="ins-editor">
        <Tarjeta relleno={false} className="ins-columna-pasos">
          <div className="ins-lista-cabecera">
            <h3>Pasos <span className="apagado">({total})</span></h3>
            {editable && <Boton tamano="pequeno" icono={<Plus />} onClick={anadir}>Añadir</Boton>}
          </div>
          {!total ? (
            <Vacio icono={<ListChecks />} titulo="Sin pasos"
              accion={editable && <Boton variante="primario" icono={<Plus />} onClick={anadir}>Añadir el primer paso</Boton>}>
              Una instrucción necesita al menos un paso para publicarse.
            </Vacio>
          ) : (
            <ol className="ins-pasos">
              {ed.pasos.map((p, i) => (
                <li key={p.clave} className={`ins-paso-item ${i === indice ? 'activo' : ''}`} onClick={() => elegir(i)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); elegir(i) } }}
                  tabIndex={0} aria-current={i === indice ? 'step' : undefined}>
                  <span className={`ins-numero ${p.es_critico ? 'critico' : ''}`}>{i + 1}</span>
                  {p.imagen_url ? <img src={urlServidor(p.imagen_url)} alt="" className="ins-paso-mini" loading="lazy" />
                    : <span className="ins-paso-mini vacia"><ImageIcon /></span>}
                  <div className="crece ins-paso-textos">
                    <div className="ins-paso-titulo">{p.titulo || <span className="apagado">Sin título</span>}</div>
                    <div className="ins-paso-marcas">
                      {p.es_critico && <span className="ins-marca critico"><AlertTriangle />Crítico</span>}
                      {p.es_seguridad && <span className="ins-marca seguridad"><ShieldAlert />Seguridad</span>}
                      {p.t_inicio !== null && <span className="diminuto apagado">{mmss(p.t_inicio)}</span>}
                    </div>
                  </div>
                  {editable && (
                    <div className="ins-mover" onClick={(e) => e.stopPropagation()}>
                      <button type="button" aria-label="Subir el paso" title="Subir" disabled={i === 0} onClick={() => mover(i, -1)}><ChevronUp /></button>
                      <button type="button" aria-label="Bajar el paso" title="Bajar" disabled={i === total - 1} onClick={() => mover(i, 1)}><ChevronDown /></button>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Tarjeta>

        {paso ? (
          <div ref={panel} className="ins-panel-ancla">
          <PanelPaso
            paso={paso} indice={indice} total={total} editable={editable}
            hayVideo={!!ins.video_url} subiendoImagen={ocupado === 'imagen'} dicho={dichoEn(ins.transcripcion, paso)}
            onCambio={(c) => cambiarPaso(indice, c)} onQuitar={() => quitar(indice)}
            onImagen={(f) => cambiarImagen(indice, f)} onVerVideo={verEnVideo}
            onIr={(i) => setSel(i)}
          />
          </div>
        ) : (
          <Tarjeta><Vacio icono={<FileText />} titulo="Elige o añade un paso">Aquí verás su imagen, su clip y su texto.</Vacio></Tarjeta>
        )}
      </div>

      <div className={`ins-inferior ${ins.video_url ? 'con-video' : ''}`}>
        <Tarjeta titulo="Datos generales" icono={<FileText size={18} />}>
          {editable ? (
            <>
              <div className="ins-fila-titulo">
                <Campo etiqueta="Título">
                  <Entrada value={ed.titulo} maxLength={300} onChange={(e) => cambiar('titulo', e.target.value)} />
                </Campo>
                <Campo etiqueta="Código">
                  <Entrada value={ed.codigo} maxLength={30} onChange={(e) => cambiar('codigo', e.target.value)} placeholder="IT-000" />
                </Campo>
              </div>
              <Campo etiqueta="Resumen" ayuda="Para qué sirve la tarea, cuándo se hace y qué resultado se busca.">
                <Area value={ed.resumen} rows={3} onChange={(e) => cambiar('resumen', e.target.value)} />
              </Campo>
            </>
          ) : ed.resumen ? <p className="ins-resumen">{ed.resumen}</p> : <p className="apagado">Sin resumen.</p>}
          <div className="ins-bloques">
            <BloqueLista icono={<AlertTriangle />} titulo="Riesgos" tono="alerta" valor={ed.riesgos} editable={editable}
              onCambio={(v) => cambiar('riesgos', v)} ejemplo="Atrapamiento de manos" />
            <BloqueLista icono={<HardHat />} titulo="EPIs" tono="aviso" valor={ed.epis} editable={editable}
              onCambio={(v) => cambiar('epis', v)} ejemplo="Guantes anticorte" />
            <BloqueLista icono={<Wrench />} titulo="Herramientas" tono="info" valor={ed.herramientas} editable={editable}
              onCambio={(v) => cambiar('herramientas', v)} ejemplo="Llave dinamométrica" />
          </div>
        </Tarjeta>

        {ins.video_url && (
          <div ref={tarjetaVideo}>
            <Tarjeta titulo="Vídeo original" icono={<Video size={18} />}>
              <video ref={video} src={urlServidor(ins.video_url)} controls preload="metadata" playsInline className="ins-video"
                poster={ins.miniatura_url ? urlServidor(ins.miniatura_url) : undefined} />
              <div className="pequeno apagado mt-1 mb-1">Salta al momento de cada paso:</div>
              <div className="ins-saltos">
                {ed.pasos.map((p, i) => p.t_inicio === null ? null : (
                  <button key={p.clave} type="button" className={`ins-salto ${i === indice ? 'activo' : ''}`}
                    onClick={() => { setSel(i); verEnVideo(p.t_inicio!) }} title={p.titulo}>
                    <span className="negrita">{i + 1}</span>{mmss(p.t_inicio)}
                  </button>
                ))}
              </div>
            </Tarjeta>
          </div>
        )}
      </div>

      {editable && sucio && (
        <div className="ins-barra-cambios" role="status">
          <span>Tienes cambios sin guardar</span>
          <Boton tamano="pequeno" variante="primario" icono={<Save />} onClick={() => guardar()} cargando={ocupado === 'guardar'}>
            Guardar
          </Boton>
        </div>
      )}

      <Historial instruccionId={ins.id} abierto={historial} onCerrar={() => setHistorial(false)}
        onAbrir={(otra) => irA(`/instrucciones/${otra}`)} />
      {dialogo}
    </div>
  )
}

/** Lo que dijo el experto en el tramo del vídeo de un paso (segmentos que se solapan con él). */
function dichoEn(segmentos: Segmento[] | null | undefined, p: Paso): string {
  if (!segmentos?.length || p.t_inicio === null || p.t_fin === null) return ''
  const [a, b] = [p.t_inicio, p.t_fin]
  return segmentos.filter((s) => Math.min(s.fin, b) - Math.max(s.inicio, a) > 0.4).map((s) => s.texto).join(' ')
}

function PanelPaso({ paso, indice, total, editable, hayVideo, subiendoImagen, dicho, onCambio, onQuitar, onImagen, onVerVideo, onIr }: {
  paso: PasoEdicion
  indice: number
  total: number
  editable: boolean
  hayVideo: boolean
  subiendoImagen: boolean
  dicho: string
  onCambio: (c: Partial<PasoEdicion>) => void
  onQuitar: () => void
  onImagen: (f: File) => void
  onVerVideo: (t: number) => void
  onIr: (i: number) => void
}) {
  return (
    <Tarjeta relleno={false} className="ins-panel">
      <div className="ins-panel-cabecera">
        <span className={`ins-numero grande ${paso.es_critico ? 'critico' : ''}`}>{indice + 1}</span>
        <div className="crece">
          <div className="diminuto apagado">Paso {indice + 1} de {total}</div>
          {editable ? (
            <input className="ins-titulo-paso" value={paso.titulo} maxLength={300} placeholder="Título del paso: qué se hace"
              onChange={(e) => onCambio({ titulo: e.target.value })} aria-label="Título del paso" />
          ) : <h2 className="ins-titulo-lectura">{paso.titulo}</h2>}
        </div>
        {editable && <Boton variante="fantasma" icono={<Trash2 />} onClick={onQuitar} title="Quitar este paso" aria-label="Quitar este paso" />}
      </div>

      <div className="ins-medios">
        <div>
          <div className="ins-medio-etiqueta"><ImageIcon />Imagen</div>
          <div className="ins-marco">
            {paso.imagen_url ? <img src={urlServidor(paso.imagen_url)} alt={`Imagen del paso ${indice + 1}`} />
              : <div className="ins-marco-vacio"><ImageIcon /><span>Sin imagen</span></div>}
            {editable && (
              <label className={`ins-marco-boton ${subiendoImagen ? 'ocupado' : ''}`}>
                {subiendoImagen ? <Loader2 className="girando" /> : <ImagePlus />}
                {paso.imagen_url ? 'Cambiar' : 'Añadir imagen'}
                <input type="file" hidden accept="image/jpeg,image/png,image/webp" disabled={subiendoImagen}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) onImagen(f); e.target.value = '' }} />
              </label>
            )}
          </div>
        </div>
        <div>
          <div className="ins-medio-etiqueta">
            <Film />Clip del experto
            {paso.t_inicio !== null && paso.t_fin !== null && <span className="apagado">· {mmss(paso.t_inicio)} a {mmss(paso.t_fin)}</span>}
          </div>
          <div className="ins-marco">
            {paso.clip_url ? <video key={paso.clip_url} src={urlServidor(paso.clip_url)} controls preload="metadata" playsInline
                poster={paso.imagen_url ? urlServidor(paso.imagen_url) : undefined} />
              : <div className="ins-marco-vacio"><Film /><span>Sin clip</span></div>}
          </div>
          {hayVideo && paso.t_inicio !== null && (
            <Boton variante="fantasma" tamano="pequeno" icono={<PlayCircle />} className="mt-1" onClick={() => onVerVideo(paso.t_inicio!)}>
              Ver en el vídeo original ({mmss(paso.t_inicio)})
            </Boton>
          )}
        </div>
      </div>

      <div className="tarjeta-cuerpo">
        {editable ? (
          <>
            <Campo etiqueta="Qué hay que hacer">
              <Area value={paso.texto} rows={4} placeholder="Explícalo en frases cortas y en imperativo: «Coloca…», «Aprieta…»."
                onChange={(e) => onCambio({ texto: e.target.value })} />
            </Campo>
            {dicho && (
              <details className="ins-dicho">
                <summary><Quote />Lo que se dice en el vídeo en este paso ({mmss(paso.t_inicio)} a {mmss(paso.t_fin)})</summary>
                <p>{dicho}</p>
              </details>
            )}
            <Campo etiqueta="Criterio de aceptación" ayuda="Cómo se comprueba que el paso está bien hecho.">
              <Area value={paso.criterio_aceptacion} rows={2} placeholder="Por ejemplo: par de 25 N·m comprobado con la llave dinamométrica."
                onChange={(e) => onCambio({ criterio_aceptacion: e.target.value })} />
            </Campo>
            <div className="ins-interruptores">
              <div className={`ins-interruptor ${paso.es_critico ? 'activo critico' : ''}`}>
                <Interruptor activo={paso.es_critico} onCambio={(v) => onCambio({ es_critico: v })}
                  etiqueta={<span className="negrita"><AlertTriangle size={15} /> Paso crítico</span>} />
                <div className="ayuda">Un fallo aquí estropea el resultado. En modo planta se pide confirmarlo expresamente.</div>
              </div>
              <div className={`ins-interruptor ${paso.es_seguridad ? 'activo seguridad' : ''}`}>
                <Interruptor activo={paso.es_seguridad} onCambio={(v) => onCambio({ es_seguridad: v })}
                  etiqueta={<span className="negrita"><ShieldAlert size={15} /> Seguridad</span>} />
                <div className="ayuda">Hay riesgo para las personas. Se destaca con un aviso de seguridad.</div>
              </div>
            </div>
          </>
        ) : (
          <>
            {(paso.es_critico || paso.es_seguridad) && (
              <div className="fila envolver mb-1">
                {paso.es_critico && <Etiqueta tono="roja" icono={<AlertTriangle />}>Paso crítico</Etiqueta>}
                {paso.es_seguridad && <Etiqueta tono="naranja" icono={<ShieldAlert />}>Seguridad</Etiqueta>}
              </div>
            )}
            {paso.texto ? <TextoFormato texto={paso.texto} /> : <p className="apagado">Sin texto.</p>}
            {paso.criterio_aceptacion && (
              <div className="ins-criterio">
                <CheckCircle2 />
                <div><div className="diminuto negrita">Criterio de aceptación</div>{paso.criterio_aceptacion}</div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="tarjeta-pie ins-panel-pie">
        <Boton tamano="pequeno" variante="fantasma" icono={<ChevronLeft />} disabled={indice === 0} onClick={() => onIr(indice - 1)}>Anterior</Boton>
        <Boton tamano="pequeno" variante="fantasma" disabled={indice >= total - 1} onClick={() => onIr(indice + 1)}>
          Siguiente<ChevronRight />
        </Boton>
      </div>
    </Tarjeta>
  )
}

function BloqueLista({ icono, titulo, tono, valor, editable, onCambio, ejemplo }: {
  icono: ReactNode; titulo: string; tono: 'alerta' | 'aviso' | 'info'; valor: string; editable: boolean
  onCambio: (v: string) => void; ejemplo: string
}) {
  const lineas = valor.split('\n').map((l) => l.replace(/^[-·•*]\s*/, '').trim()).filter(Boolean)
  return (
    <div className={`ins-bloque tono-${tono}`}>
      <div className="ins-bloque-titulo">{icono}{titulo}</div>
      {editable ? (
        <Area value={valor} rows={4} placeholder={`Uno por línea. Por ejemplo: ${ejemplo}`} onChange={(e) => onCambio(e.target.value)} />
      ) : lineas.length ? (
        <ul>{lineas.map((l, i) => <li key={i}>{l}</li>)}</ul>
      ) : <div className="pequeno apagado">No se indican.</div>}
    </div>
  )
}

function EsqueletoEditor() {
  return (
    <div className="columna">
      <Esqueleto alto={20} ancho={260} />
      <Esqueleto alto={34} ancho="60%" />
      <div className="ins-editor mt-2">
        <Esqueleto alto={420} />
        <Esqueleto alto={420} />
      </div>
    </div>
  )
}
