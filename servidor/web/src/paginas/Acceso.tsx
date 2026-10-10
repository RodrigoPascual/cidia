// Pantallas de acceso: inicio de sesión (o continuar sin sesión con servicios básicos), cambio
// obligatorio de la contraseña inicial o temporal, carga inicial y servidor sin conexión.

import { useCallback, useEffect, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Check, Eye, EyeOff, KeyRound, Loader2, Lock, LogOut, MessageSquare, RefreshCw, ShieldCheck, TrendingUp, User, Video,
  WifiOff,
} from 'lucide-react'
import { get, post } from '../api'
import { useSesion } from '../sesion'
import { Aviso, Boton, LogoCidia, useAvisos } from '../ui'

interface InfoServidor { empresa: string | null; servidor: string }

/** Ruta interna a la que volver tras iniciar sesión (solo rutas de la propia interfaz). */
function destinoSeguro(desde: unknown): string {
  if (typeof desde !== 'string' || !desde.startsWith('/') || desde.startsWith('//') || desde.startsWith('/acceso')) return '/'
  return desde
}

/** Comprueba el servidor y vuelve a intentarlo solo mientras no responda. */
function useServidor() {
  const [info, setInfo] = useState<InfoServidor | null>(null)
  const [conectado, setConectado] = useState<boolean | null>(null)
  const [intento, setIntento] = useState(0)
  const comprobar = useCallback(() => setIntento((i) => i + 1), [])
  useEffect(() => {
    let vivo = true
    get<InfoServidor>('/api/sistema/info')
      .then((i) => { if (vivo) { setInfo(i); setConectado(true) } })
      .catch(() => { if (vivo) setConectado(false) })
    return () => { vivo = false }
  }, [intento])
  useEffect(() => {
    if (conectado !== false) return
    const t = setTimeout(comprobar, 8000)
    return () => clearTimeout(t)
  }, [conectado, intento, comprobar])
  return { info, conectado, comprobar }
}

// ------------------------------------------------------------------ estructura común

function MarcoAcceso({ children }: { children: ReactNode }) {
  return (
    <div className="acceso">
      <div className="acceso-marca">
        <div className="fila" style={{ gap: 14 }}>
          <LogoCidia tamano={46} />
          <div>
            <div className="acceso-nombre">CidIA</div>
            <div className="acceso-sub">Copiloto de conocimiento industrial</div>
          </div>
        </div>
        <div className="acceso-lema">
          <h1>El conocimiento experto <span>se queda en la empresa</span>.</h1>
          <ul className="acceso-ventajas">
            <li><Video /><span>El experto graba su tarea y CidIA la convierte en una instrucción de trabajo.</span></li>
            <li><MessageSquare /><span>Pregunta en el puesto, por voz o por texto, y recibe respuestas con su fuente.</span></li>
            <li><TrendingUp /><span>Tu progreso, con evidencias, en la matriz ILUO.</span></li>
          </ul>
        </div>
        <div className="acceso-privacidad">
          <Lock size={13} /> Todo se procesa en el servidor de tu empresa. Nada sale a Internet.
        </div>
      </div>
      <div className="acceso-formulario">{children}</div>
    </div>
  )
}

function EstadoServidor({ info, conectado, comprobar }: ReturnType<typeof useServidor>) {
  return (
    <div className={`acceso-servidor ${conectado === false ? 'mal' : conectado ? 'ok' : ''}`} role="status">
      {conectado === null ? <Loader2 className="girando" size={14} /> : <span className={`punto ${conectado ? '' : 'mal'}`} />}
      <span className="crece">
        {conectado === null ? 'Conectando con el servidor…'
          : conectado ? `Conectado al servidor de ${info?.empresa ?? 'la empresa'}`
            : 'No se encuentra el servidor de la empresa'}
      </span>
      {conectado === false && (
        <button type="button" className="enlace-boton" onClick={comprobar}><RefreshCw size={13} /> Reintentar</button>
      )}
    </div>
  )
}

function CampoContrasena({ id, valor, onCambio, autoComplete, placeholder, autoFocus }: {
  id: string; valor: string; onCambio: (v: string) => void; autoComplete: string; placeholder?: string; autoFocus?: boolean
}) {
  const [ver, setVer] = useState(false)
  const [mayusculas, setMayusculas] = useState(false)
  const mirar = (e: KeyboardEvent<HTMLInputElement>) => setMayusculas(e.getModifierState?.('CapsLock') ?? false)
  return (
    <>
      <div className="entrada-icono con-accion">
        <KeyRound />
        <input id={id} className="entrada grande" type={ver ? 'text' : 'password'} autoComplete={autoComplete} value={valor}
          autoFocus={autoFocus} placeholder={placeholder} onKeyUp={mirar} onKeyDown={mirar}
          onChange={(e) => onCambio(e.target.value)} aria-describedby={mayusculas ? `${id}-mayus` : undefined} />
        <button type="button" className="accion-entrada" onClick={() => setVer((v) => !v)}
          aria-label={ver ? 'Ocultar la contraseña' : 'Mostrar la contraseña'} aria-pressed={ver}>
          {ver ? <EyeOff /> : <Eye />}
        </button>
      </div>
      {mayusculas && <div className="ayuda texto-aviso" id={`${id}-mayus`}>Tienes activadas las mayúsculas (Bloq Mayús).</div>}
    </>
  )
}

// ------------------------------------------------------------------ inicio de sesión

export default function Acceso() {
  const { iniciar, entrarComoInvitado, motivoSalida } = useSesion()
  const navegar = useNavigate()
  const lugar = useLocation()
  const destino = destinoSeguro((lugar.state as { desde?: unknown } | null)?.desde)
  const servidor = useServidor()
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [entrandoInvitado, setEntrandoInvitado] = useState(false)

  useEffect(() => { document.title = 'Iniciar sesión · CidIA' }, [])

  async function enviar(e: FormEvent) {
    e.preventDefault()
    if (!usuario.trim() || !contrasena) return
    setError(null)
    setEnviando(true)
    try {
      await iniciar(usuario.trim(), contrasena)
      navegar(destino, { replace: true })
    } catch (err) {
      setError((err as Error).message)
      setContrasena('')
      servidor.comprobar()
    } finally {
      setEnviando(false)
    }
  }

  async function invitado() {
    setError(null)
    setEntrandoInvitado(true)
    try {
      await entrarComoInvitado()
      navegar('/copiloto', { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setEntrandoInvitado(false)
    }
  }

  return (
    <MarcoAcceso>
      <form className="acceso-caja" onSubmit={enviar} noValidate>
        <h2>Bienvenido a CidIA</h2>
        <EstadoServidor {...servidor} />

        {motivoSalida && !error && <div className="mb-2"><Aviso tono="amarillo">{motivoSalida}</Aviso></div>}
        {error && <div className="mb-2"><Aviso tono="alerta">{error}</Aviso></div>}

        <div className="campo">
          <label htmlFor="usuario">Usuario</label>
          <div className="entrada-icono">
            <User />
            <input id="usuario" className="entrada grande" autoComplete="username" autoFocus value={usuario}
              autoCapitalize="none" autoCorrect="off" spellCheck={false}
              onChange={(e) => setUsuario(e.target.value)} placeholder="tu.usuario" />
          </div>
        </div>
        <div className="campo">
          <label htmlFor="contrasena">Contraseña</label>
          <CampoContrasena id="contrasena" valor={contrasena} onCambio={setContrasena} autoComplete="current-password" placeholder="••••••••" />
        </div>
        <Boton variante="primario" tamano="grande" bloque type="submit" cargando={enviando} disabled={!usuario.trim() || !contrasena}>
          Iniciar sesión
        </Boton>
        <div className="separador" />
        <Boton variante="fantasma" bloque type="button" className="acceso-invitado" onClick={invitado} cargando={entrandoInvitado}
          icono={<MessageSquare />}>
          Continuar sin sesión (servicios básicos)
        </Boton>
        <div className="diminuto apagado centro mt-2">
          <ShieldCheck size={13} style={{ verticalAlign: -2 }} /> Sin sesión solo tienes el chat general y los documentos públicos.
        </div>
      </form>
    </MarcoAcceso>
  )
}

// ------------------------------------------------------------------ cambio obligatorio

/** Primer acceso con una contraseña inicial o temporal: hay que elegir una propia antes de seguir. */
export function CambioObligatorio() {
  const { perfil, recargar, salir } = useSesion()
  const avisar = useAvisos()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetida, setRepetida] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => { document.title = 'Elige tu contraseña · CidIA' }, [])

  const reglas = [
    { ok: nueva.length >= 8, texto: 'Al menos 8 caracteres' },
    { ok: nueva.length > 0 && nueva !== actual, texto: 'Distinta de la contraseña que te dieron' },
    { ok: repetida.length > 0 && repetida === nueva, texto: 'Las dos contraseñas coinciden' },
  ]
  const valido = actual.length > 0 && reglas.every((r) => r.ok)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    if (!valido) return
    setError(null)
    setEnviando(true)
    try {
      await post('/api/auth/contrasena', { actual, nueva })
      avisar('Contraseña guardada. Úsala a partir de ahora para entrar.')
      await recargar()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  const nombre = perfil?.nombre.split(' ')[0] ?? ''
  return (
    <MarcoAcceso>
      <form className="acceso-caja" onSubmit={enviar} noValidate>
        <div className="acceso-icono-paso"><ShieldCheck /></div>
        <h2>Hola{nombre ? `, ${nombre}` : ''}. Elige tu contraseña</h2>
        <p className="apagado mt-1 mb-3">
          Has entrado con una contraseña inicial o temporal que te ha dado la administración. Antes de seguir, cámbiala por
          una que solo sepas tú.
        </p>
        {error && <div className="mb-2"><Aviso tono="alerta">{error}</Aviso></div>}
        {/* Para que el gestor de contraseñas sepa de qué cuenta es */}
        <input type="text" name="usuario" autoComplete="username" value={perfil?.usuario ?? ''} hidden readOnly />
        <div className="campo">
          <label htmlFor="actual">Contraseña que te han dado</label>
          <CampoContrasena id="actual" valor={actual} onCambio={setActual} autoComplete="current-password" autoFocus />
        </div>
        <div className="campo">
          <label htmlFor="nueva">Nueva contraseña</label>
          <CampoContrasena id="nueva" valor={nueva} onCambio={setNueva} autoComplete="new-password" />
        </div>
        <div className="campo">
          <label htmlFor="repetida">Repite la nueva contraseña</label>
          <CampoContrasena id="repetida" valor={repetida} onCambio={setRepetida} autoComplete="new-password" />
        </div>
        <ul className="reglas-contrasena" aria-label="Requisitos de la contraseña">
          {reglas.map((r) => (
            <li key={r.texto} className={r.ok ? 'ok' : ''}><Check aria-hidden="true" />{r.texto}<span className="sr-solo">{r.ok ? ': cumplido' : ': pendiente'}</span></li>
          ))}
        </ul>
        <Boton variante="primario" tamano="grande" bloque type="submit" cargando={enviando} disabled={!valido}>
          Guardar y continuar
        </Boton>
        <div className="separador" />
        <Boton variante="fantasma" bloque type="button" icono={<LogOut />} onClick={() => void salir()}>
          Cerrar sesión y hacerlo más tarde
        </Boton>
        <div className="diminuto apagado centro mt-2">
          Mejor una frase fácil de recordar que una palabra rara. Nadie de la empresa te la pedirá nunca.
        </div>
      </form>
    </MarcoAcceso>
  )
}

// ------------------------------------------------------------------ carga y sin conexión

/** Pantalla mientras se comprueba la sesión al abrir la interfaz. Aparece con un leve retraso
 *  para no parpadear cuando la respuesta es inmediata. */
export function PantallaCarga() {
  return (
    <div className="pantalla-carga" role="status" aria-live="polite">
      <LogoCidia tamano={48} />
      <div className="fila apagado"><Loader2 className="girando" size={18} /> Conectando con CidIA…</div>
    </div>
  )
}

/** Hay una sesión guardada pero el servidor no responde: se espera y se reintenta sin cerrarla. */
export function SinConexion() {
  const { recargar, salir } = useSesion()
  const [probando, setProbando] = useState(false)
  const probar = useCallback(async () => {
    setProbando(true)
    try { await recargar() } finally { setProbando(false) }
  }, [recargar])
  useEffect(() => {
    const t = setInterval(() => void probar(), 10_000)
    window.addEventListener('online', probar)
    return () => { clearInterval(t); window.removeEventListener('online', probar) }
  }, [probar])
  return (
    <div className="pantalla-carga" role="alert">
      <div className="sin-conexion-caja">
        <div className="icono-vacio"><WifiOff /></div>
        <h2>No hay conexión con el servidor de la empresa</h2>
        <p className="apagado">
          Comprueba que el equipo está conectado a la red de la planta. Tu sesión se conserva: en cuanto el servidor
          responda, sigues donde estabas. Se vuelve a intentar cada pocos segundos.
        </p>
        <div className="fila" style={{ justifyContent: 'center' }}>
          <Boton variante="primario" icono={<RefreshCw />} cargando={probando} onClick={() => void probar()}>Reintentar ahora</Boton>
          <Boton variante="fantasma" icono={<LogOut />} onClick={() => void salir()}>Cerrar sesión</Boton>
        </div>
      </div>
    </div>
  )
}
