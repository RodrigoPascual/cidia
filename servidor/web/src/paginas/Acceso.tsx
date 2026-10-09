// Pantalla de inicio de sesión (o continuar sin sesión con servicios básicos).

import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { KeyRound, Lock, MessageSquare, ShieldCheck, User, Video, TrendingUp } from 'lucide-react'
import { get } from '../api'
import { useSesion } from '../sesion'
import { Aviso, Boton, LogoCidia } from '../ui'

export default function Acceso() {
  const { iniciar, entrarComoInvitado } = useSesion()
  const navegar = useNavigate()
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [info, setInfo] = useState<{ empresa: string | null; servidor: string } | null>(null)
  const [conectado, setConectado] = useState<boolean | null>(null)

  useEffect(() => {
    get<{ empresa: string | null; servidor: string }>('/api/sistema/info')
      .then((i) => { setInfo(i); setConectado(true) })
      .catch(() => setConectado(false))
  }, [])

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await iniciar(usuario, contrasena)
      navegar('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  async function invitado() {
    setError(null)
    try {
      await entrarComoInvitado()
      navegar('/copiloto')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="acceso">
      <div className="acceso-marca">
        <div className="fila" style={{ gap: 14 }}>
          <LogoCidia tamano={46} />
          <div>
            <div style={{ fontSize: 30, fontWeight: 700, lineHeight: 1 }}>CidIA</div>
            <div style={{ color: '#9aa3ae', fontSize: 14 }}>Copiloto de conocimiento industrial</div>
          </div>
        </div>
        <div className="acceso-lema" style={{ position: 'relative', zIndex: 1 }}>
          <h1 style={{ fontSize: 38, lineHeight: 1.15, maxWidth: 520 }}>
            El conocimiento experto <span style={{ color: 'var(--acento)' }}>se queda en la empresa</span>.
          </h1>
          <div className="columna mt-3" style={{ gap: 16, color: '#cfd4da', maxWidth: 480 }}>
            <div className="fila arriba"><Video size={20} color="#F2C200" /><span>El experto graba su tarea y CidIA la convierte en una instrucción de trabajo.</span></div>
            <div className="fila arriba"><MessageSquare size={20} color="#F2C200" /><span>Pregunta en el puesto, por voz o por texto, y recibe respuestas con su fuente.</span></div>
            <div className="fila arriba"><TrendingUp size={20} color="#F2C200" /><span>Tu progreso, con evidencias, en la matriz ILUO.</span></div>
          </div>
        </div>
        <div className="pequeno" style={{ color: '#8d96a2', position: 'relative', zIndex: 1 }}>
          <Lock size={13} style={{ verticalAlign: -2 }} /> Todo se procesa en el servidor de tu empresa. Nada sale a Internet.
        </div>
      </div>

      <div className="acceso-formulario">
        <form className="acceso-caja" onSubmit={enviar}>
          <h2 style={{ fontSize: 26 }}>Bienvenido a CidIA</h2>
          <div className="fila mt-1 mb-3 pequeno" style={{ color: conectado === false ? 'var(--alerta)' : 'var(--verde)' }}>
            <span className={`punto ${conectado === false ? 'mal' : ''}`} />
            {conectado === null ? 'Conectando con el servidor…'
              : conectado ? `Conectado al servidor de ${info?.empresa ?? 'la empresa'}`
                : 'No se encuentra el servidor de la empresa'}
          </div>

          {error && <div className="mb-2"><Aviso tono="alerta">{error}</Aviso></div>}

          <div className="campo">
            <label htmlFor="usuario">Usuario</label>
            <div className="entrada-icono">
              <User />
              <input id="usuario" className="entrada" autoComplete="username" autoFocus value={usuario}
                onChange={(e) => setUsuario(e.target.value)} placeholder="tu.usuario" style={{ height: 46 }} />
            </div>
          </div>
          <div className="campo">
            <label htmlFor="contrasena">Contraseña</label>
            <div className="entrada-icono">
              <KeyRound />
              <input id="contrasena" className="entrada" type="password" autoComplete="current-password" value={contrasena}
                onChange={(e) => setContrasena(e.target.value)} placeholder="••••••••" style={{ height: 46 }} />
            </div>
          </div>
          <Boton variante="primario" tamano="grande" bloque type="submit" cargando={enviando} disabled={!usuario || !contrasena}>
            Iniciar sesión
          </Boton>
          <div className="separador" />
          <Boton variante="fantasma" bloque type="button" onClick={invitado} icono={<MessageSquare />}>
            Continuar sin sesión (servicios básicos)
          </Boton>
          <div className="diminuto apagado centro mt-2">
            <ShieldCheck size={13} style={{ verticalAlign: -2 }} /> Sin sesión solo tienes el chat general y los documentos públicos.
          </div>
        </form>
      </div>
    </div>
  )
}
