// Componentes de interfaz de CidIA. Úsalos en todas las páginas para mantener el estilo.

import {
  Children, cloneElement, createContext, forwardRef, isValidElement, useCallback, useContext, useEffect, useId, useRef, useState,
  type ButtonHTMLAttributes, type InputHTMLAttributes, type KeyboardEvent as EventoTeclado, type ReactElement,
  type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertTriangle, CheckCircle2, Info, Loader2, Lock, RefreshCw, SearchX, UploadCloud, WifiOff, X, XCircle,
} from 'lucide-react'
import { ErrorApi } from '../api'

// ------------------------------------------------------------------ marca

export function LogoCidia({ tamano = 34 }: { tamano?: number }) {
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="11" fill="#F2C200" />
      <path d="M27.4 13.6a9.2 9.2 0 1 0 0 12.8" fill="none" stroke="#1F2328" strokeWidth="4.4" strokeLinecap="round" />
      <circle cx="29.2" cy="20" r="2.7" fill="#1F2328" />
    </svg>
  )
}

// ------------------------------------------------------------------ botones

type VarianteBoton = 'primario' | 'secundario' | 'verde' | 'oscuro' | 'peligro' | 'fantasma'

type PropsBoton = ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: VarianteBoton; tamano?: 'pequeno' | 'grande' | 'enorme'; icono?: ReactNode; cargando?: boolean; bloque?: boolean
}

export const Boton = forwardRef<HTMLButtonElement, PropsBoton>(function Boton({
  variante = 'secundario', tamano, icono, cargando, bloque, children, className = '', ...resto
}, ref) {
  const clases = ['boton', variante, tamano ?? '', bloque ? 'bloque' : '', !children ? 'icono' : '', className].filter(Boolean).join(' ')
  // Un botón solo con icono necesita nombre accesible: si no trae aria-label, usa su title.
  const nombre = !children && !resto['aria-label'] && typeof resto.title === 'string' ? resto.title : undefined
  return (
    <button ref={ref} className={clases} aria-label={nombre} aria-busy={cargando || undefined} {...resto} disabled={cargando || resto.disabled}>
      {cargando ? <Loader2 className="girando" /> : icono}
      {children}
    </button>
  )
})

// ------------------------------------------------------------------ estructura

export function Cabecera({ titulo, subtitulo, antetitulo, acciones }: {
  titulo: ReactNode; subtitulo?: ReactNode; antetitulo?: ReactNode; acciones?: ReactNode
}) {
  return (
    <div className="cabecera">
      <div className="titulos">
        {antetitulo && <div className="antetitulo">{antetitulo}</div>}
        <h1>{titulo}</h1>
        {subtitulo && <div className="subtitulo">{subtitulo}</div>}
      </div>
      {acciones && <div className="acciones">{acciones}</div>}
    </div>
  )
}

export function Tarjeta({ titulo, icono, acciones, pie, children, relleno = true, className = '', onClick }: {
  titulo?: ReactNode; icono?: ReactNode; acciones?: ReactNode; pie?: ReactNode; children?: ReactNode
  relleno?: boolean; className?: string; onClick?: () => void
}) {
  return (
    <div className={`tarjeta ${onClick ? 'interactiva' : ''} ${className}`} onClick={onClick}
      {...(onClick ? {
        role: 'button', tabIndex: 0,
        onKeyDown: (e: EventoTeclado<HTMLDivElement>) => {
          if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onClick() }
        },
      } : {})}>
      {(titulo || acciones) && (
        <div className="tarjeta-cabecera">
          <h3>{icono}{titulo}</h3>
          {acciones && <div className="fila">{acciones}</div>}
        </div>
      )}
      {children !== undefined && <div className={relleno ? 'tarjeta-cuerpo' : 'tarjeta-cuerpo sin-relleno'}>{children}</div>}
      {pie && <div className="tarjeta-pie">{pie}</div>}
    </div>
  )
}

export function Dato({ icono, valor, etiqueta, tono }: { icono: ReactNode; valor: ReactNode; etiqueta: ReactNode; tono?: 'verde' | 'alerta' | 'info' }) {
  return (
    <div className="dato">
      <div className={`icono-dato ${tono ?? ''}`}>{icono}</div>
      <div>
        <div className="valor">{valor}</div>
        <div className="dato-etiqueta">{etiqueta}</div>
      </div>
    </div>
  )
}

export function Etiqueta({ children, tono, icono, title }: {
  children: ReactNode; tono?: 'amarilla' | 'verde' | 'roja' | 'naranja' | 'azul' | 'oscura'; icono?: ReactNode; title?: string
}) {
  return <span className={`etiqueta ${tono ?? ''}`} title={title}>{icono}{children}</span>
}

export function Aviso({ tono, children, titulo }: { tono?: 'exito' | 'alerta' | 'amarillo'; children: ReactNode; titulo?: string }) {
  const icono = tono === 'exito' ? <CheckCircle2 /> : tono === 'alerta' ? <AlertTriangle /> : <Info />
  return (
    <div className={`aviso ${tono ?? ''}`} role={tono === 'alerta' ? 'alert' : undefined}>
      {icono}
      <div>{titulo && <div className="negrita">{titulo}</div>}{children}</div>
    </div>
  )
}

export function Avatar({ nombre, iniciales, tamano, color }: { nombre?: string; iniciales?: string; tamano?: 'p' | 'g'; color?: string }) {
  const ini = iniciales ?? (nombre ?? '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()
  const paleta = ['#1F8A70', '#2F6FBF', '#8A6D00', '#7A4FB5', '#C8442F', '#3A4048', '#0E7C86']
  const h = (nombre ?? ini).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return <div className={`avatar ${tamano ?? ''}`} style={{ background: color ?? paleta[h % paleta.length] }} title={nombre}>{ini}</div>
}

export function Vacio({ icono, titulo, children, accion }: { icono?: ReactNode; titulo: string; children?: ReactNode; accion?: ReactNode }) {
  return (
    <div className="vacio">
      {icono && <div className="icono-vacio">{icono}</div>}
      <h3>{titulo}</h3>
      {children && <div className="pequeno" style={{ maxWidth: 460 }}>{children}</div>}
      {accion && <div className="mt-1">{accion}</div>}
    </div>
  )
}

export function Cargando({ texto = 'Cargando…' }: { texto?: string }) {
  return <div className="cargando" role="status" aria-live="polite"><Loader2 className="girando" size={20} /> {texto}</div>
}

/** Esqueleto genérico de una página: cabecera y tarjetas. Para la carga perezosa de las rutas. */
export function EsqueletoPagina() {
  return (
    <div className="esqueleto-pagina" role="status" aria-label="Cargando la página">
      <Esqueleto alto={13} ancho={120} />
      <Esqueleto alto={30} ancho="42%" className="mt-1" />
      <Esqueleto alto={15} ancho="64%" className="mt-1" />
      <div className="rejilla c3 mt-3">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={86} />)}</div>
      <Esqueleto alto={260} className="mt-2" />
    </div>
  )
}

export function Esqueleto({ alto = 16, ancho = '100%', className = '' }: { alto?: number; ancho?: number | string; className?: string }) {
  return <div className={`esqueleto ${className}`} style={{ height: alto, width: ancho }} />
}

export function BarraProgreso({ valor, tono }: { valor: number; tono?: 'amarilla' }) {
  return <div className={`barra-progreso ${tono ?? ''}`}><div style={{ width: `${Math.max(0, Math.min(100, valor))}%` }} /></div>
}

export function ErrorCarga({ error, reintentar }: { error: unknown; reintentar?: () => void }) {
  const msg = error instanceof ErrorApi || error instanceof Error ? error.message : String(error)
  const estado = error instanceof ErrorApi ? error.estado : -1
  const sinConexion = estado === 0 || estado >= 502
  // Reintentar no arregla un «no existe» ni un «no tienes acceso»: ahí no se ofrece.
  const [icono, titulo, conReintento] =
    sinConexion ? [<WifiOff key="i" />, 'Sin conexión con el servidor', true]
      : estado === 404 ? [<SearchX key="i" />, 'No lo encontramos', false]
        : estado === 403 ? [<Lock key="i" />, 'No tienes acceso a esto', false]
          : [<XCircle key="i" />, 'No se ha podido cargar', true]
  return (
    <div role="alert" className={`error-carga ${sinConexion || estado >= 500 ? 'grave' : ''}`}>
      <Vacio icono={icono} titulo={titulo}
        accion={reintentar && conReintento && <Boton icono={<RefreshCw />} onClick={reintentar}>Reintentar</Boton>}>
        {msg}
      </Vacio>
    </div>
  )
}

// ------------------------------------------------------------------ formularios

const CONTROLES = new Set<unknown>(['input', 'select', 'textarea'])

export function Campo({ etiqueta, ayuda, children }: { etiqueta?: ReactNode; ayuda?: ReactNode; children: ReactNode }) {
  // Asocia la etiqueta (y la ayuda) al control cuando el campo contiene uno solo.
  const id = useId()
  const unico = Children.count(children) === 1 && isValidElement(children) ? (children as ReactElement<Record<string, unknown>>) : null
  const esControl = !!unico && (CONTROLES.has(unico.type) || unico.type === Entrada || unico.type === Selector || unico.type === Area)
  const idControl = esControl ? ((unico!.props.id as string | undefined) ?? id) : undefined
  const idAyuda = ayuda && esControl ? `${id}-ayuda` : undefined
  const control = esControl
    ? cloneElement(unico!, { id: idControl, 'aria-describedby': (unico!.props['aria-describedby'] as string | undefined) ?? idAyuda })
    : children
  return (
    <div className="campo">
      {etiqueta && <label htmlFor={idControl}>{etiqueta}</label>}
      {control}
      {ayuda && <div className="ayuda" id={idAyuda}>{ayuda}</div>}
    </div>
  )
}

export function Entrada(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="entrada" {...props} />
}

export function Selector({ opciones, vacio, ...props }: SelectHTMLAttributes<HTMLSelectElement> & {
  opciones: { valor: string | number; texto: string }[]; vacio?: string
}) {
  return (
    <select className="selector" {...props}>
      {vacio !== undefined && <option value="">{vacio}</option>}
      {opciones.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
    </select>
  )
}

export function Area(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="area" {...props} />
}

export function Interruptor({ activo, onCambio, etiqueta, deshabilitado }: {
  activo: boolean; onCambio: (v: boolean) => void; etiqueta?: ReactNode; deshabilitado?: boolean
}) {
  return (
    <label className="interruptor">
      <input type="checkbox" role="switch" checked={activo} disabled={deshabilitado} onChange={(e) => onCambio(e.target.checked)} />
      <span className="pista" />
      {etiqueta && <span>{etiqueta}</span>}
    </label>
  )
}

export function Casilla({ marcada, onCambio, children }: { marcada: boolean; onCambio: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="casilla">
      <input type="checkbox" checked={marcada} onChange={(e) => onCambio(e.target.checked)} />
      {children}
    </label>
  )
}

export function Pestanas<T extends string>({ pestanas, activa, onCambio, etiqueta }: {
  pestanas: { id: T; texto: ReactNode; icono?: ReactNode; contador?: number }[]; activa: T; onCambio: (id: T) => void
  etiqueta?: string
}) {
  const lista = useRef<HTMLDivElement>(null)
  // Flechas, Inicio y Fin mueven entre pestañas (patrón ARIA de pestañas).
  const tecla = (e: EventoTeclado<HTMLDivElement>) => {
    const i = pestanas.findIndex((p) => p.id === activa)
    const destino = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0
      : e.key === 'End' ? pestanas.length - 1 : null
    if (destino === null || !pestanas.length) return
    e.preventDefault()
    const j = (destino + pestanas.length) % pestanas.length
    onCambio(pestanas[j].id)
    requestAnimationFrame(() => lista.current?.querySelectorAll<HTMLButtonElement>('[role=tab]')[j]?.focus())
  }
  return (
    <div className="pestanas" role="tablist" aria-label={etiqueta} ref={lista} onKeyDown={tecla}>
      {pestanas.map((p) => (
        <button key={p.id} type="button" role="tab" aria-selected={p.id === activa} tabIndex={p.id === activa ? 0 : -1}
          className={`pestana ${p.id === activa ? 'activa' : ''}`} onClick={() => onCambio(p.id)}>
          {p.icono}{p.texto}{p.contador !== undefined && <span className="contador">{p.contador}</span>}
        </button>
      ))}
    </div>
  )
}

export function ZonaSubida({ onFicheros, acepta, multiple, texto, detalle }: {
  onFicheros: (f: File[]) => void; acepta?: string; multiple?: boolean; texto?: string; detalle?: string
}) {
  const ref = useRef<HTMLInputElement>(null)
  const [encima, setEncima] = useState(false)
  return (
    <div
      className={`zona-subida ${encima ? 'encima' : ''}`}
      role="button" tabIndex={0}
      onClick={() => ref.current?.click()}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ref.current?.click() } }}
      onDragOver={(e) => { e.preventDefault(); setEncima(true) }}
      onDragLeave={() => setEncima(false)}
      onDrop={(e) => {
        e.preventDefault(); setEncima(false)
        const f = Array.from(e.dataTransfer.files)
        if (f.length) onFicheros(multiple ? f : [f[0]])
      }}
    >
      <UploadCloud />
      <strong>{texto ?? 'Arrastra aquí un fichero o haz clic para elegirlo'}</strong>
      {detalle && <div className="pequeno mt-1">{detalle}</div>}
      <input ref={ref} type="file" hidden accept={acepta} multiple={multiple}
        onChange={(e) => { const f = Array.from(e.target.files ?? []); if (f.length) onFicheros(f); e.target.value = '' }} />
    </div>
  )
}

// ------------------------------------------------------------------ modal

// Pila de diálogos abiertos: Escape cierra solo el de arriba.
const pilaModales: number[] = []
let siguienteModal = 1

const ENFOCABLES = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), '
  + 'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({ abierto, titulo, onCerrar, children, pie, ancho }: {
  abierto: boolean; titulo: ReactNode; onCerrar: () => void; children: ReactNode; pie?: ReactNode; ancho?: boolean
}) {
  const cerrar = useRef(onCerrar)
  cerrar.current = onCerrar
  const caja = useRef<HTMLDivElement>(null)
  const idTitulo = useId()
  useEffect(() => {
    if (!abierto) return
    const id = siguienteModal++
    pilaModales.push(id)
    const anterior = document.activeElement as HTMLElement | null
    // Foco dentro del diálogo: el primer campo si lo hay; si no, el propio diálogo.
    requestAnimationFrame(() => {
      const c = caja.current
      if (!c || c.contains(document.activeElement)) return
      const campo = c.querySelector<HTMLElement>(
        '[autofocus], .modal-cuerpo input:not([type=hidden]):not([disabled]), .modal-cuerpo textarea:not([disabled]), .modal-cuerpo select:not([disabled])')
      ;(campo ?? c).focus({ preventScroll: true })
    })
    document.body.classList.add('sin-desplazamiento')
    const tecla = (e: KeyboardEvent) => {
      if (pilaModales[pilaModales.length - 1] !== id) return
      if (e.key === 'Escape') {
        e.stopPropagation()
        cerrar.current()
      } else if (e.key === 'Tab' && caja.current) {
        // El foco no sale del diálogo mientras está abierto.
        const lista = Array.from(caja.current.querySelectorAll<HTMLElement>(ENFOCABLES)).filter((x) => x.offsetParent !== null)
        if (!lista.length) return
        const primero = lista[0]
        const ultimo = lista[lista.length - 1]
        const activo = document.activeElement
        if (e.shiftKey && (activo === primero || activo === caja.current)) { e.preventDefault(); ultimo.focus() }
        else if (!e.shiftKey && (activo === ultimo || !caja.current.contains(activo))) { e.preventDefault(); primero.focus() }
      }
    }
    window.addEventListener('keydown', tecla)
    return () => {
      window.removeEventListener('keydown', tecla)
      const i = pilaModales.indexOf(id)
      if (i >= 0) pilaModales.splice(i, 1)
      if (!pilaModales.length) document.body.classList.remove('sin-desplazamiento')
      if (anterior && document.contains(anterior)) anterior.focus({ preventScroll: true })
    }
  }, [abierto])
  if (!abierto) return null
  return (
    <div className="velo" onMouseDown={(e) => e.target === e.currentTarget && onCerrar()}>
      <div ref={caja} className={`modal ${ancho ? 'ancho' : ''}`} role="dialog" aria-modal="true" aria-labelledby={idTitulo} tabIndex={-1}>
        <div className="modal-cabecera">
          <h2 id={idTitulo}>{titulo}</h2>
          <Boton variante="fantasma" icono={<X />} onClick={onCerrar} aria-label="Cerrar" />
        </div>
        <div className="modal-cuerpo">{children}</div>
        {pie && <div className="modal-pie">{pie}</div>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ avisos flotantes

interface AvisoFlotante { id: number; tono: 'exito' | 'error' | 'info'; texto: string }
const CtxAvisos = createContext<(texto: string, tono?: AvisoFlotante['tono']) => void>(() => {})

export function ProveedorAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<AvisoFlotante[]>([])
  const quitar = useCallback((id: number) => setAvisos((a) => a.filter((x) => x.id !== id)), [])
  const avisar = useCallback((texto: string, tono: AvisoFlotante['tono'] = 'exito') => {
    const id = Date.now() + Math.random()
    // Sin repetir el mismo aviso si ya está a la vista; como mucho tres a la vez.
    setAvisos((a) => a.some((x) => x.texto === texto && x.tono === tono) ? a : [...a, { id, tono, texto }].slice(-3))
    setTimeout(() => quitar(id), tono === 'error' ? 7000 : 4000)
  }, [quitar])
  return (
    <CtxAvisos.Provider value={avisar}>
      {children}
      <div className="avisos-flotantes" aria-live="polite">
        {avisos.map((a) => (
          <div key={a.id} className={`aviso-flotante ${a.tono}`} role={a.tono === 'error' ? 'alert' : 'status'}>
            {a.tono === 'exito' ? <CheckCircle2 /> : a.tono === 'error' ? <XCircle /> : <Info />}
            <span className="crece">{a.texto}</span>
            <button type="button" className="cerrar-aviso" aria-label="Cerrar aviso" onClick={() => quitar(a.id)}><X /></button>
          </div>
        ))}
      </div>
    </CtxAvisos.Provider>
  )
}

/** avisar('Guardado') · avisar('Algo ha fallado', 'error') */
export function useAvisos() {
  return useContext(CtxAvisos)
}

/** Muestra el mensaje de un error de la API como aviso. */
export function useAvisarError() {
  const avisar = useAvisos()
  return useCallback((e: unknown) => {
    const msg = e instanceof Error ? e.message : String(e)
    avisar(msg, 'error')
  }, [avisar])
}

// ------------------------------------------------------------------ datos

/** Carga datos de la API con estado de carga y error. `recargar()` vuelve a pedirlos. */
export function useDatos<T>(cargar: (senal: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  const [datos, setDatos] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [cargando, setCargando] = useState(true)
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const ctl = new AbortController()
    setCargando(true)
    setError(null)
    cargar(ctl.signal)
      .then((d) => { if (!ctl.signal.aborted) setDatos(d) })
      .catch((e) => { if (!ctl.signal.aborted && e?.name !== 'AbortError') setError(e) })
      .finally(() => { if (!ctl.signal.aborted) setCargando(false) })
    return () => ctl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])
  const recargar = useCallback(() => setVersion((v) => v + 1), [])
  return { datos, error, cargando, recargar, setDatos }
}

// ------------------------------------------------------------------ texto con formato

/** Markdown seguro (sin HTML) con las citas [n] convertidas en marcas pulsables. */
export function TextoFormato({ texto, onCita }: { texto: string; onCita?: (n: number) => void }) {
  const conCitas = texto.replace(/\[(\d{1,2})\]/g, (_, n) => `[​${n}](#cita-${n})`)
  return (
    <div className="formato">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const m = href?.match(/^#cita-(\d+)$/)
            if (m) {
              const n = Number(m[1])
              return (
                <span className="cita" role="button" tabIndex={0} aria-label={`Fuente ${n}`} onClick={() => onCita?.(n)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onCita?.(n) } }}>{n}</span>
              )
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>
          },
        }}
      >
        {conCitas}
      </ReactMarkdown>
    </div>
  )
}

// ------------------------------------------------------------------ ILUO

/** Cuadrado ILUO: un trazo por nivel (1 I, 2 L, 3 U, 4 O relleno). */
export function Iluo({ nivel, tamano = 28, caducado }: { nivel: number; tamano?: number; caducado?: boolean }) {
  const t = tamano
  const g = Math.max(2.5, t / 9)
  const c = caducado ? '#C8442F' : '#1F2328'
  const m = g / 2
  return (
    <svg className="iluo" width={t} height={t} viewBox={`0 0 ${t} ${t}`} aria-label={`Nivel ${['sin iniciar', 'I', 'L', 'U', 'O'][nivel] ?? ''}`}>
      <rect x={m} y={m} width={t - g} height={t - g} fill={nivel >= 4 ? '#F2C200' : 'none'} stroke="#D9DCE1" strokeWidth={1} />
      {nivel >= 1 && <line x1={m} y1={m} x2={m} y2={t - m} stroke={c} strokeWidth={g} strokeLinecap="round" />}
      {nivel >= 2 && <line x1={m} y1={t - m} x2={t - m} y2={t - m} stroke={c} strokeWidth={g} strokeLinecap="round" />}
      {nivel >= 3 && <line x1={t - m} y1={t - m} x2={t - m} y2={m} stroke={c} strokeWidth={g} strokeLinecap="round" />}
      {nivel >= 4 && <line x1={m} y1={m} x2={t - m} y2={m} stroke={c} strokeWidth={g} strokeLinecap="round" />}
    </svg>
  )
}

export const LETRA_ILUO = ['·', 'I', 'L', 'U', 'O']
export const NOMBRE_ILUO = ['Sin iniciar', 'En formación', 'Ejecuta con apoyo', 'Autónomo', 'Puede formar a otros']

// ------------------------------------------------------------------ voz

/** Grabación de voz «mantén pulsado para hablar». Devuelve un Blob webm/ogg al soltar. */
/** ¿Va embebida en la app de escritorio? Allí el micrófono lo pone el marco principal. */
function enAppDeEscritorio(): boolean {
  try { return window.location.protocol === 'dsh-app:' && window.parent !== window } catch { return false }
}

type RespuestaMicro = { estado: 'grabando' | 'lista' | 'cancelada' | 'error'; audio?: Blob; duracion_ms?: number; mensaje?: string }

/** Pide al plugin de la app que haga una acción de grabación y espera su respuesta. */
function pedirAlPuente(id: string, accion: 'empezar' | 'parar' | 'cancelar', esperar: RespuestaMicro['estado'][]): Promise<RespuestaMicro> {
  return new Promise((resolver) => {
    const temporizador = window.setTimeout(() => { window.removeEventListener('message', alMensaje); resolver({ estado: 'error', mensaje: 'La app no responde al pedir el micrófono.' }) }, accion === 'empezar' ? 20000 : 15000)
    function alMensaje(e: MessageEvent) {
      if (e.origin !== window.location.origin || e.source !== window.parent) return
      const d = e.data
      if (!d || d.tipo !== 'cidia:microfono' || d.id !== id) return
      if (!esperar.includes(d.estado) && d.estado !== 'error') return
      window.clearTimeout(temporizador)
      window.removeEventListener('message', alMensaje)
      resolver(d as RespuestaMicro)
    }
    window.addEventListener('message', alMensaje)
    window.parent.postMessage({ tipo: 'cidia:microfono', id, accion }, window.location.origin)
  })
}

export function useGrabadora() {
  const [grabando, setGrabando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const grabador = useRef<MediaRecorder | null>(null)
  const trozos = useRef<Blob[]>([])
  const resolver = useRef<((b: Blob | null) => void) | null>(null)
  const inicio = useRef(0)
  const flujoActual = useRef<MediaStream | null>(null)
  const idPuente = useRef<string | null>(null)

  // Al desmontar el componente se apaga el micrófono si seguía grabando.
  useEffect(() => () => {
    if (idPuente.current) {
      try { window.parent.postMessage({ tipo: 'cidia:microfono', id: idPuente.current, accion: 'cancelar' }, window.location.origin) } catch { /* sin app */ }
      idPuente.current = null
    }
    flujoActual.current?.getTracks().forEach((t) => t.stop())
    if (grabador.current && grabador.current.state !== 'inactive') {
      resolver.current = null
      try { grabador.current.stop() } catch { /* ya parado */ }
    }
  }, [])

  const empezar = useCallback(async () => {
    setError(null)
    if (enAppDeEscritorio()) {
      const id = `micro-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      idPuente.current = id
      inicio.current = Date.now()
      setGrabando(true)
      const r = await pedirAlPuente(id, 'empezar', ['grabando'])
      if (r.estado !== 'grabando') {
        idPuente.current = null
        setGrabando(false)
        setError(r.mensaje ?? 'No se puede usar el micrófono. Revisa los permisos de Windows.')
      }
      return
    }
    try {
      const flujo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      flujoActual.current = flujo
      const tipo = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
      const g = new MediaRecorder(flujo, tipo ? { mimeType: tipo } : undefined)
      trozos.current = []
      g.ondataavailable = (e) => e.data.size && trozos.current.push(e.data)
      g.onstop = () => {
        flujo.getTracks().forEach((t) => t.stop())
        flujoActual.current = null
        const blob = new Blob(trozos.current, { type: g.mimeType || 'audio/webm' })
        const corto = Date.now() - inicio.current < 400
        resolver.current?.(corto ? null : blob)
      }
      grabador.current = g
      inicio.current = Date.now()
      g.start()
      setGrabando(true)
    } catch {
      setError('No se puede usar el micrófono. Revisa los permisos.')
    }
  }, [])

  const parar = useCallback((): Promise<Blob | null> => {
    const id = idPuente.current
    if (id) {
      idPuente.current = null
      setGrabando(false)
      return pedirAlPuente(id, 'parar', ['lista', 'cancelada']).then((r) => {
        if (r.estado === 'error') { setError(r.mensaje ?? 'No se ha podido grabar.'); return null }
        if (r.estado !== 'lista' || !r.audio) return null
        return (r.duracion_ms ?? Date.now() - inicio.current) < 400 ? null : r.audio
      })
    }
    return new Promise((res) => {
      const g = grabador.current
      if (!g || g.state === 'inactive') return res(null)
      resolver.current = res
      g.stop()
      setGrabando(false)
    })
  }, [])

  return { grabando, error, empezar, parar, flujo: flujoActual }
}

// ------------------------------------------------------------------ confirmación

export function useConfirmar() {
  const [estado, setEstado] = useState<{ titulo: string; texto: ReactNode; peligro?: boolean; res: (v: boolean) => void } | null>(null)
  const confirmar = useCallback((titulo: string, texto: ReactNode, peligro = false) =>
    new Promise<boolean>((res) => setEstado({ titulo, texto, peligro, res })), [])
  const dialogo = estado && (
    <Modal abierto titulo={estado.titulo} onCerrar={() => { estado.res(false); setEstado(null) }}
      pie={<>
        <Boton autoFocus={estado.peligro} onClick={() => { estado.res(false); setEstado(null) }}>Cancelar</Boton>
        <Boton autoFocus={!estado.peligro} variante={estado.peligro ? 'peligro' : 'primario'}
          onClick={() => { estado.res(true); setEstado(null) }}>Confirmar</Boton>
      </>}>
      <div className="apagado">{estado.texto}</div>
    </Modal>
  )
  return { confirmar, dialogo }
}
