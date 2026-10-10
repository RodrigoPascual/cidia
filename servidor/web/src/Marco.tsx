// Estructura común: barra lateral con la navegación según los servicios de cada persona,
// barra superior en el móvil y, dentro de la app de escritorio (?embed=1), solo el contenido.

import { Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { matchPath, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Brain, ClipboardCheck, FileText, FolderOpen, GraduationCap, HelpCircle, Home, Inbox, Lightbulb, ListChecks,
  LogIn, LogOut, Menu, MessageSquare, Network, ScrollText, Server, TrendingUp, UserCog, Users, Video, Wrench, X,
} from 'lucide-react'
import { BASE_APP, EMBEBIDA, ErrorApi, get } from './api'
import { NOMBRE_ROL, useSesion } from './sesion'
import { Avatar, Boton, EsqueletoPagina, LogoCidia } from './ui'

interface Enlace {
  ruta: string; texto: string; icono: ReactNode; servicio: string | null
  contador?: string; tonoContador?: 'alerta'
}
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
      { ruta: '/lagunas', texto: 'Lagunas', icono: <HelpCircle />, servicio: 'lagunas', contador: 'lagunas', tonoContador: 'alerta' },
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

const TODOS = NAVEGACION.flatMap((g) => g.enlaces)

/** Avisa a la barra lateral de que algo ha cambiado. Tras un POST/PUT/PATCH/DELETE ya se hace solo. */
export { refrescarContadores } from './api'

/** Enlace de la navegación que corresponde a una ruta (el más específico). */
function enlaceDe(ruta: string): Enlace | undefined {
  if (ruta === '/' || ruta === '') return TODOS[0]
  return TODOS.filter((e) => e.ruta !== '/' && matchPath({ path: e.ruta, end: false }, ruta))
    .sort((a, b) => b.ruta.length - a.ruta.length)[0]
}

const TITULOS_EXTRA: Record<string, string> = { '/perfil': 'Mi perfil' }

/** Cada cuánto se piden los contadores como mucho al navegar (la barra no necesita más). */
const MIN_ENTRE_CONTADORES = 15_000
const CADA_CONTADORES = 60_000

function esCaida(e: unknown) {
  return e instanceof ErrorApi && (e.estado === 0 || e.estado >= 502)
}

export default function Marco({ ancho = false }: { ancho?: boolean }) {
  const { perfil, puede, salir } = useSesion()
  const [menu, setMenu] = useState(false)
  const [contadores, setContadores] = useState<Record<string, number>>({})
  const [servidorOk, setServidorOk] = useState(true)
  const lugar = useLocation()
  const navegar = useNavigate()
  const ultimaPeticion = useRef(0)
  const botonMenu = useRef<HTMLButtonElement>(null)

  // ---------------------------------------------------------------- navegación
  useEffect(() => {
    setMenu(false)
    // Cada página empieza arriba (el navegador conserva el desplazamiento entre rutas de la SPA).
    window.scrollTo({ top: 0 })
    // Con muchas secciones la barra lateral se desplaza: la sección actual queda siempre a la vista.
    requestAnimationFrame(() => document.querySelector('.lateral-nav .lateral-enlace.activo')?.scrollIntoView({ block: 'nearest' }))
  }, [lugar.pathname])

  useEffect(() => {
    const e = enlaceDe(lugar.pathname)
    const texto = TITULOS_EXTRA[lugar.pathname] ?? e?.texto
    document.title = texto && texto !== 'Inicio' ? `${texto} · CidIA` : 'CidIA'
  }, [lugar.pathname])

  // Menú del móvil: recibe el foco, Escape lo cierra y el fondo no se desplaza mientras está abierto.
  useEffect(() => {
    if (!menu) return
    requestAnimationFrame(() => document.querySelector<HTMLElement>('.lateral .cerrar-menu')?.focus())
    document.body.classList.add('sin-desplazamiento')
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') { setMenu(false); botonMenu.current?.focus() } }
    window.addEventListener('keydown', tecla)
    return () => { document.body.classList.remove('sin-desplazamiento'); window.removeEventListener('keydown', tecla) }
  }, [menu])

  // ---------------------------------------------------------------- contadores y estado del servidor
  const pedir = useCallback(async (forzar = false) => {
    if (!perfil) return
    const ahora = Date.now()
    if (!forzar && ahora - ultimaPeticion.current < MIN_ENTRE_CONTADORES) return
    ultimaPeticion.current = ahora
    try {
      if (perfil.invitado) await get('/salud')
      else setContadores(await get<Record<string, number>>('/api/inicio/contadores'))
      setServidorOk(true)
    } catch (e) {
      if (esCaida(e)) setServidorOk(false)
    }
  }, [perfil])

  useEffect(() => { void pedir() }, [pedir, lugar.pathname])
  useEffect(() => {
    const forzar = () => void pedir(true)
    const alVolver = () => { if (document.visibilityState === 'visible') void pedir() }
    window.addEventListener('cidia:contadores', forzar)
    window.addEventListener('online', forzar)
    document.addEventListener('visibilitychange', alVolver)
    // Sin conexión se comprueba más a menudo para que el aviso desaparezca en cuanto vuelva.
    const t = setInterval(() => void pedir(true), servidorOk ? CADA_CONTADORES : 10_000)
    return () => {
      window.removeEventListener('cidia:contadores', forzar)
      window.removeEventListener('online', forzar)
      document.removeEventListener('visibilitychange', alVolver)
      clearInterval(t)
    }
  }, [pedir, servidorOk])

  if (!perfil) return null
  const grupos = NAVEGACION.map((g) => ({ ...g, enlaces: g.enlaces.filter((e) => !e.servicio || puede(e.servicio)) }))
    .filter((g) => g.enlaces.length)
  const actual = enlaceDe(lugar.pathname)
  const tituloActual = TITULOS_EXTRA[lugar.pathname] ?? actual?.texto ?? 'CidIA'
  const cerrarSesion = async () => { await salir(); navegar('/acceso') }
  const rol = `${NOMBRE_ROL[perfil.rol] ?? ''}${perfil.es_experto && perfil.rol === 'empleado' ? ' · Experto' : ''}`

  const contenido = (
    <main id="contenido" className={`contenido ${ancho ? 'ancho' : ''}`} tabIndex={-1}>
      {!servidorOk && (
        <div className="aviso-conexion" role="alert">
          <span className="punto mal" /> Sin conexión con el servidor de la empresa. Lo que veas puede no estar al día; se reintenta solo.
        </div>
      )}
      <Suspense fallback={<EsqueletoPagina />}>
        <Outlet />
      </Suspense>
    </main>
  )

  // Dentro de la app de escritorio la navegación la pone la barra lateral de la app.
  if (EMBEBIDA) {
    return (
      <div className="app embebida">
        <div className="principal">
          <BarraEmbebida />
          {contenido}
        </div>
      </div>
    )
  }

  return (
    <div className={`app ${menu ? 'menu-abierto' : ''}`}>
      <a className="saltar" href="#contenido">Saltar al contenido</a>
      <aside className="lateral" id="menu-lateral" aria-label="Navegación principal">
        <div className="lateral-marca">
          <LogoCidia />
          <div className="crece">
            <span className="marca-texto">CidIA</span>
            <span className="marca-sub">el conocimiento se queda</span>
          </div>
          <Boton variante="fantasma" className="cerrar-menu" icono={<X />} aria-label="Cerrar el menú" onClick={() => setMenu(false)} />
        </div>
        <nav className="lateral-nav">
          {grupos.map((g) => (
            <div key={g.titulo} className="lateral-grupo" role="group" aria-label={g.titulo}>
              <div className="lateral-grupo-titulo" aria-hidden="true">{g.titulo}</div>
              {g.enlaces.map((e) => {
                const n = e.contador ? contadores[e.contador] : 0
                return (
                  <NavLink key={e.ruta} to={e.ruta} end={e.ruta === '/'}
                    className={({ isActive }) => `lateral-enlace ${isActive ? 'activo' : ''}`}>
                    {e.icono}
                    <span className="crece recortar">{e.texto}</span>
                    {n ? <span className={`contador ${e.tonoContador ?? ''}`} aria-label={`${n} pendientes`}>{n > 99 ? '99+' : n}</span> : null}
                  </NavLink>
                )
              })}
            </div>
          ))}
        </nav>
        <div className="lateral-pie">
          {perfil.invitado ? (
            <Boton variante="primario" bloque icono={<LogIn />} onClick={cerrarSesion}>
              Iniciar sesión
            </Boton>
          ) : (
            <div className="tarjeta-usuario">
              <NavLink to="/perfil" className="usuario-enlace" title="Mi perfil">
                <Avatar nombre={perfil.nombre} iniciales={perfil.iniciales} />
                <span className="crece">
                  <span className="nombre recortar">{perfil.nombre}</span>
                  {/* La cuenta «Administración» no repite su rol debajo del nombre. */}
                  {rol !== perfil.nombre && <span className="detalle recortar">{rol}</span>}
                </span>
              </NavLink>
              <Boton variante="fantasma" className="boton-salir" icono={<LogOut />} title="Cerrar sesión" onClick={cerrarSesion} />
            </div>
          )}
          <div className={`estado-servidor ${servidorOk ? '' : 'mal'}`} role="status">
            <span className={`punto ${servidorOk ? '' : 'mal'}`} />
            {servidorOk ? 'Servidor de la empresa conectado' : 'Sin conexión con el servidor'}
          </div>
        </div>
      </aside>
      {menu && <div className="velo-menu" onClick={() => setMenu(false)} />}
      <div className="principal">
        <header className="barra-movil">
          <Boton ref={botonMenu} variante="fantasma" icono={<Menu />} onClick={() => setMenu(true)}
            aria-label="Abrir el menú" aria-expanded={menu} aria-controls="menu-lateral" />
          <LogoCidia tamano={26} />
          <span className="barra-movil-titulo recortar">{tituloActual}</span>
          {!servidorOk && <span className="punto mal" title="Sin conexión con el servidor" />}
          {!perfil.invitado && (
            <NavLink to="/perfil" aria-label="Mi perfil" className="barra-movil-usuario">
              <Avatar nombre={perfil.nombre} iniciales={perfil.iniciales} tamano="p" />
            </NavLink>
          )}
        </header>
        {contenido}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ modo embebido

const SECCIONES_ADMIN = TODOS.filter((e) => e.ruta.startsWith('/admin/'))

/** Primera ruta que se abrió en el marco: si la persona navega a otra sección, se ofrece volver. */
const rutaEntrada = window.location.pathname.slice(BASE_APP.length) || '/'

/**
 * En la app de escritorio cada panel es un iframe sin la barra lateral de CidIA. Aquí van:
 * las pestañas de las secciones de administración (el panel «Administración» abre solo la
 * primera) y un «Volver» cuando desde un panel se ha saltado a otra sección.
 */
function BarraEmbebida() {
  const { puede } = useSesion()
  const lugar = useLocation()
  const navegar = useNavigate()
  const enAdmin = lugar.pathname.startsWith('/admin/')
  const seccion = (r: string) => (r.startsWith('/admin/') ? '/admin' : '/' + (r.split('/')[1] ?? ''))
  const fuera = seccion(lugar.pathname) !== seccion(rutaEntrada)
  const admin = SECCIONES_ADMIN.filter((e) => e.servicio && puede(e.servicio))
  if (!fuera && !(enAdmin && admin.length > 1)) return null
  return (
    <div className="barra-embebida">
      {fuera && (
        <Boton variante="fantasma" tamano="pequeno" icono={<ArrowLeft />} onClick={() => navegar(rutaEntrada)}>
          Volver a {enlaceDe(rutaEntrada)?.texto ?? 'la sección'}
        </Boton>
      )}
      {enAdmin && admin.length > 1 && (
        <nav className="subnav" aria-label="Secciones de administración">
          {admin.map((e) => (
            <NavLink key={e.ruta} to={e.ruta} className={({ isActive }) => `subnav-enlace ${isActive ? 'activo' : ''}`}>
              {e.icono}{e.texto}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}
