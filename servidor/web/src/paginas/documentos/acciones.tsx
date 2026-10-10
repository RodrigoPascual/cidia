// Acciones sobre un documento (editar, reindexar, borrar) compartidas por la tabla y el detalle.

import { useCallback, useState } from 'react'
import { del, post } from '../../api'
import { useAvisarError, useAvisos, useConfirmar } from '../../ui'
import EditarDocumento from './EditarDocumento'
import type { Documento, Opciones } from './tipos'

export interface AccionesDocumento {
  editar: (d: Documento) => void
  reindexar: (d: Documento) => Promise<void>
  borrar: (d: Documento) => Promise<void>
  ocupado: number | null
}

/** `alCambiar(d, borrado)` se llama tras cada cambio para recargar lo que haga falta. */
export function useAccionesDocumento(opciones: Opciones | null, alCambiar: (d: Documento, borrado?: boolean) => void) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const [editando, setEditando] = useState<Documento | null>(null)
  const [ocupado, setOcupado] = useState<number | null>(null)

  const reindexar = useCallback(async (d: Documento) => {
    setOcupado(d.id)
    try {
      const nuevo = await post<Documento>(`/api/documentos/${d.id}/reindexar`)
      avisar(nuevo.estado === 'listo' ? 'Documento reindexado.' : 'Reindexando el documento. Tardará unos segundos.')
      alCambiar(nuevo)
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }, [avisar, avisarError, alCambiar])

  const borrar = useCallback(async (d: Documento) => {
    // (Las instrucciones no se borran desde aquí: se gestionan desde Instrucciones.)
    const nacido = d.origen === 'aportacion'
      ? ' Nació de una aportación validada: el copiloto dejará de citarla.'
      : d.estado === 'borrador'
        ? ' Es una ficha sin publicar: su autor ya no podrá revisarla ni publicarla.'
        : ''
    const ok = await confirmar(
      'Borrar documento',
      <>¿Seguro que quieres borrar «{d.titulo}»? El copiloto dejará de encontrarlo{d.nombre_fichero ? ' y se borrará el fichero original' : ''}.{nacido} No se puede deshacer.</>,
      true,
    )
    if (!ok) return
    setOcupado(d.id)
    try {
      await del(`/api/documentos/${d.id}`)
      avisar('Documento borrado.')
      alCambiar(d, true)
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }, [confirmar, avisar, avisarError, alCambiar])

  const dialogos = (
    <>
      {dialogo}
      {opciones && editando && (
        <EditarDocumento
          documento={editando} opciones={opciones} onCerrar={() => setEditando(null)}
          onGuardado={(d) => { setEditando(null); alCambiar(d) }}
        />
      )}
    </>
  )

  const acciones: AccionesDocumento = { editar: setEditando, reindexar, borrar, ocupado }
  return { acciones, dialogos }
}
