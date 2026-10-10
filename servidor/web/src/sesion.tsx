// Sesión del usuario: perfil, inicio de sesión, modo invitado y puente con la app de escritorio.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ErrorApi, get, guardarToken, post, siSesionCaduca, token } from './api'

export interface Perfil {
  invitado: boolean
  id?: number
  usuario?: string
  nombre: string
  iniciales: string
  rol: 'invitado' | 'empleado' | 'jefe' | 'admin'
  es_experto?: boolean
  memoria_activa?: boolean
  /** Entró con una contraseña inicial o temporal: hay que cambiarla antes de seguir. */
  debe_cambiar_contrasena?: boolean
  servicios: string[]
  puesto?: string | null
  departamento?: { id: number; nombre: string } | null
  nivel?: { orden: number; nombre: string } | null
  formaciones?: { id: number; departamento: string; puesto: string | null }[]
}

interface ContextoSesion {
  perfil: Perfil | null
  cargando: boolean
  /** Hay sesión guardada pero el servidor no responde: no se cierra la sesión, se reintenta. */
  sinConexion: boolean
  /** Por qué se ha vuelto a la pantalla de acceso (la sesión caducó o se cerró en otro sitio). */
  motivoSalida: string | null
  iniciar: (usuario: string, contrasena: string) => Promise<void>
  entrarComoInvitado: () => Promise<void>
  salir: () => Promise<void>
  recargar: () => Promise<void>
  puede: (servicio: string) => boolean
}

const Contexto = createContext<ContextoSesion | null>(null)

/** Avisa a la app de escritorio (plugin CidIA) de la sesión, si la interfaz va embebida. */
function avisarApp(t: string | null, perfil: Perfil | null) {
  if (window.parent === window) return
  try {
    window.parent.postMessage({ tipo: 'cidia:sesion', token: t, perfil }, window.location.origin)
  } catch {
    /* sin app anfitriona */
  }
}

// El último perfil se guarda junto a su sesión para pintar la interfaz al instante al abrirla (cada
// panel de la app de escritorio es una carga nueva) mientras se comprueba en segundo plano.
const CLAVE_PERFIL = 'cidia.perfil'
const firma = (t: string) => t.slice(-32)

function perfilGuardado(t: string | null): Perfil | null {
  if (!t) return null
  try {
    const g = JSON.parse(localStorage.getItem(CLAVE_PERFIL) ?? 'null') as { firma: string; perfil: Perfil } | null
    return g && g.firma === firma(t) ? g.perfil : null
  } catch {
    return null
  }
}

function guardarPerfil(t: string | null, p: Perfil | null) {
  try {
    if (t && p) localStorage.setItem(CLAVE_PERFIL, JSON.stringify({ firma: firma(t), perfil: p }))
    else localStorage.removeItem(CLAVE_PERFIL)
  } catch {
    /* almacenamiento no disponible */
  }
}

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [cargando, setCargando] = useState(true)
  const [sinConexion, setSinConexion] = useState(false)
  const [motivoSalida, setMotivoSalida] = useState<string | null>(null)
  const perfilActual = useRef<Perfil | null>(null)
  perfilActual.current = perfil

  const recargar = useCallback(async () => {
    if (!token()) {
      setPerfil(null)
      setCargando(false)
      return
    }
    try {
      const p = await get<Perfil>('/api/auth/yo')
      setPerfil(p)
      setSinConexion(false)
      guardarPerfil(token(), p)
      avisarApp(token(), p)
    } catch (e) {
      // Solo un 401 quiere decir que la sesión ya no vale. Si el servidor no responde, la sesión
      // se conserva y la interfaz muestra que no hay conexión (y vuelve a intentarlo).
      if (e instanceof ErrorApi && e.estado === 401) {
        guardarToken(null)
        guardarPerfil(null, null)
        setPerfil(null)
        setSinConexion(false)
      } else {
        setSinConexion(true)
      }
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    // La app de escritorio puede pasar un token ya obtenido (inicio de sesión desde el plugin).
    const alMensaje = (e: MessageEvent) => {
      const d = e.data
      if (d && d.tipo === 'cidia:token' && typeof d.token === 'string') {
        guardarToken(d.token)
        recargar()
      }
    }
    window.addEventListener('message', alMensaje)
    const hash = new URLSearchParams(window.location.hash.slice(1))
    const t = hash.get('token')
    if (t) {
      guardarToken(t)
      history.replaceState(null, '', window.location.pathname + window.location.search)
    }
    const previo = perfilGuardado(token())
    if (previo) {
      setPerfil(previo)
      setCargando(false)
    }
    siSesionCaduca(() => {
      guardarToken(null)
      guardarPerfil(null, null)
      if (perfilActual.current && !perfilActual.current.invitado) {
        setMotivoSalida('Tu sesión ha terminado. Vuelve a iniciar sesión para seguir donde estabas.')
      }
      setPerfil(null)
      avisarApp(null, null)
    })
    recargar()
    return () => window.removeEventListener('message', alMensaje)
  }, [recargar])

  const iniciar = useCallback(async (usuario: string, contrasena: string) => {
    const r = await post<{ token: string; perfil: Perfil }>('/api/auth/login', { usuario, contrasena })
    guardarToken(r.token)
    guardarPerfil(r.token, r.perfil)
    setMotivoSalida(null)
    setPerfil(r.perfil)
    avisarApp(r.token, r.perfil)
  }, [])

  const entrarComoInvitado = useCallback(async () => {
    const r = await post<{ token: string; perfil: Perfil }>('/api/auth/invitado')
    guardarToken(r.token)
    guardarPerfil(r.token, r.perfil)
    setMotivoSalida(null)
    setPerfil(r.perfil)
    avisarApp(r.token, r.perfil)
  }, [])

  const salir = useCallback(async () => {
    try {
      await post('/api/auth/salir')
    } catch {
      /* ya no era válida */
    }
    guardarToken(null)
    guardarPerfil(null, null)
    setPerfil(null)
    setSinConexion(false)
    setMotivoSalida(null)
    avisarApp(null, null)
  }, [])

  const puede = useCallback((s: string) => !!perfil?.servicios.includes(s), [perfil])

  const valor = useMemo(
    () => ({ perfil, cargando, sinConexion, motivoSalida, iniciar, entrarComoInvitado, salir, recargar, puede }),
    [perfil, cargando, sinConexion, motivoSalida, iniciar, entrarComoInvitado, salir, recargar, puede],
  )
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

export function useSesion(): ContextoSesion {
  const c = useContext(Contexto)
  if (!c) throw new Error('useSesion fuera de ProveedorSesion')
  return c
}

export const NOMBRE_ROL: Record<string, string> = {
  invitado: 'Sin sesión',
  empleado: 'Empleado',
  jefe: 'Jefe de equipo',
  admin: 'Administración',
}
