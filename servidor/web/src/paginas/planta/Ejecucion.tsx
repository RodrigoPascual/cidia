// Modo planta a pantalla completa (fuera del Marco): un paso por pantalla con letra grande,
// imagen o clip del experto, confirmación obligatoria de los pasos críticos, copiloto por voz o
// texto en el contexto del paso, foto del resultado comparada con la referencia y cierre con resumen.
// Quien supervisa (jefes, administración) la recorre en solo lectura, foto del resultado incluida, y
// el jefe del departamento de la tarea da la foto por buena o la rechaza con un comentario
// (con ?revisar=1 se abre directamente en la foto).
// Atajos: → o espacio = Hecho / Siguiente, ← = Anterior.

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BadgeCheck, Camera, Check, CheckCircle2, ClipboardCheck, Clock, Eye, Film, Flag,
  HardHat, ListChecks, Loader2, Maximize2, RefreshCw, ShieldAlert, ThumbsDown, ThumbsUp, TrendingUp, UserRound, Wrench,
  X, XCircle,
} from 'lucide-react'
import { EMBEBIDA, enviarFormulario, fecha, get, post, urlServidor } from '../../api'
import {
  Area, Aviso, Boton, Campo, ErrorCarga, Esqueleto, Etiqueta, Iluo, LogoCidia, Modal, NOMBRE_ILUO, TextoFormato, Vacio,
  useAvisarError, useAvisos, useDatos,
} from '../../ui'
import { consumirRespuesta, duracion, idLocal, reloj, RESPUESTA_VACIA } from './copiloto'
import { PanelCopiloto, type Mensaje } from './PanelCopiloto'
import type { EjecucionDatos, PasoEjecucion, ResumenFin, RevisionFoto, Veredicto } from './tipos'
import './planta.css'

type Fase = 'pasos' | 'cierre' | 'fin'

/** Vuelve a la pantalla anterior o, si se entró directamente, a la lista de tareas. */
function useVolver() {
  const navegar = useNavigate()
  return (destino = '/planta') => (window.history.length > 1 ? navegar(-1) : navegar(destino))
}

export default function Ejecucion() {
  const { id } = useParams()
  const volver = useVolver()
  const { datos, error, recargar } = useDatos((s) => get<EjecucionDatos>(`/api/planta/ejecuciones/${id}`, s), [id])

  if (datos) return <Pantalla key={datos.id} inicial={datos} />
  return (
    <div className={`planta ej ${EMBEBIDA ? 'embebida' : ''}`}>
      <header className="planta-barra">
        <div className="ej-marca"><LogoCidia tamano={30} /><span>Modo planta</span></div>
        <div className="crece" />
        <Boton variante="fantasma" className="ej-salir" icono={<X />} onClick={() => volver()}>Salir</Boton>
      </header>
      {error ? (
        <div className="ej-cierre-cuerpo"><ErrorCarga error={error} reintentar={recargar} /></div>
      ) : (
        <main className="planta-cuerpo" aria-busy="true">
          <div className="ej-paso">
            <Esqueleto alto={14} ancho={120} />
            <Esqueleto alto={34} ancho="70%" />
            <Esqueleto alto={260} />
            <Esqueleto alto={18} />
            <Esqueleto alto={18} ancho="80%" />
          </div>
          <div className="ej-copiloto" style={{ padding: 18, gap: 12 }}>
            <Esqueleto alto={34} ancho="50%" />
            <div className="crece" />
            <Esqueleto alto={84} ancho={84} />
          </div>
        </main>
      )}
    </div>
  )
}

/**
 * Reduce la foto del móvil (12 MP, varios MB) a 1600 px de lado en JPEG antes de subirla: se sube
 * antes con la wifi de la planta y el modelo de visión la compara mucho más rápido. Si el
 * navegador no puede (formato raro, poca memoria), se sube la original.
 */
async function reducirFoto(f: File, lado = 1600): Promise<Blob> {
  try {
    const mapa = await createImageBitmap(f)
    const escala = Math.min(1, lado / Math.max(mapa.width, mapa.height))
    if (escala >= 1 && f.size < 2_500_000) { mapa.close(); return f }
    const lienzo = document.createElement('canvas')
    lienzo.width = Math.round(mapa.width * escala)
    lienzo.height = Math.round(mapa.height * escala)
    lienzo.getContext('2d')?.drawImage(mapa, 0, 0, lienzo.width, lienzo.height)
    mapa.close()
    const reducida = await new Promise<Blob | null>((res) => lienzo.toBlob(res, 'image/jpeg', 0.85))
    return reducida && reducida.size > 0 && reducida.size < f.size ? reducida : f
  } catch {
    return f
  }
}

/** Segundos transcurridos, contados en el navegador desde la carga (sin depender de su reloj). */
function useSegundos(base: number, activo: boolean) {
  const cargado = useRef(Date.now())
  const [ahora, setAhora] = useState(Date.now())
  useEffect(() => {
    if (!activo) return
    const t = setInterval(() => setAhora(Date.now()), 1000)
    return () => clearInterval(t)
  }, [activo])
  return activo ? base + (ahora - cargado.current) / 1000 : base
}

/** «Pedro Ruiz» → «Pedro R.» (en la barra del modo planta, como en la maqueta del plan). */
function nombreCorto(nombre: string): string {
  const [nombrePila, ...resto] = nombre.trim().split(/ +/)
  return resto.length ? `${nombrePila} ${resto[0][0]}.` : nombrePila
}

/** Texto de riesgos sin repetir: la instrucción y la tarea a menudo traen el mismo. */
function unirRiesgos(...textos: (string | null | undefined)[]): string {
  const vistos = new Set<string>()
  return textos.filter((t): t is string => !!t?.trim()).filter((t) => {
    const clave = t.trim().toLowerCase()
    if (vistos.has(clave)) return false
    vistos.add(clave)
    return true
  }).join('\n')
}

function Pantalla({ inicial }: { inicial: EjecucionDatos }) {
  const navegar = useNavigate()
  const volver = useVolver()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const [params] = useSearchParams()
  const aRevisar = params.get('revisar') === '1'

  const [ej, setEj] = useState(inicial)
  const total = ej.pasos.length
  const soloLectura = !ej.es_mia || ej.estado !== 'en_curso'
  const [indice, setIndice] = useState(Math.max(0, Math.min(inicial.paso_actual, total - 1)))
  const [atras, setAtras] = useState(false)
  const [fase, setFase] = useState<Fase>(() => {
    if (!inicial.es_mia) return aRevisar && inicial.foto && inicial.pasos.every((p) => p.confirmado) ? 'cierre' : 'pasos'
    if (inicial.estado === 'completada') return 'fin'
    return inicial.estado === 'en_curso' && inicial.pasos.every((p) => p.confirmado) ? 'cierre' : 'pasos'
  })
  const [marcados, setMarcados] = useState<Record<number, boolean>>({})
  const [enviando, setEnviando] = useState(false)
  const [sacudir, setSacudir] = useState(false)
  const [faltaMarcar, setFaltaMarcar] = useState<number | null>(null) // paso crítico sin marcar al pulsar «Hecho»
  const [resumen, setResumen] = useState<ResumenFin | null>(null)
  const [salir, setSalir] = useState(false)
  const [ampliada, setAmpliada] = useState<string | null>(null)
  const restringido = !!inicial.contenido_restringido
  const [mensajes, setMensajes] = useState<Mensaje[]>(() => inicial.historial.map((h) => ({
    id: `h${h.id}`, pasoId: h.paso_id, pregunta: h.pregunta,
    respuesta: {
      texto: h.respuesta ?? '', fuentes: h.fuentes ?? [], terminado: true, conRespaldo: h.con_respaldo, oculta: restringido,
    },
  })))
  const segundos = useSegundos(inicial.duracion_s, ej.estado === 'en_curso')

  const paso: PasoEjecucion | undefined = ej.pasos[indice]
  const confirmados = ej.pasos.filter((p) => p.confirmado).length
  const todosHechos = confirmados === total
  const primerPendiente = ej.pasos.findIndex((p) => !p.confirmado)
  const delPaso = useMemo(() => mensajes.filter((m) => m.pasoId === paso?.id), [mensajes, paso?.id])
  const progreso = fase === 'pasos' ? (confirmados / Math.max(1, total)) * 100 : 100

  useEffect(() => {
    if (inicial.es_mia && inicial.estado === 'en_curso' && inicial.pasos_confirmados > 0 && fase === 'pasos') {
      avisar(`Continúas donde lo dejaste: paso ${indice + 1} de ${total}.`, 'info')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ------------------------------------------------------------------ navegación entre pasos

  function irA(i: number) {
    setAtras(i < indice)
    setIndice(i)
  }

  function anterior() {
    if (fase === 'cierre') { setAtras(true); setFase('pasos'); return }
    if (fase === 'pasos' && indice > 0) irA(indice - 1)
  }

  function siguiente(pasos: PasoEjecucion[]) {
    if (indice < total - 1) irA(indice + 1)
    else if (pasos.every((p) => p.confirmado)) setFase('cierre') // en solo lectura, para ver la foto del resultado
  }

  async function hecho() {
    if (fase !== 'pasos' || enviando || !paso) return
    if (soloLectura || paso.confirmado) { siguiente(ej.pasos); return }
    if (paso.es_critico && !marcados[paso.id]) {
      // Aviso dentro del recuadro rojo (un aviso flotante taparía el botón «Hecho»).
      setSacudir(true)
      setFaltaMarcar(paso.id)
      setTimeout(() => setSacudir(false), 420)
      return
    }
    setEnviando(true)
    try {
      await post(`/api/planta/ejecuciones/${ej.id}/pasos/${paso.id}/confirmar`, { critico_confirmado: !!marcados[paso.id] })
      const momento = new Date().toISOString()
      const marcar = (lista: PasoEjecucion[]) => lista.map((p) => p.id === paso.id
        ? { ...p, confirmado: true, critico_confirmado: p.es_critico, confirmado_en: momento } : p)
      setEj((e) => {
        const pasos = marcar(e.pasos)
        return { ...e, pasos, pasos_confirmados: pasos.filter((p) => p.confirmado).length }
      })
      siguiente(marcar(ej.pasos))
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
    }
  }

  // Atajos de teclado: se enlazan una vez y leen siempre las funciones actuales.
  const teclas = useRef({ hecho, anterior, bloqueado: false })
  teclas.current = { hecho, anterior, bloqueado: salir || !!ampliada || fase === 'fin' }
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      const t = teclas.current
      // e.repeat: dejar pulsada la flecha no puede confirmar varios pasos seguidos sin mirarlos.
      if (t.bloqueado || e.defaultPrevented || e.repeat || e.altKey || e.ctrlKey || e.metaKey) return
      // Con un diálogo abierto (una cita del copiloto, la imagen ampliada...) las flechas no
      // pueden confirmar el paso que queda detrás.
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
      const el = e.target as HTMLElement
      // Ni al escribir ni con el foco en el clip (sus controles usan las flechas para avanzar el vídeo).
      if (el.closest('textarea, select, video, audio, [contenteditable="true"], input:not([type="checkbox"])')) return
      if (e.key === 'ArrowRight') { e.preventDefault(); t.hecho() }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); t.anterior() }
      else if (e.key === ' ' && !el.closest('button, a, input')) { e.preventDefault(); t.hecho() }
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [])

  // ------------------------------------------------------------------ copiloto

  function preguntar(texto: string) {
    if (soloLectura || !paso) return
    const idm = idLocal()
    const pasoId = paso.id
    const critico = paso.es_critico
    // El servidor cuenta la consulta al recibirla: se refleja ya en los contadores de la pantalla
    // y se deshace si la rechaza (sin conexión, ejecución cerrada, sin acceso...).
    const contar = (n: number) => setEj((e) => ({
      ...e,
      consultas: e.consultas + n,
      consultas_criticos: e.consultas_criticos + (critico ? n : 0),
      pasos: e.pasos.map((p) => (p.id === pasoId ? { ...p, consultas: p.consultas + n } : p)),
    }))
    setMensajes((ms) => [...ms, { id: idm, pasoId, pregunta: texto, respuesta: { ...RESPUESTA_VACIA } }])
    contar(1)
    consumirRespuesta(`/api/planta/ejecuciones/${ej.id}/preguntar`, { pregunta: texto, paso_id: pasoId },
      (r) => setMensajes((ms) => ms.map((m) => (m.id === idm ? { ...m, respuesta: r } : m))))
      .then((r) => { if (r.rechazada) contar(-1) })
  }

  // ------------------------------------------------------------------ foto, final y salida

  const entradaFoto = useRef<HTMLInputElement>(null)
  const [subiendo, setSubiendo] = useState(false)
  const [previa, setPrevia] = useState<string | null>(null)
  useEffect(() => () => { if (previa) URL.revokeObjectURL(previa) }, [previa])
  const referencia = useMemo(() => {
    for (let i = ej.pasos.length - 1; i >= 0; i--) if (ej.pasos[i].imagen_url) return ej.pasos[i].imagen_url
    return null
  }, [ej.pasos])

  async function subirFoto(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setPrevia(URL.createObjectURL(f))
    setSubiendo(true)
    try {
      const fd = new FormData()
      const foto = await reducirFoto(f)
      fd.append('imagen', foto, foto === f ? f.name || 'resultado.jpg' : 'resultado.jpg')
      const v = await enviarFormulario<Veredicto>(`/api/planta/ejecuciones/${ej.id}/foto`, fd)
      setEj((x) => ({ ...x, foto: v }))
    } catch (err) {
      avisarError(err)
      setPrevia(null)
    } finally {
      setSubiendo(false)
    }
  }

  async function finalizar() {
    setEnviando(true)
    try {
      const r = await post<{ resumen: ResumenFin }>(`/api/planta/ejecuciones/${ej.id}/finalizar`)
      setResumen(r.resumen)
      setEj((x) => ({ ...x, estado: 'completada' }))
      setFase('fin')
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
    }
  }

  async function abandonar() {
    setEnviando(true)
    try {
      await post(`/api/planta/ejecuciones/${ej.id}/abandonar`)
      avisar('Ejecución abandonada. Puedes empezarla de nuevo cuando quieras.', 'info')
      navegar('/planta')
    } catch (e) {
      avisarError(e)
      setEnviando(false)
    }
  }

  function pedirSalida() {
    if (ej.es_mia && ej.estado === 'en_curso') setSalir(true)
    else if (ej.es_mia) navegar('/planta')
    else volver(aRevisar ? '/planta?vista=fotos' : '/equipo')
  }

  // ------------------------------------------------------------------ pantalla

  const ins = ej.instruccion
  const chip = fase === 'pasos' ? `Paso ${indice + 1} de ${total}` : fase === 'cierre' ? 'Resultado' : 'Completada'

  let cuerpo
  if (ej.es_mia && ej.estado === 'abandonada') {
    cuerpo = (
      <div className="ej-cierre-cuerpo">
        <div className="ej-exito">
          <Vacio icono={<XCircle />} titulo="Esta ejecución se abandonó"
            accion={<Boton variante="primario" tamano="grande" icono={<ListChecks />} onClick={() => navegar('/planta')}>Volver a mis tareas</Boton>}>
            Puedes empezar la tarea de nuevo desde la lista de tareas.
          </Vacio>
        </div>
      </div>
    )
  } else if (fase === 'fin') {
    cuerpo = <Exito ej={ej} resumen={resumen} onVolver={() => navegar('/planta')} onProgreso={() => navegar('/progreso')} />
  } else if (fase === 'cierre') {
    const foto = urlServidor(previa ?? ej.foto?.foto_url)
    const ref = urlServidor(ej.foto?.referencia_url ?? referencia)
    const quien = ej.persona?.nombre ?? 'La persona'
    cuerpo = (
      <div className="ej-cierre-cuerpo">
        <div className="ej-cierre">
          <section className="ej-tarjeta">
            <h2><Camera /> Foto del resultado</h2>
            <div className="apagado">
              {soloLectura
                ? `Foto que hizo ${quien} al terminar, junto a la imagen del experto. El veredicto del modelo es orientativo: decide una persona.`
                : 'Haz una foto de la pieza terminada. CidIA la compara con la imagen del experto y te avisa si ve algo distinto. Es orientativo: decide siempre una persona.'}
            </div>
            <div className="ej-comparar">
              <figure>
                {ref ? <img src={ref} alt="Referencia del experto" /> : (
                  <div className="sin-ref">
                    {restringido ? 'La imagen del experto es de otro departamento' : 'La instrucción no tiene imagen de referencia'}
                  </div>
                )}
                <figcaption>Así debe quedar</figcaption>
              </figure>
              <figure>
                {foto ? (
                  <img src={foto} alt="Foto del resultado" />
                ) : soloLectura ? (
                  <div className="sin-ref">Sin foto del resultado</div>
                ) : (
                  <div className="sin-ref">
                    <Boton variante="primario" tamano="grande" icono={<Camera />} onClick={() => entradaFoto.current?.click()}>
                      Hacer foto
                    </Boton>
                  </div>
                )}
                <figcaption>{soloLectura ? 'Su resultado' : 'Tu resultado'}</figcaption>
              </figure>
            </div>
            <div className="mt-2">
              {subiendo ? (
                <div className="fila apagado"><Loader2 className="girando" size={18} /> Comparando con la referencia…</div>
              ) : ej.foto ? (
                <VeredictoAviso v={ej.foto} propia={ej.es_mia} />
              ) : !soloLectura ? (
                <div className="pequeno apagado">La foto es opcional: puedes finalizar sin ella. Vale JPG, PNG o WEBP.</div>
              ) : null}
            </div>
            {!soloLectura && (ej.foto || previa) && !subiendo && (
              <div className="mt-1">
                <Boton variante="fantasma" icono={<RefreshCw />} onClick={() => entradaFoto.current?.click()}>Repetir la foto</Boton>
              </div>
            )}
            {ej.foto?.revision && !ej.puede_revisar && (
              <div className="mt-2"><EstadoRevision r={ej.foto.revision} propia={ej.es_mia} /></div>
            )}
            {!soloLectura && (
              <input ref={entradaFoto} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden
                onChange={subirFoto} />
            )}
          </section>
          <div className="ej-cierre-lateral">
          {ej.puede_revisar && ej.foto && (
            <PanelRevision ej={ej} onRevisada={(v) => setEj((x) => ({ ...x, foto: v }))} />
          )}
          <section className="ej-tarjeta">
            <h2><ClipboardCheck /> {soloLectura ? 'Resumen de la ejecución' : 'Has terminado los pasos'}</h2>
            <div className="apagado">
              {!soloLectura
                ? 'Revisa el resumen y pulsa «Finalizar» para registrar la ejecución en tu progreso.'
                : ej.estado === 'completada'
                  ? `Completada el ${fecha(ej.fin, true)}.`
                  : 'Ha confirmado todos los pasos, pero todavía no la ha finalizado.'}
            </div>
            <div className="ej-cifras">
              <Cifra valor={`${confirmados}/${total}`} etiqueta="Pasos confirmados" />
              <Cifra valor={ej.pasos.filter((p) => p.es_critico).length} etiqueta="Críticos comprobados" />
              <Cifra valor={reloj(segundos)} etiqueta="Tiempo" />
              <Cifra valor={ej.consultas} etiqueta="Consultas al copiloto" />
            </div>
            {ej.consultas_criticos > 0 && (
              <div className="pequeno apagado">
                {ej.consultas_criticos} {ej.consultas_criticos === 1 ? 'consulta' : 'consultas'} en pasos críticos.
                {' '}Para el nivel «Autónomo» hace falta una ejecución sin consultas en los críticos.
              </div>
            )}
          </section>
          </div>
        </div>
      </div>
    )
  } else if (paso) {
    const marcado = paso.confirmado ? paso.critico_confirmado || paso.es_critico : !!marcados[paso.id]
    const riesgos = unirRiesgos(ins.riesgos, ej.tarea.riesgos_prl)
    const antes = indice === 0 && (ins.epis || ins.herramientas || riesgos)
    cuerpo = (
      <main className="planta-cuerpo">
        <section className="ej-columna">
          <article key={paso.id} className={`ej-paso ${atras ? 'atras' : ''}`}>
            <div className="ej-paso-cabecera">
              <span className="ej-paso-numero">Paso {indice + 1} de {total}</span>
              {paso.es_seguridad && <Etiqueta tono="naranja" icono={<ShieldAlert />}>Seguridad</Etiqueta>}
              {paso.confirmado && <Etiqueta tono="verde" icono={<CheckCircle2 />}>Hecho</Etiqueta>}
              {!ej.es_mia && paso.consultas > 0 && <Etiqueta tono="azul">{paso.consultas} {paso.consultas === 1 ? 'consulta' : 'consultas'}</Etiqueta>}
            </div>
            <h1 className="planta-paso-titulo">{paso.titulo}</h1>
            {paso.es_critico && (
              <div className="ej-critico" role="alert">
                <div className="ej-critico-titulo"><AlertTriangle /> PASO CRÍTICO</div>
                <div className="ej-critico-texto">
                  {paso.criterio_aceptacion || 'Comprueba este punto con atención antes de seguir.'}
                </div>
                <label className={`ej-casilla ${marcado ? 'marcada' : ''} ${sacudir ? 'aviso' : ''}`}>
                  <input type="checkbox" checked={marcado} disabled={soloLectura || paso.confirmado}
                    onChange={(e) => {
                      const v = e.target.checked
                      setMarcados((m) => ({ ...m, [paso.id]: v }))
                      if (v) setFaltaMarcar(null)
                    }} />
                  {paso.confirmado ? 'Confirmado: este punto se comprobó' : 'He comprobado este punto crítico'}
                </label>
                {faltaMarcar === paso.id && !marcado && (
                  <div className="ej-critico-falta" role="alert">
                    Marca la casilla para confirmar que lo has comprobado. Sin ella no se puede seguir.
                  </div>
                )}
              </div>
            )}
            {antes && (
              <div className="ej-antes">
                <div className="ej-antes-titulo"><ListChecks /> Antes de empezar</div>
                {ins.epis && <div className="ej-antes-fila"><HardHat /><div><strong>EPI</strong>{ins.epis}</div></div>}
                {ins.herramientas && <div className="ej-antes-fila"><Wrench /><div><strong>Herramientas</strong>{ins.herramientas}</div></div>}
                {riesgos && <div className="ej-antes-fila riesgo"><ShieldAlert /><div><strong>Riesgos</strong>{riesgos}</div></div>}
              </div>
            )}
            {paso.texto && <div className="planta-texto"><TextoFormato texto={paso.texto} /></div>}
            <Media paso={paso} onAmpliar={setAmpliada} />
            {!paso.es_critico && paso.criterio_aceptacion && (
              <div className="ej-criterio"><strong>Cómo saber que está bien</strong>{paso.criterio_aceptacion}</div>
            )}
          </article>
        </section>
        <aside className="ej-columna">
          <PanelCopiloto numero={indice + 1} mensajes={delPaso} soloLectura={soloLectura} onPreguntar={preguntar} />
        </aside>
      </main>
    )
  } else {
    cuerpo = <div className="ej-cierre-cuerpo"><Vacio icono={<ListChecks />} titulo="La instrucción no tiene pasos" /></div>
  }

  const mostrarPie = fase !== 'fin' && !(ej.es_mia && ej.estado === 'abandonada') && !!paso
  return (
    <div className={`planta ej ${EMBEBIDA ? 'embebida' : ''}`}>
      <header className="planta-barra">
        <div className="ej-marca"><LogoCidia tamano={30} /><span>Modo planta</span></div>
        <div className="ej-tarea">
          <div className="nombre recortar">
            {ej.tarea.codigo && <span className="codigo">{ej.tarea.codigo}</span>}{ej.tarea.nombre}
          </div>
          <div className="detalle">{ins.codigo ?? 'Instrucción'} · versión {ins.version}</div>
        </div>
        {ej.es_mia && ej.persona && (
          <div className="ej-persona" title={ej.persona.nombre}><UserRound /> {nombreCorto(ej.persona.nombre)}</div>
        )}
        {ej.estado === 'en_curso' && <div className="ej-reloj" title="Tiempo de la ejecución"><Clock /> {reloj(segundos)}</div>}
        <div className="ej-chip-paso">{chip}</div>
        <Boton variante="fantasma" className="ej-salir" icono={<X />} onClick={pedirSalida}>Salir</Boton>
      </header>
      <div className="ej-progreso" role="progressbar" aria-valuenow={Math.round(progreso)} aria-valuemin={0} aria-valuemax={100}>
        <div style={{ width: `${progreso}%` }} />
      </div>
      {!ej.es_mia && (
        <div className="ej-lectura">
          <Eye /> Estás viendo la ejecución de {ej.persona?.nombre ?? 'otra persona'}
          {ej.estado === 'completada' ? ' (completada)' : ej.estado === 'abandonada' ? ' (abandonada)' : ' (en curso)'}.
          Solo lectura.
          {restringido && ' La tarea es de otro departamento: ves el avance y las consultas, no el contenido de la instrucción.'}
        </div>
      )}

      {cuerpo}

      {mostrarPie && (
        <footer className="planta-pie">
          <Boton variante="secundario" tamano="enorme" icono={<ArrowLeft />} onClick={anterior}
            disabled={fase === 'pasos' && indice === 0}>
            Anterior
          </Boton>
          <div className="ej-pie-centro">
            {fase === 'pasos' ? (
              <div className="ej-puntos" aria-label="Pasos">
                {ej.pasos.map((p, i) => (
                  <button key={p.id} type="button" title={`${i + 1}. ${p.titulo}`}
                    className={`ej-punto ${p.confirmado ? 'hecho' : ''} ${p.es_critico ? 'critico' : ''} ${i === indice ? 'actual' : ''}`}
                    disabled={!soloLectura && primerPendiente >= 0 && i > primerPendiente}
                    aria-label={`Paso ${i + 1}${p.confirmado ? ', hecho' : ''}${p.es_critico ? ', crítico' : ''}`}
                    onClick={() => irA(i)} />
                ))}
              </div>
            ) : (
              <div className="negrita">{confirmados} de {total} pasos confirmados</div>
            )}
            <div className="ej-atajos">
              {fase === 'pasos' ? <><kbd>←</kbd> <kbd>→</kbd> o <kbd>espacio</kbd> para moverte</> : <><kbd>←</kbd> para volver a los pasos</>}
            </div>
          </div>
          {fase === 'pasos' ? (
            <Boton variante="verde" tamano="enorme" cargando={enviando}
              icono={paso!.confirmado || soloLectura ? <ArrowRight /> : <Check />}
              disabled={soloLectura && indice === total - 1 && !todosHechos} onClick={hecho}>
              {paso!.confirmado || soloLectura ? (indice === total - 1 && todosHechos ? 'Resultado' : 'Siguiente') : 'Hecho'}
            </Boton>
          ) : soloLectura ? (
            <Boton variante="secundario" tamano="enorme" icono={<X />} onClick={pedirSalida}>Salir</Boton>
          ) : (
            <Boton variante="verde" tamano="enorme" icono={<Flag />} cargando={enviando} disabled={subiendo} onClick={finalizar}>
              Finalizar
            </Boton>
          )}
        </footer>
      )}

      <Modal abierto={salir} titulo="¿Salir del modo planta?" onCerrar={() => setSalir(false)}
        pie={<>
          <Boton variante="peligro" cargando={enviando} onClick={abandonar}>Abandonar</Boton>
          <Boton onClick={() => setSalir(false)}>Seguir aquí</Boton>
          <Boton variante="primario" onClick={() => navegar('/planta')}>Salir y continuar luego</Boton>
        </>}>
        <div className="apagado">
          Llevas {confirmados} de {total} pasos. Si sales, podrás continuar desde la lista de tareas en el mismo paso.
          Si la abandonas, la ejecución se cierra sin completarse.
        </div>
      </Modal>

      <Modal abierto={!!ampliada} titulo={paso ? `Paso ${indice + 1}: ${paso.titulo}` : 'Imagen'} onCerrar={() => setAmpliada(null)} ancho>
        {ampliada && <img src={ampliada} alt="" style={{ width: '100%', borderRadius: 12, display: 'block' }} />}
      </Modal>
    </div>
  )
}

function Media({ paso, onAmpliar }: { paso: PasoEjecucion; onAmpliar: (url: string) => void }) {
  const clip = urlServidor(paso.clip_url)
  const imagen = urlServidor(paso.imagen_url)
  if (clip) {
    return (
      <div className="ej-media">
        <video key={clip} src={clip} poster={imagen} autoPlay loop muted controls playsInline preload="auto" />
        <span className="ej-media-etiqueta"><Film /> Clip del experto</span>
      </div>
    )
  }
  if (imagen) {
    return (
      <div className="ej-media">
        <img src={imagen} alt={`Paso ${paso.numero}: ${paso.titulo}`} />
        <Boton variante="fantasma" className="ej-ampliar" icono={<Maximize2 />} onClick={() => onAmpliar(imagen)} aria-label="Ampliar imagen" />
      </div>
    )
  }
  return null
}

function Cifra({ valor, etiqueta, tono }: { valor: ReactNode; etiqueta: string; tono?: 'alerta' }) {
  return (
    <div className={`ej-cifra ${tono ?? ''}`}>
      <div className="valor">{valor}</div>
      <div className="etiqueta">{etiqueta}</div>
    </div>
  )
}

function VeredictoAviso({ v, propia }: { v: Veredicto; propia: boolean }) {
  const confianza = v.confianza != null ? ` Confianza del modelo: ${Math.round(v.confianza * 100)} %.` : ''
  const quien = propia ? 'tu responsable' : 'el responsable'
  if (v.estado === 'comparada' && v.coincide && !v.revision_humana) {
    return <Aviso tono="exito" titulo="Se parece a la referencia">{v.observaciones || v.mensaje}{confianza} Decide siempre una persona.</Aviso>
  }
  if (v.estado === 'comparada' && v.coincide) {
    return <Aviso tono="amarillo" titulo="El modelo tiene dudas">{v.observaciones || v.mensaje}{confianza} La revisará {quien}.</Aviso>
  }
  if (v.estado === 'comparada') {
    return <Aviso tono="amarillo" titulo="Revisa el resultado">{v.observaciones || v.mensaje}{confianza} Si tienes dudas, avisa a {quien}.</Aviso>
  }
  return <Aviso titulo={`La revisará ${quien}`}>{v.mensaje}</Aviso>
}

/** Decisión del jefe sobre la foto, tal y como la ve quien hizo la tarea (o quien supervisa). */
function EstadoRevision({ r, propia }: { r: RevisionFoto; propia: boolean }) {
  const cuando = fecha(r.fecha, true)
  if (r.estado === 'aprobada') {
    return (
      <Aviso tono="exito" titulo={`${r.revisor} ha dado la foto por buena`}>
        {r.comentario ? `«${r.comentario}» · ` : ''}{cuando}
      </Aviso>
    )
  }
  return (
    <Aviso tono="alerta" titulo={`${r.revisor} ha rechazado la foto`}>
      {r.comentario ? `«${r.comentario}»` : 'Sin comentario.'} · {cuando}
      {propia && <div className="mt-1">Corrige lo que indica y, si lo necesitas, pregúntale cómo hacerlo.</div>}
    </Aviso>
  )
}

/** El jefe del departamento de la tarea da la foto por buena o la rechaza con un comentario. */
function PanelRevision({ ej, onRevisada }: { ej: EjecucionDatos; onRevisada: (v: Veredicto) => void }) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const r = ej.foto?.revision ?? null
  const [editando, setEditando] = useState(!r)
  const [comentario, setComentario] = useState(r?.comentario ?? '')
  const [enviando, setEnviando] = useState<'aprobada' | 'rechazada' | null>(null)
  const [falta, setFalta] = useState(false)
  const nombre = ej.persona?.nombre?.split(' ')[0] ?? 'la persona'

  async function decidir(decision: 'aprobada' | 'rechazada') {
    const texto = comentario.trim()
    if (decision === 'rechazada' && texto.length < 3) { setFalta(true); return }
    setEnviando(decision)
    try {
      const v = await post<Veredicto>(`/api/planta/ejecuciones/${ej.id}/revision`, { decision, comentario: texto || null })
      onRevisada(v)
      setEditando(false)
      setFalta(false)
      avisar(decision === 'aprobada' ? 'Foto dada por buena.' : `Foto rechazada. ${nombre} verá tu comentario.`)
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(null)
    }
  }

  return (
    <section className={`ej-tarjeta ej-revision ${ej.foto?.pendiente_revision ? 'pendiente' : ''}`}>
      <h2><BadgeCheck /> Revisión del responsable</h2>
      {r && !editando ? (
        <>
          <EstadoRevision r={r} propia={false} />
          <div className="mt-1">
            <Boton variante="fantasma" icono={<RefreshCw />} onClick={() => setEditando(true)}>Cambiar la decisión</Boton>
          </div>
        </>
      ) : (
        <>
          <div className="apagado">
            {ej.foto?.necesita_revision
              ? 'CidIA no ha podido confirmar que el resultado está bien. Compara la foto con la referencia y decide tú.'
              : 'El modelo cree que coincide con la referencia. Puedes confirmarlo o rechazarlo si ves algo mal.'}
          </div>
          <div className="mt-2">
            <Campo etiqueta={`Comentario para ${nombre}`} ayuda="Obligatorio si la rechazas: explica qué hay que corregir.">
              <Area rows={3} maxLength={1000} value={comentario} placeholder="Por ejemplo: falta la marca de testigo en el tornillo 3."
                onChange={(e) => { setComentario(e.target.value); if (falta) setFalta(false) }} />
            </Campo>
          </div>
          {falta && <div className="ej-revision-falta" role="alert">Escribe qué hay que corregir antes de rechazarla.</div>}
          <div className="ej-revision-botones">
            <Boton variante="verde" tamano="grande" icono={<ThumbsUp />} cargando={enviando === 'aprobada'} disabled={!!enviando}
              onClick={() => decidir('aprobada')}>
              Dar por buena
            </Boton>
            <Boton variante="peligro" tamano="grande" icono={<ThumbsDown />} cargando={enviando === 'rechazada'} disabled={!!enviando}
              onClick={() => decidir('rechazada')}>
              Rechazar
            </Boton>
            {r && <Boton variante="fantasma" disabled={!!enviando} onClick={() => setEditando(false)}>Cancelar</Boton>}
          </div>
        </>
      )}
    </section>
  )
}

function Exito({ ej, resumen, onVolver, onProgreso }: {
  ej: EjecucionDatos; resumen: ResumenFin | null; onVolver: () => void; onProgreso: () => void
}) {
  const r: ResumenFin = resumen ?? {
    duracion_s: ej.duracion_s, consultas: ej.consultas, consultas_criticos: ej.consultas_criticos,
    pasos: ej.pasos.length, pasos_criticos: ej.pasos.filter((p) => p.es_critico).length,
  }
  const nivel = r.nivel ?? 0
  const subio = r.nivel_anterior !== undefined && nivel > r.nivel_anterior
  const consejo = r.consultas === 0
    ? 'Sin consultas al copiloto: vas ganando autonomía.'
    : r.consultas_criticos === 0
      ? 'Ninguna consulta en los pasos críticos. Buen trabajo.'
      : 'La próxima vez intenta resolver los pasos críticos sin consultar: así se alcanza el nivel «Autónomo».'
  return (
    <div className="ej-cierre-cuerpo">
      <div className="ej-exito">
        <svg className="ej-exito-icono" viewBox="0 0 100 100" aria-hidden="true">
          <circle cx="50" cy="50" r="46" />
          <path d="M29 52 L44 66 L72 36" />
        </svg>
        <h1>Tarea completada</h1>
        <div className="apagado mt-1">
          {ej.tarea.nombre} · {ej.instruccion.codigo ?? 'instrucción'} versión {ej.instruccion.version}
        </div>
        <div className="ej-cifras">
          <Cifra valor={duracion(r.duracion_s)} etiqueta="Tiempo" />
          <Cifra valor={r.pasos} etiqueta={`Pasos (${r.pasos_criticos} críticos)`} />
          <Cifra valor={r.consultas} etiqueta="Consultas al copiloto" />
          <Cifra valor={r.consultas_criticos} etiqueta="En pasos críticos" tono={r.consultas_criticos ? 'alerta' : undefined} />
        </div>
        {nivel > 0 && (
          <div className="ej-nivel">
            <Iluo nivel={nivel} tamano={56} caducado={r.caducado} />
            <div className="crece">
              <div className="negrita">{subio ? `Has subido al nivel ${r.nivel_letra}` : `Nivel ${r.nivel_letra} · ${NOMBRE_ILUO[nivel]}`}</div>
              {r.ejecuciones_completadas !== undefined && (
                <div className="pequeno apagado">
                  {r.ejecuciones_completadas} {r.ejecuciones_completadas === 1 ? 'ejecución completada' : 'ejecuciones completadas'} de esta tarea
                </div>
              )}
            </div>
            {subio && <Etiqueta tono="verde">Nuevo nivel</Etiqueta>}
          </div>
        )}
        <p className="apagado mb-3">{consejo}</p>
        {ej.foto?.revision ? (
          <div className="ej-exito-revision"><EstadoRevision r={ej.foto.revision} propia={ej.es_mia} /></div>
        ) : ej.foto?.pendiente_revision ? (
          <p className="pequeno apagado mb-3">Tu responsable revisará la foto del resultado y verás aquí su decisión.</p>
        ) : null}
        <div className="fila envolver" style={{ justifyContent: 'center' }}>
          <Boton variante="primario" tamano="grande" icono={<ListChecks />} onClick={onVolver}>Volver a mis tareas</Boton>
          <Boton tamano="grande" icono={<TrendingUp />} onClick={onProgreso}>Ver mi progreso</Boton>
        </div>
      </div>
    </div>
  )
}
