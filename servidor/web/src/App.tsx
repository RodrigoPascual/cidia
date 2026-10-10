// Rutas de la interfaz. Cada página vive en src/paginas y se carga bajo demanda.

import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Marco from './Marco'
import Acceso, { CambioObligatorio, PantallaCarga, SinConexion } from './paginas/Acceso'
import { BASE_APP } from './api'
import { useSesion } from './sesion'

// Cada página con el servicio que la abre: se cargan bajo demanda y, cuando el navegador está
// libre, se precargan las de la persona para que cambiar de sección sea inmediato.
const PAGINAS = {
  Inicio: ['perfil', () => import('./paginas/Inicio')],
  Copiloto: ['chat', () => import('./paginas/Copiloto')],
  Perfil: ['perfil', () => import('./paginas/Perfil')],
  PlantaTareas: ['planta', () => import('./paginas/planta/Tareas')],
  PlantaEjecucion: ['planta', () => import('./paginas/planta/Ejecucion')],
  Formacion: ['formacion', () => import('./paginas/formacion/Formacion')],
  FormacionTarea: ['formacion', () => import('./paginas/formacion/Tarea')],
  Evaluacion: ['evaluacion', () => import('./paginas/evaluacion/Evaluacion')],
  MiProgreso: ['progreso', () => import('./paginas/progreso/MiProgreso')],
  Equipo: ['equipo', () => import('./paginas/progreso/Equipo')],
  Aportaciones: ['aportaciones', () => import('./paginas/aportaciones/Aportaciones')],
  Validar: ['validar', () => import('./paginas/aportaciones/Validar')],
  Lagunas: ['lagunas', () => import('./paginas/aportaciones/Lagunas')],
  Espacio: ['espacio', () => import('./paginas/espacio/Espacio')],
  Captura: ['captura', () => import('./paginas/captura/Captura')],
  Entrevista: ['captura', () => import('./paginas/captura/Entrevista')],
  Instrucciones: ['instrucciones', () => import('./paginas/instrucciones/Instrucciones')],
  EditorInstruccion: ['instrucciones', () => import('./paginas/instrucciones/Editor')],
  Documentos: ['documentos', () => import('./paginas/documentos/Documentos')],
  Organizacion: ['organizacion', () => import('./paginas/admin/Organizacion')],
  Empleados: ['empleados', () => import('./paginas/admin/Empleados')],
  Modelos: ['modelos', () => import('./paginas/admin/Modelos')],
  Registro: ['registro', () => import('./paginas/admin/Registro')],
  Sistema: ['sistema', () => import('./paginas/admin/Sistema')],
} as const satisfies Record<string, readonly [string, () => Promise<unknown>]>

const Inicio = lazy(PAGINAS.Inicio[1])
const Copiloto = lazy(PAGINAS.Copiloto[1])
const Perfil = lazy(PAGINAS.Perfil[1])
const PlantaTareas = lazy(PAGINAS.PlantaTareas[1])
const PlantaEjecucion = lazy(PAGINAS.PlantaEjecucion[1])
const Formacion = lazy(PAGINAS.Formacion[1])
const FormacionTarea = lazy(PAGINAS.FormacionTarea[1])
const Evaluacion = lazy(PAGINAS.Evaluacion[1])
const MiProgreso = lazy(PAGINAS.MiProgreso[1])
const Equipo = lazy(PAGINAS.Equipo[1])
const Aportaciones = lazy(PAGINAS.Aportaciones[1])
const Validar = lazy(PAGINAS.Validar[1])
const Lagunas = lazy(PAGINAS.Lagunas[1])
const Espacio = lazy(PAGINAS.Espacio[1])
const Captura = lazy(PAGINAS.Captura[1])
const Entrevista = lazy(PAGINAS.Entrevista[1])
const Instrucciones = lazy(PAGINAS.Instrucciones[1])
const EditorInstruccion = lazy(PAGINAS.EditorInstruccion[1])
const Documentos = lazy(PAGINAS.Documentos[1])
const Organizacion = lazy(PAGINAS.Organizacion[1])
const Empleados = lazy(PAGINAS.Empleados[1])
const Modelos = lazy(PAGINAS.Modelos[1])
const Registro = lazy(PAGINAS.Registro[1])
const Sistema = lazy(PAGINAS.Sistema[1])

function Protegida({ servicio, children }: { servicio?: string; children: ReactNode }) {
  const { perfil, puede } = useSesion()
  const lugar = useLocation()
  if (!perfil) return <Navigate to="/acceso" state={{ desde: lugar.pathname + lugar.search }} replace />
  if (servicio && !puede(servicio)) {
    return <Navigate to={perfil.invitado ? '/copiloto' : '/'} replace />
  }
  return <>{children}</>
}

/** Precarga en segundo plano las páginas que puede abrir la persona (una vez por sesión). */
function usePrecarga(servicios: readonly string[] | undefined) {
  useEffect(() => {
    if (!servicios?.length) return
    const quiere = new Set(servicios)
    const cargas = Object.values(PAGINAS).filter(([s]) => quiere.has(s)).map(([, cargar]) => cargar)
    let cancelado = false
    const ocioso = (f: () => void) =>
      typeof window.requestIdleCallback === 'function' ? window.requestIdleCallback(f, { timeout: 4000 }) : setTimeout(f, 1500)
    const siguiente = () => {
      const c = cargas.shift()
      if (!c || cancelado) return
      c().catch(() => { /* se volverá a pedir al navegar */ }).finally(() => ocioso(siguiente))
    }
    const t = window.setTimeout(() => ocioso(siguiente), 2500)
    return () => { cancelado = true; window.clearTimeout(t) }
  }, [servicios?.join(',')])  // eslint-disable-line react-hooks/exhaustive-deps
}

function Rutas() {
  const { perfil, cargando, sinConexion, puede } = useSesion()
  usePrecarga(perfil?.servicios)
  if (cargando) return <PantallaCarga />
  // Hay sesión guardada pero el servidor no responde: se espera sin cerrar la sesión.
  if (!perfil && sinConexion) return <SinConexion />
  // Contraseña inicial o temporal: hay que cambiarla antes de usar nada (después se sigue en la
  // misma dirección que se había pedido).
  if (perfil?.debe_cambiar_contrasena) return <CambioObligatorio />
  const p = (servicio: string | undefined, el: ReactNode) => <Protegida servicio={servicio}>{el}</Protegida>
  return (
    <Suspense fallback={<PantallaCarga />}>
      <Routes>
        <Route path="/acceso" element={perfil && !perfil.invitado ? <Navigate to="/" replace /> : <Acceso />} />
        {/* Modo planta: pantalla completa, sin barra lateral */}
        <Route path="/planta/ejecucion/:id" element={p('planta', <PlantaEjecucion />)} />
        <Route element={p(undefined, <Marco />)}>
          <Route index element={perfil?.invitado ? <Navigate to="/copiloto" replace /> : p('perfil', <Inicio />)} />
          <Route path="copiloto" element={p('chat', <Copiloto />)} />
          <Route path="perfil" element={p('perfil', <Perfil />)} />
          <Route path="planta" element={p('planta', <PlantaTareas />)} />
          <Route path="formacion" element={p('formacion', <Formacion />)} />
          <Route path="formacion/tarea/:id" element={p('formacion', <FormacionTarea />)} />
          <Route path="evaluacion" element={p('evaluacion', <Evaluacion />)} />
          <Route path="progreso" element={p('progreso', <MiProgreso />)} />
          <Route path="equipo" element={p('equipo', <Equipo />)} />
          <Route path="aportaciones" element={p('aportaciones', <Aportaciones />)} />
          <Route path="validar" element={p('validar', <Validar />)} />
          <Route path="lagunas" element={p('lagunas', <Lagunas />)} />
          <Route path="espacio" element={p('espacio', <Espacio />)} />
          <Route path="captura" element={p('captura', <Captura />)} />
          <Route path="captura/entrevista/:id" element={p('captura', <Entrevista />)} />
          <Route path="instrucciones" element={p('instrucciones', <Instrucciones />)} />
          <Route path="instrucciones/:id" element={p('instrucciones', <EditorInstruccion />)} />
          <Route path="documentos" element={p('documentos', <Documentos />)} />
          <Route path="admin/organizacion" element={p('organizacion', <Organizacion />)} />
          <Route path="admin/empleados" element={p(puede('empleados') ? 'empleados' : 'equipo', <Empleados />)} />
          <Route path="admin/modelos" element={p('modelos', <Modelos />)} />
          <Route path="admin/registro" element={p('registro', <Registro />)} />
          <Route path="admin/sistema" element={p('sistema', <Sistema />)} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <BrowserRouter basename={BASE_APP} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Rutas />
    </BrowserRouter>
  )
}
