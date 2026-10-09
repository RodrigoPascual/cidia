// Sesión del usuario: perfil, inicio de sesión, modo invitado y puente con la app de escritorio.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { get, guardarToken, post, siSesionCaduca, token } from './api'

export interface Perfil {
  invitado: boolean
  id?: number
  usuario?: string
  nombre: string
  iniciales: string
  rol: 'invitado' | 'empleado' | 'jefe' | 'admin'
  es_experto?: boolean
  memoria_activa?: boolean
  servicios: string[]
  puesto?: string | null
  departamento?: { id: number; nombre: string } | null
  nivel?: { orden: number; nombre: string } | null
  formaciones?: { id: number; departamento: string; puesto: string | null }[]
}

interface ContextoSesion {
  perfil: Perfil | null
  cargando: boolean
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
    window.parent.postMessage({ tipo: 'cidia:sesion', token: t, perfil }, '*')
  } catch {
    /* sin app anfitriona */
  }
}

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [cargando, setCargando] = useState(true)

  const recargar = useCallback(async () => {
    if (!token()) {
      setPerfil(null)
      setCargando(false)
      return
    }
    try {
      const p = await get<Perfil>('/api/auth/yo')
      setPerfil(p)
      avisarApp(token(), p)
    } catch {
      guardarToken(null)
      setPerfil(null)
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
    siSesionCaduca(() => {
      guardarToken(null)
      setPerfil(null)
      avisarApp(null, null)
    })
    recargar()
    return () => window.removeEventListener('message', alMensaje)
  }, [recargar])

  const iniciar = useCallback(async (usuario: string, contrasena: string) => {
    const r = await post<{ token: string; perfil: Perfil }>('/api/auth/login', { usuario, contrasena })
    guardarToken(r.token)
    setPerfil(r.perfil)
    avisarApp(r.token, r.perfil)
  }, [])

  const entrarComoInvitado = useCallback(async () => {
    const r = await post<{ token: string; perfil: Perfil }>('/api/auth/invitado')
    guardarToken(r.token)
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
    setPerfil(null)
    avisarApp(null, null)
  }, [])

  const puede = useCallback((s: string) => !!perfil?.servicios.includes(s), [perfil])

  const valor = useMemo(
    () => ({ perfil, cargando, iniciar, entrarComoInvitado, salir, recargar, puede }),
    [perfil, cargando, iniciar, entrarComoInvitado, salir, recargar, puede],
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
