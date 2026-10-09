// Rutas de la interfaz. Cada página vive en src/paginas y se carga bajo demanda.

import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Marco from './Marco'
import Acceso from './paginas/Acceso'
import { BASE_APP } from './api'
import { useSesion } from './sesion'
import { Cargando } from './ui'

const Inicio = lazy(() => import('./paginas/Inicio'))
const Copiloto = lazy(() => import('./paginas/Copiloto'))
const Perfil = lazy(() => import('./paginas/Perfil'))
const PlantaTareas = lazy(() => import('./paginas/planta/Tareas'))
const PlantaEjecucion = lazy(() => import('./paginas/planta/Ejecucion'))
const Formacion = lazy(() => import('./paginas/formacion/Formacion'))
const FormacionTarea = lazy(() => import('./paginas/formacion/Tarea'))
const Evaluacion = lazy(() => import('./paginas/evaluacion/Evaluacion'))
const MiProgreso = lazy(() => import('./paginas/progreso/MiProgreso'))
const Equipo = lazy(() => import('./paginas/progreso/Equipo'))
const Aportaciones = lazy(() => import('./paginas/aportaciones/Aportaciones'))
const Validar = lazy(() => import('./paginas/aportaciones/Validar'))
const Lagunas = lazy(() => import('./paginas/aportaciones/Lagunas'))
const Espacio = lazy(() => import('./paginas/espacio/Espacio'))
const Captura = lazy(() => import('./paginas/captura/Captura'))
const Entrevista = lazy(() => import('./paginas/captura/Entrevista'))
const Instrucciones = lazy(() => import('./paginas/instrucciones/Instrucciones'))
const EditorInstruccion = lazy(() => import('./paginas/instrucciones/Editor'))
const Documentos = lazy(() => import('./paginas/documentos/Documentos'))
const Organizacion = lazy(() => import('./paginas/admin/Organizacion'))
const Empleados = lazy(() => import('./paginas/admin/Empleados'))
const Modelos = lazy(() => import('./paginas/admin/Modelos'))
const Registro = lazy(() => import('./paginas/admin/Registro'))
const Sistema = lazy(() => import('./paginas/admin/Sistema'))

function Protegida({ servicio, children }: { servicio?: string; children: ReactNode }) {
  const { perfil, puede } = useSesion()
  const lugar = useLocation()
  if (!perfil) return <Navigate to="/acceso" state={{ desde: lugar.pathname }} replace />
  if (servicio && !puede(servicio)) {
    return <Navigate to={perfil.invitado ? '/copiloto' : '/'} replace />
  }
  return <>{children}</>
}

function Rutas() {
  const { perfil, cargando, puede } = useSesion()
  if (cargando) return <Cargando texto="Conectando con CidIA…" />
  const p = (servicio: string | undefined, el: ReactNode) => <Protegida servicio={servicio}>{el}</Protegida>
  return (
    <Suspense fallback={<Cargando />}>
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
