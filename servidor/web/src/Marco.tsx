// Estructura común: barra lateral con la navegación según los servicios de cada persona.

import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Brain, ClipboardCheck, FileText, FolderOpen, GraduationCap, HelpCircle, Home, Inbox, Lightbulb, ListChecks,
  LogIn, LogOut, Menu, MessageSquare, Network, ScrollText, Server, TrendingUp, UserCog, Users, Video, Wrench,
} from 'lucide-react'
import { EMBEBIDA, get } from './api'
import { NOMBRE_ROL, useSesion } from './sesion'
import { Avatar, Boton, LogoCidia } from './ui'

interface Enlace { ruta: string; texto: string; icono: ReactNode; servicio: string | null; contador?: string }
interface Grupo { titulo: string; enlaces: Enlace[] }

const NAVEGACION: Grupo[] = [
  {
    titulo: 'Mi trabajo',
    enlaces: [
      { ruta: '/', texto: 'Inicio', icono: <Home />, servicio: 'perfil' },
      { ruta: '/copiloto', texto: 'Copiloto', icono: <MessageSquare />, servicio: 'chat' },
      { ruta: '/planta', texto: 'Modo planta', icono: <Wrench />, servicio: 'planta' },
      { ruta: '/formacion', texto: 'Formación', icono: <GraduationCap />, servicio: 'formacion' },
      { ruta: '/evaluacion', texto: 'Evaluación', icono: <ClipboardCheck />, servicio: 'evaluacion', contador: 'evaluacion' },
      { ruta: '/progreso', texto: 'Mi progreso', icono: <TrendingUp />, servicio: 'progreso' },
      { ruta: '/aportaciones', texto: 'Aportaciones', icono: <Lightbulb />, servicio: 'aportaciones' },
      { ruta: '/espacio', texto: 'Espacio de trabajo', icono: <FolderOpen />, servicio: 'espacio' },
    ],
  },
  {
    titulo: 'Conocimiento',
    enlaces: [
      { ruta: '/captura', texto: 'Captura', icono: <Video />, servicio: 'captura' },
      { ruta: '/instrucciones', texto: 'Instrucciones', icono: <ListChecks />, servicio: 'instrucciones', contador: 'borradores' },
      { ruta: '/documentos', texto: 'Documentos', icono: <FileText />, servicio: 'documentos' },
    ],
  },
  {
    titulo: 'Mi equipo',
    enlaces: [
      { ruta: '/validar', texto: 'Validar aportaciones', icono: <Inbox />, servicio: 'validar', contador: 'aportaciones' },
      { ruta: '/lagunas', texto: 'Lagunas', icono: <HelpCircle />, servicio: 'lagunas', contador: 'lagunas' },
      { ruta: '/equipo', texto: 'Progreso del equipo', icono: <Users />, servicio: 'equipo' },
    ],
  },
  {
    titulo: 'Administración',
    enlaces: [
      { ruta: '/admin/organizacion', texto: 'Organización', icono: <Network />, servicio: 'organizacion' },
      { ruta: '/admin/empleados', texto: 'Empleados', icono: <UserCog />, servicio: 'empleados' },
      { ruta: '/admin/modelos', texto: 'Modelos', icono: <Brain />, servicio: 'modelos' },
      { ruta: '/admin/registro', texto: 'Registro de actividad', icono: <ScrollText />, servicio: 'registro' },
      { ruta: '/admin/sistema', texto: 'Sistema', icono: <Server />, servicio: 'sistema' },
    ],
  },
]

export default function Marco({ ancho = false }: { ancho?: boolean }) {
  const { perfil, puede, salir } = useSesion()
  const [menu, setMenu] = useState(false)
  const [contadores, setContadores] = useState<Record<string, number>>({})
  const [servidorOk, setServidorOk] = useState(true)
  const lugar = useLocation()
  const navegar = useNavigate()

  useEffect(() => setMenu(false), [lugar.pathname])

  useEffect(() => {
    if (!perfil || perfil.invitado) return
    let vivo = true
    const pedir = () =>
      get<Record<string, number>>('/api/inicio/contadores')
        .then((c) => { if (vivo) { setContadores(c); setServidorOk(true) } })
        .catch((e) => { if (vivo && e?.estado === 0) setServidorOk(false) })
    pedir()
    const t = setInterval(pedir, 45000)
    return () => { vivo = false; clearInterval(t) }
  }, [perfil, lugar.pathname])

  if (!perfil) return null
  const grupos = NAVEGACION.map((g) => ({ ...g, enlaces: g.enlaces.filter((e) => !e.servicio || puede(e.servicio)) }))
    .filter((g) => g.enlaces.length)

  // Dentro de la app de escritorio la navegación la pone la barra lateral de la app.
  if (EMBEBIDA) {
    return (
      <div className="app embebida">
        <div className="principal">
          <main className={`contenido ${ancho ? 'ancho' : ''}`}><Outlet /></main>
        </div>
      </div>
    )
  }

  return (
    <div className={`app ${menu ? 'menu-abierto' : ''}`}>
      <aside className="lateral">
        <div className="lateral-marca">
          <LogoCidia />
          <div>
            <span className="marca-texto">CidIA</span>
            <span className="marca-sub">el conocimiento se queda</span>
          </div>
        </div>
        <nav className="lateral-nav">
          {grupos.map((g) => (
            <div key={g.titulo} className="lateral-grupo">
              <div className="lateral-grupo-titulo">{g.titulo}</div>
              {g.enlaces.map((e) => (
                <NavLink key={e.ruta} to={e.ruta} end={e.ruta === '/'} className={({ isActive }) => `lateral-enlace ${isActive ? 'activo' : ''}`}>
                  {e.icono}
                  <span>{e.texto}</span>
                  {e.contador && contadores[e.contador] ? <span className="contador">{contadores[e.contador]}</span> : null}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="lateral-pie">
          {perfil.invitado ? (
            <Boton variante="primario" bloque icono={<LogIn />} onClick={async () => { await salir(); navegar('/acceso') }}>
              Iniciar sesión
            </Boton>
          ) : (
            <div className="tarjeta-usuario">
              <NavLink to="/perfil" style={{ display: 'contents' }}><Avatar nombre={perfil.nombre} iniciales={perfil.iniciales} /></NavLink>
              <div className="crece">
                <NavLink to="/perfil" className="nombre recortar" style={{ display: 'block', color: '#fff' }}>{perfil.nombre}</NavLink>
                <div className="detalle">{NOMBRE_ROL[perfil.rol]}</div>
              </div>
              <Boton variante="fantasma" icono={<LogOut />} title="Cerrar sesión" style={{ color: '#9aa3ae' }}
                onClick={async () => { await salir(); navegar('/acceso') }} />
            </div>
          )}
          <div className="estado-servidor">
            <span className={`punto ${servidorOk ? '' : 'mal'}`} />
            {servidorOk ? 'Servidor de la empresa conectado' : 'Sin conexión con el servidor'}
          </div>
        </div>
      </aside>
      {menu && <div className="velo-menu" onClick={() => setMenu(false)} />}
      <div className="principal">
        <div className="barra-movil">
          <Boton variante="fantasma" icono={<Menu />} style={{ color: '#fff' }} onClick={() => setMenu(true)} aria-label="Menú" />
          <LogoCidia tamano={26} />
          <strong>CidIA</strong>
        </div>
        <main className={`contenido ${ancho ? 'ancho' : ''}`}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
