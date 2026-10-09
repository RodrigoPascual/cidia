// Documentos: biblioteca de conocimiento de jefes y administración, y consola de búsqueda.
//
// · Biblioteca: subir (varios ficheros), etiquetar quién lo encuentra, reindexar y borrar.
// · Probar búsqueda: qué fragmentos encuentra una pregunta y con qué puntuación.
// Los permisos se comprueban siempre en el servidor; aquí solo se adapta lo que se muestra.

import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Database, Library, ScanSearch, Upload } from 'lucide-react'
import { get } from '../../api'
import { Boton, Cabecera, Cargando, ErrorCarga, Etiqueta, Pestanas, useDatos } from '../../ui'
import { useAccionesDocumento } from './acciones'
import Biblioteca from './Biblioteca'
import DetalleDocumento from './DetalleDocumento'
import PanelSubida from './PanelSubida'
import ProbarBusqueda from './ProbarBusqueda'
import type { Documento, Opciones } from './tipos'
import './documentos.css'

type Vista = 'biblioteca' | 'buscar'

export default function Documentos() {
  const [params, setParams] = useSearchParams()
  const vista: Vista = params.get('vista') === 'buscar' ? 'buscar' : 'biblioteca'
  const [subiendo, setSubiendo] = useState(false)
  const [abierto, setAbierto] = useState<number | null>(null)
  const [version, setVersion] = useState(0)
  const { datos: opciones, error, recargar } = useDatos<Opciones>((s) => get<Opciones>('/api/documentos/opciones', s))

  const refrescar = useCallback(() => setVersion((v) => v + 1), [])
  const alCambiar = useCallback((d: Documento, borrado?: boolean) => {
    if (borrado) setAbierto((a) => (a === d.id ? null : a))
    refrescar()
  }, [refrescar])
  const { acciones, dialogos } = useAccionesDocumento(opciones, alCambiar)

  const cambiarVista = (v: Vista) => setParams(v === 'buscar' ? { vista: 'buscar' } : {}, { replace: true })

  return (
    <>
      <Cabecera
        antetitulo={<><Library size={14} /> Conocimiento</>}
        titulo="Documentos"
        subtitulo={opciones?.es_admin
          ? 'Todo el conocimiento que puede citar el copiloto. Decide quién encuentra cada documento por departamento, nivel, formación o como público.'
          : 'El conocimiento de tu departamento que puede citar el copiloto. Decide quién lo encuentra por nivel, formación o como público.'}
        acciones={<>
          {opciones?.motor === 'weknora' && <Etiqueta tono="azul" icono={<Database />}>Motor WeKnora</Etiqueta>}
          <Boton variante="primario" icono={<Upload />} disabled={!opciones} onClick={() => setSubiendo(true)}>
            Subir conocimiento
          </Boton>
        </>}
      />

      <Pestanas<Vista>
        activa={vista} onCambio={cambiarVista}
        pestanas={[
          { id: 'biblioteca', texto: 'Biblioteca', icono: <Library size={16} /> },
          { id: 'buscar', texto: 'Probar búsqueda', icono: <ScanSearch size={16} /> },
        ]}
      />

      {error && !opciones ? (
        <ErrorCarga error={error} reintentar={recargar} />
      ) : !opciones ? (
        <Cargando />
      ) : vista === 'biblioteca' ? (
        <Biblioteca opciones={opciones} version={version} acciones={acciones} onAbrir={setAbierto} onSubir={() => setSubiendo(true)} />
      ) : (
        <ProbarBusqueda opciones={opciones} onAbrir={setAbierto} />
      )}

      {opciones && (
        <PanelSubida
          abierto={subiendo} opciones={opciones} onCerrar={() => setSubiendo(false)}
          onSubido={() => { refrescar(); if (vista !== 'biblioteca') cambiarVista('biblioteca') }}
        />
      )}
      <DetalleDocumento documentoId={abierto} version={version} acciones={acciones} onCerrar={() => setAbierto(null)} />
      {dialogos}
    </>
  )
}
