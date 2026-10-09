// Copiloto: chat con la documentación de la empresa. Respuestas en streaming con citas [n]
// pulsables, fuentes bajo cada respuesta, voz («mantén pulsado para hablar»), modo socrático,
// valoración, historial y aviso amable cuando no hay respaldo (la pregunta queda como laguna).

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  BookOpen, CircleHelp, Clock, Copy, GraduationCap, HardHat, History, ListChecks, LogIn, MessageSquarePlus, Mic,
  RotateCcw, Send, ShieldCheck, Sparkles, Square, ThumbsDown, ThumbsUp, Wrench,
} from 'lucide-react'
import { flujo, get, post } from '../api'
import { useSesion } from '../sesion'
import { Aviso, Boton, Cabecera, Interruptor, LogoCidia, TextoFormato, useAvisarError, useAvisos } from '../ui'
import BotonVoz from './copiloto/BotonVoz'
import Historial from './copiloto/Historial'
import PanelFuente from './copiloto/PanelFuente'
import { ubicacion, type ConsultaGuardada, type Fuente, type Mensaje, type Modo, type PaginaHistorial } from './copiloto/tipos'
import './copiloto/copiloto.css'

const MAX_GUARDADOS = 40 // mensajes que se recuerdan al volver a la página (en esta pestaña)
const TURNOS_HISTORIAL = 6

const SUGERENCIAS_EMPLEADO: { icono: ReactNode; texto: string }[] = [
  { icono: <ShieldCheck />, texto: '¿Qué equipos de protección necesito en mi puesto?' },
  { icono: <ListChecks />, texto: '¿Cuáles son los pasos críticos de mi tarea?' },
  { icono: <Wrench />, texto: '¿Qué hago si una máquina se atasca?' },
  { icono: <BookOpen />, texto: 'Resúmeme la instrucción de trabajo de mi puesto' },
]

const SUGERENCIAS_INVITADO: { icono: ReactNode; texto: string }[] = [
  { icono: <HardHat />, texto: '¿Qué normas de seguridad hay que seguir en la planta?' },
  { icono: <BookOpen />, texto: '¿Qué tengo que saber en mi primer día?' },
  { icono: <ShieldCheck />, texto: '¿Qué hago en caso de emergencia?' },
  { icono: <Sparkles />, texto: '¿Qué es CidIA y cómo me puede ayudar?' },
]

let contadorIds = 0
const nuevoId = () => `m${Date.now().toString(36)}${(contadorIds++).toString(36)}`

/** «[1, 2]» → «[1][2]»: así cada número es una cita pulsable (TextoFormato solo reconoce [n]). */
function separarCitas(texto: string): string {
  return texto.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})+)\]/g, (_, grupo: string) =>
    grupo.split(',').map((n) => `[${n.trim()}]`).join(''))
}

function saludo(): string {
  const h = new Date().getHours()
  return h < 14 ? 'Buenos días' : h < 21 ? 'Buenas tardes' : 'Buenas noches'
}

/** Copia texto al portapapeles (también en http, donde navigator.clipboard no existe). */
async function copiarTexto(texto: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(texto)
      return true
    }
  } catch {
    /* se prueba el método clásico */
  }
  const area = document.createElement('textarea')
  area.value = texto
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  area.remove()
  return ok
}

/** En un puesto compartido, la conversación de quien usó antes la pestaña no se queda guardada. */
function olvidarOtras(clave: string) {
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const k = sessionStorage.key(i)
      if (k && k.startsWith('cidia.copiloto.') && k !== clave) sessionStorage.removeItem(k)
    }
  } catch {
    /* almacenamiento no disponible */
  }
}

function leerGuardados(clave: string): Mensaje[] {
  olvidarOtras(clave)
  try {
    const crudo = sessionStorage.getItem(clave)
    if (!crudo) return []
    const lista = JSON.parse(crudo) as Mensaje[]
    // Una respuesta que se quedó a medias al salir de la página ya no va a terminar.
    return lista.map((m) => (m.estado === 'buscando' || m.estado === 'escribiendo'
      ? { ...m, estado: 'error', error: 'La respuesta se interrumpió al salir de la página.' }
      : m))
  } catch {
    return []
  }
}

function guardar(clave: string, mensajes: Mensaje[]) {
  try {
    if (mensajes.length) sessionStorage.setItem(clave, JSON.stringify(mensajes.slice(-MAX_GUARDADOS)))
    else sessionStorage.removeItem(clave)
  } catch {
    /* almacenamiento no disponible */
  }
}

function leerSocratico(): boolean {
  try {
    return localStorage.getItem('cidia.copiloto.socratico') === '1'
  } catch {
    return false
  }
}

export default function Copiloto() {
  const { perfil, salir } = useSesion()
  const navegar = useNavigate()
  const [params, setParams] = useSearchParams()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const invitado = !!perfil?.invitado
  const clave = `cidia.copiloto.${perfil?.id ?? 'invitado'}`

  const [mensajes, setMensajes] = useState<Mensaje[]>(() => leerGuardados(clave))
  const [texto, setTexto] = useState('')
  const [socratico, setSocratico] = useState(leerSocratico)
  const [panel, setPanel] = useState<{ id: string; n: number } | null>(null)
  const [historialAbierto, setHistorialAbierto] = useState(false)
  const [recientes, setRecientes] = useState<string[]>([])

  const control = useRef<AbortController | null>(null)
  const area = useRef<HTMLTextAreaElement>(null)
  const seguir = useRef(true) // seguir el final de la conversación mientras llega la respuesta

  const enCurso = mensajes.some((m) => m.estado === 'buscando' || m.estado === 'escribiendo')

  useEffect(() => { if (!enCurso) guardar(clave, mensajes) }, [clave, mensajes, enCurso])
  useEffect(() => () => control.current?.abort(), [])
  useEffect(() => {
    try { localStorage.setItem('cidia.copiloto.socratico', socratico ? '1' : '0') } catch { /* sin almacenamiento */ }
  }, [socratico])

  // Seguir el final solo si la persona no ha subido a leer algo anterior.
  useEffect(() => {
    const alDesplazar = () => {
      seguir.current = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 220
    }
    window.addEventListener('scroll', alDesplazar, { passive: true })
    return () => window.removeEventListener('scroll', alDesplazar)
  }, [])
  useEffect(() => {
    // Hasta el final del documento: así el compositor fijo no tapa las últimas líneas.
    if (seguir.current && mensajes.length) window.scrollTo({ top: document.documentElement.scrollHeight })
  }, [mensajes])

  // Últimas preguntas, para retomarlas desde la bienvenida.
  useEffect(() => {
    if (invitado) return
    const ctl = new AbortController()
    get<PaginaHistorial>('/api/consulta/historial?por_pagina=10', ctl.signal)
      .then((d) => setRecientes([...new Set(d.elementos.map((c) => c.pregunta))].slice(0, 3)))
      .catch(() => { /* la bienvenida funciona sin ellas */ })
    return () => ctl.abort()
  }, [invitado])

  const ajustarAltura = () => {
    const a = area.current
    if (!a) return
    a.style.height = 'auto'
    a.style.height = `${Math.min(a.scrollHeight, 180)}px`
  }
  useEffect(ajustarAltura, [texto])

  const enviar = useCallback(async (pregunta: string, voz = false) => {
    const p = pregunta.trim()
    if (!p || control.current) return
    const modo: Modo = socratico ? 'socratico' : 'normal'
    const historial = mensajes
      .filter((m) => m.estado === 'listo' && m.texto.trim())
      .slice(-TURNOS_HISTORIAL)
      .map((m) => ({ rol: m.rol, texto: m.texto }))
    const idRespuesta = nuevoId()
    setMensajes((ms) => [
      ...ms,
      { id: nuevoId(), rol: 'usuario', texto: p, estado: 'listo', voz },
      { id: idRespuesta, rol: 'asistente', texto: '', estado: 'buscando', modo, pregunta: p },
    ])
    setTexto('')
    seguir.current = true
    const ctl = new AbortController()
    control.current = ctl
    const actualizar = (cambio: Partial<Mensaje> | ((m: Mensaje) => Partial<Mensaje>)) =>
      setMensajes((ms) => ms.map((m) => (m.id === idRespuesta ? { ...m, ...(typeof cambio === 'function' ? cambio(m) : cambio) } : m)))
    try {
      for await (const ev of flujo('/api/consulta', { pregunta: p, modo, historial }, ctl.signal)) {
        if (ev.evento === 'fuentes') actualizar({ fuentes: ev.datos.fuentes })
        else if (ev.evento === 'token') actualizar((m) => ({ texto: m.texto + ev.datos.texto, estado: 'escribiendo' }))
        else if (ev.evento === 'fin') actualizar({ ...ev.datos, estado: 'listo' })
        else if (ev.evento === 'error') actualizar({ estado: 'error', error: ev.datos.mensaje })
      }
      // El flujo terminó sin «fin»: detenido por la persona o cortado por la red.
      actualizar((m) => (m.estado === 'buscando' || m.estado === 'escribiendo'
        ? ctl.signal.aborted
          ? { estado: m.texto ? 'listo' : 'error', error: 'Has detenido la respuesta.' }
          : { estado: 'error', error: 'La respuesta se ha cortado. Inténtalo de nuevo.' }
        : {}))
    } catch (e) {
      actualizar((m) => ({
        estado: ctl.signal.aborted && m.texto ? 'listo' : 'error',
        error: ctl.signal.aborted ? 'Has detenido la respuesta.' : e instanceof Error ? e.message : String(e),
      }))
    } finally {
      if (control.current === ctl) control.current = null
      area.current?.focus()
    }
  }, [mensajes, socratico])

  // /copiloto?pregunta=... (enlaces desde otras pantallas): se pregunta al entrar.
  // (con un temporizador que se cancela, para que el doble montaje de React no pregunte dos veces)
  useEffect(() => {
    const q = params.get('pregunta')
    if (!q) return
    const t = setTimeout(() => {
      // Solo se quita «pregunta»: el resto (p. ej. embed=1 dentro de la app de escritorio) se conserva.
      const resto = new URLSearchParams(params)
      resto.delete('pregunta')
      setParams(resto, { replace: true })
      enviar(q)
    }, 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const detener = () => control.current?.abort()

  const nuevaConversacion = () => {
    control.current?.abort()
    setMensajes([])
    setPanel(null)
    setTexto('')
    area.current?.focus()
  }

  const reintentar = (m: Mensaje) => {
    if (!m.pregunta || control.current) return
    setMensajes((ms) => {
      const i = ms.findIndex((x) => x.id === m.id)
      // Se quitan la respuesta fallida y la pregunta que la originó; enviar() las vuelve a poner.
      return i > 0 && ms[i - 1].rol === 'usuario' ? [...ms.slice(0, i - 1), ...ms.slice(i + 1)] : ms.filter((x) => x.id !== m.id)
    })
    setTimeout(() => enviar(m.pregunta!), 0)
  }

  const valorar = async (m: Mensaje, valor: 1 | -1) => {
    if (!m.consulta_id) return
    try {
      await post(`/api/consulta/${m.consulta_id}/valoracion`, { valor })
      setMensajes((ms) => ms.map((x) => (x.id === m.id ? { ...x, valoracion: valor } : x)))
      avisar(valor === 1 ? 'Gracias. Nos ayuda a saber qué funciona.' : 'Gracias. Lo tendremos en cuenta para mejorar.')
    } catch (e) {
      avisarError(e)
    }
  }

  const copiar = async (m: Mensaje) => {
    const limpio = separarCitas(m.texto).replace(/\s?\[\d{1,2}\]/g, '').trim()
    avisar((await copiarTexto(limpio)) ? 'Respuesta copiada.' : 'No se ha podido copiar.', 'info')
  }

  const abrirCita = (m: Mensaje, n: number) => {
    if ((m.fuentes ?? []).some((f) => f.n === n)) setPanel({ id: m.id, n })
    else avisar('Esa cita no corresponde a ninguna fuente de esta respuesta.', 'info')
  }

  const recuperar = (c: ConsultaGuardada) => {
    setHistorialAbierto(false)
    seguir.current = true
    setMensajes((ms) => [
      ...ms,
      { id: nuevoId(), rol: 'usuario', texto: c.pregunta, estado: 'listo' },
      {
        id: nuevoId(), rol: 'asistente', texto: c.respuesta ?? '', estado: 'listo', fuentes: c.fuentes, modo: c.modo,
        con_respaldo: c.con_respaldo, aviso_sin_respaldo: c.aviso_sin_respaldo, laguna_id: c.laguna_id,
        consulta_id: c.id, citadas: c.citadas,
        valoracion: c.valoracion, duracion_ms: c.duracion_ms ?? undefined, pregunta: c.pregunta,
        // Una respuesta detenida antes de escribir nada se guarda sin texto.
        error: c.respuesta ? undefined : 'Esta respuesta se detuvo antes de empezar a escribirse.',
      },
    ])
  }

  const iniciarSesion = async () => {
    await salir()
    navegar('/acceso')
  }

  const mensajePanel = panel ? mensajes.find((m) => m.id === panel.id) : undefined
  const nombre = perfil && !perfil.invitado ? perfil.nombre.split(' ')[0] : ''
  const sugerencias = invitado ? SUGERENCIAS_INVITADO : SUGERENCIAS_EMPLEADO

  return (
    <div className="copiloto">
      <Cabecera
        antetitulo={<><Sparkles size={14} /> Copiloto</>}
        titulo="Pregunta lo que necesites"
        subtitulo="Respondo con la documentación de la empresa y te digo de dónde sale cada dato."
        acciones={<>
          <span title="Te guío con preguntas para que llegues tú a la respuesta, en lugar de dártela hecha.">
            <Interruptor activo={socratico} onCambio={setSocratico} etiqueta="Modo socrático" />
          </span>
          {!invitado && (
            <Boton icono={<History />} onClick={() => setHistorialAbierto(true)}>Historial</Boton>
          )}
          <Boton icono={<MessageSquarePlus />} onClick={nuevaConversacion} disabled={!mensajes.length && !enCurso}>
            Nueva conversación
          </Boton>
        </>}
      />

      {invitado && (
        <div className="mb-2">
          <Aviso tono="amarillo" titulo="Estás usando CidIA sin iniciar sesión">
            Solo consulto los documentos públicos de la empresa y hay un límite de preguntas por hora.{' '}
            <button type="button" className="enlace-texto" onClick={iniciarSesion}>
              <LogIn size={14} /> Inicia sesión
            </button>{' '}
            para buscar en el conocimiento de tu puesto.
          </Aviso>
        </div>
      )}

      <div className="copiloto-mensajes">
        {mensajes.length === 0 ? (
          <div className="bienvenida">
            <div className="bienvenida-logo"><LogoCidia tamano={58} /></div>
            <h2>{nombre ? `${saludo()}, ${nombre}.` : `${saludo()}.`} ¿En qué te ayudo?</h2>
            <p className="apagado">
              Pregunta como se lo preguntarías a un compañero con experiencia.
              {!invitado && <> También puedes hablarme: mantén pulsado el <Mic size={14} className="en-linea" /> y suelta al terminar.</>}
            </p>
            <div className="sugerencias">
              {sugerencias.map((s) => (
                <button key={s.texto} type="button" className="sugerencia" onClick={() => enviar(s.texto)}>
                  <span className="sugerencia-icono">{s.icono}</span>
                  <span>{s.texto}</span>
                </button>
              ))}
            </div>
            {recientes.length > 0 && (
              <div className="recientes">
                <div className="diminuto apagado mb-1">Retoma lo último que preguntaste</div>
                <div className="fila envolver" style={{ justifyContent: 'center' }}>
                  {recientes.map((r) => (
                    <button key={r} type="button" className="reciente" onClick={() => enviar(r)} title={r}>
                      <History size={14} /> <span className="recortar">{r}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          mensajes.map((m) => m.rol === 'usuario' ? (
            <div key={m.id} className="burbuja usuario">
              {m.voz && <Mic size={14} className="icono-voz" aria-label="Pregunta por voz" />}
              <span className="pre">{m.texto}</span>
            </div>
          ) : (
            <Respuesta
              key={m.id}
              m={m}
              invitado={invitado}
              onCita={(n) => abrirCita(m, n)}
              onValorar={(v) => valorar(m, v)}
              onCopiar={() => copiar(m)}
              onReintentar={() => reintentar(m)}
            />
          ))
        )}
      </div>

      <div className="compositor-zona">
        {socratico && (
          <div className="modo-aviso">
            <GraduationCap size={15} /> Modo socrático: te guiaré con preguntas para que llegues tú a la respuesta.
          </div>
        )}
        <form className="chat-entrada compositor" onSubmit={(e) => { e.preventDefault(); enviar(texto) }}>
          <textarea
            ref={area}
            rows={1}
            value={texto}
            maxLength={4000}
            aria-label="Tu pregunta"
            placeholder={enCurso ? 'Esperando la respuesta…' : 'Escribe tu pregunta…'}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                enviar(texto)
              }
            }}
          />
          {!invitado && <BotonVoz onTexto={(t) => enviar(t, true)} deshabilitado={enCurso} />}
          {enCurso ? (
            <Boton type="button" variante="oscuro" icono={<Square />} onClick={detener} title="Detener la respuesta"
              aria-label="Detener la respuesta" />
          ) : (
            <Boton type="submit" variante="primario" icono={<Send />} disabled={!texto.trim()} title="Enviar"
              aria-label="Enviar" />
          )}
        </form>
        <div className="compositor-ayuda diminuto apagado">
          Intro para enviar · Mayús + Intro para otra línea · Comprueba siempre los datos críticos en la fuente.
          {perfil?.memoria_activa && (
            <> · <Link to="/perfil" className="enlace-memoria">Memoria personal activada</Link></>
          )}
        </div>
      </div>

      {mensajePanel && panel && (
        <PanelFuente
          fuentes={mensajePanel.fuentes ?? []}
          n={panel.n}
          citadas={mensajePanel.citadas}
          onCambiar={(n) => setPanel({ id: mensajePanel.id, n })}
          onCerrar={() => setPanel(null)}
        />
      )}

      {!invitado && (
        <Historial abierto={historialAbierto} onCerrar={() => setHistorialAbierto(false)} onElegir={recuperar} />
      )}
    </div>
  )
}

// ------------------------------------------------------------------ respuesta del copiloto

function Respuesta({ m, invitado, onCita, onValorar, onCopiar, onReintentar }: {
  m: Mensaje
  invitado: boolean
  onCita: (n: number) => void
  onValorar: (v: 1 | -1) => void
  onCopiar: () => void
  onReintentar: () => void
}) {
  const fuentes = m.fuentes ?? []
  const terminado = m.estado === 'listo'
  const sinRespaldo = terminado && m.con_respaldo === false
  // A un «hola» o un «gracias» no se le contesta «no lo he encontrado en la documentación».
  const avisoSinRespaldo = sinRespaldo && m.aviso_sin_respaldo !== false
  const citadas = m.citadas ?? []

  return (
    <div className="burbuja asistente">
      <div className="avatar-copiloto"><LogoCidia tamano={30} /></div>
      <div className={`globo ${m.estado === 'escribiendo' ? 'escribiendo' : ''}`}>
        {m.modo === 'socratico' && (
          <div className="modo-mensaje"><GraduationCap size={13} /> Modo socrático</div>
        )}

        {m.estado === 'buscando' ? (
          <div className="pensando">
            <span className="puntos" aria-hidden="true"><i /><i /><i /></span>
            {fuentes.length
              ? `He encontrado ${fuentes.length === 1 ? 'un fragmento' : `${fuentes.length} fragmentos`}. Redactando la respuesta…`
              : 'Buscando en la documentación…'}
          </div>
        ) : m.texto ? (
          <TextoFormato texto={separarCitas(m.texto)} onCita={onCita} />
        ) : null}

        {terminado && m.error && <div className="diminuto apagado mt-1">{m.error}</div>}

        {m.estado === 'error' && (
          <div className="respuesta-error">
            <span>{m.error ?? 'No se ha podido responder.'}</span>
            {m.pregunta && m.error !== 'Has detenido la respuesta.' && (
              <Boton tamano="pequeno" icono={<RotateCcw />} onClick={onReintentar}>Reintentar</Boton>
            )}
          </div>
        )}

        {avisoSinRespaldo && (
          <div className="sin-respaldo">
            <CircleHelp />
            <div>
              <strong>No lo he encontrado en la documentación.</strong>{' '}
              {m.laguna_id
                ? 'He apuntado tu pregunta para que alguien que lo sepa la responda. Mientras tanto, consúltalo con tu responsable.'
                : invitado
                  ? 'Inicia sesión para buscar también en la documentación de tu puesto.'
                  : 'Si es algo de tu trabajo, consúltalo con tu responsable.'}
            </div>
          </div>
        )}

        {fuentes.length > 0 && m.estado !== 'buscando' && (
          <ListaFuentes fuentes={fuentes} citadas={citadas} revisadas={sinRespaldo} onAbrir={onCita} />
        )}

        {terminado && !!m.consulta_id && (
          <div className="acciones-respuesta">
            <Boton variante="fantasma" tamano="pequeno" icono={<Copy />} onClick={onCopiar} title="Copiar la respuesta"
              aria-label="Copiar la respuesta" />
            <Boton variante="fantasma" tamano="pequeno" icono={<ThumbsUp />} onClick={() => onValorar(1)}
              className={m.valoracion === 1 ? 'valorada-si' : ''} title="Me ha sido útil" aria-label="Me ha sido útil"
              aria-pressed={m.valoracion === 1} />
            <Boton variante="fantasma" tamano="pequeno" icono={<ThumbsDown />} onClick={() => onValorar(-1)}
              className={m.valoracion === -1 ? 'valorada-no' : ''} title="No me ha sido útil"
              aria-label="No me ha sido útil" aria-pressed={m.valoracion === -1} />
            {typeof m.duracion_ms === 'number' && (
              <span className="diminuto apagado fila" style={{ gap: 4 }}>
                <Clock size={13} /> {(m.duracion_ms / 1000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} s
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ListaFuentes({ fuentes, citadas, revisadas, onAbrir }: {
  fuentes: Fuente[]; citadas: number[]; revisadas: boolean; onAbrir: (n: number) => void
}) {
  return (
    <div className="bloque-fuentes">
      <div className="fuentes-titulo">{revisadas ? 'Documentos revisados' : 'Fuentes'}</div>
      <div className="fuentes">
        {fuentes.map((f) => {
          const donde = ubicacion(f)
          const citada = citadas.includes(f.n) && f.disponible !== false
          const apagada = f.disponible === false || (!citada && citadas.length > 0)
          return (
            <button key={f.n} type="button" className={`fuente ${citada ? 'citada' : apagada ? 'sin-citar' : ''}`}
              onClick={() => onAbrir(f.n)} title={`${f.titulo}${donde ? ` · ${donde}` : ''}`}>
              <span className="n">{f.n}</span>
              <span className="recortar">{f.titulo}</span>
              {donde && <span className="ubic">{donde}</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
