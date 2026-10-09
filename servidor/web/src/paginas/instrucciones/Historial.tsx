// Historial de versiones de una tarea y comparación de cada versión con la anterior.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, GitCompare, History } from 'lucide-react'
import { fecha, get, urlServidor } from '../../api'
import { Boton, Cargando, ErrorCarga, Etiqueta, Modal, useDatos } from '../../ui'
import { ESTADOS, type CambioCampo, type CambioPaso, type Diferencias, type Version } from './tipos'

const TIPOS: Record<CambioPaso['tipo'], { texto: string; tono: 'verde' | 'roja' | 'amarilla' | 'azul' }> = {
  nuevo: { texto: 'Nuevo', tono: 'verde' },
  eliminado: { texto: 'Eliminado', tono: 'roja' },
  modificado: { texto: 'Modificado', tono: 'amarilla' },
  movido: { texto: 'Movido', tono: 'azul' },
}

export default function Historial({ instruccionId, abierto, onCerrar, onAbrir }: {
  instruccionId: number; abierto: boolean; onCerrar: () => void
  /** Abre otra versión (el editor lo usa para avisar si hay cambios sin guardar). */
  onAbrir?: (id: number) => void
}) {
  const navegar = useNavigate()
  const versiones = useDatos((s) => (abierto ? get<Version[]>(`/api/instrucciones/${instruccionId}/versiones`, s)
    : Promise.resolve(null)), [instruccionId, abierto])
  const [comparando, setComparando] = useState<number | null>(null)

  useEffect(() => setComparando(null), [instruccionId, abierto])

  return (
    <Modal abierto={abierto} titulo={<span className="fila"><History size={20} />Historial de versiones</span>} onCerrar={onCerrar} ancho>
      {versiones.error ? <ErrorCarga error={versiones.error} reintentar={versiones.recargar} />
        : !versiones.datos ? <Cargando /> : (
          <div className="ins-historial">
            {versiones.datos.map((v, i) => {
              const anterior = versiones.datos![i + 1]
              return (
                <div key={v.id} className={`ins-version-fila ${v.actual ? 'actual' : ''}`}>
                  <div className="fila envolver">
                    <span className="ins-version-grande">v{v.version}</span>
                    <Etiqueta tono={ESTADOS[v.estado].tono}>{ESTADOS[v.estado].texto}</Etiqueta>
                    {v.actual && <Etiqueta>Esta versión</Etiqueta>}
                    <span className="crece" />
                    {anterior && (
                      <Boton tamano="pequeno" icono={<GitCompare />} onClick={() => setComparando(comparando === v.id ? null : v.id)}>
                        {comparando === v.id ? 'Ocultar cambios' : `Cambios desde v${anterior.version}`}
                      </Boton>
                    )}
                    {!v.actual && (
                      <Boton tamano="pequeno" variante="fantasma" icono={<ArrowRight />}
                        onClick={() => { onCerrar(); if (onAbrir) onAbrir(v.id); else navegar(`/instrucciones/${v.id}`) }}>
                        Abrir
                      </Boton>
                    )}
                  </div>
                  <div className="pequeno apagado mt-1">
                    {v.n_pasos} pasos · creada por {v.autor?.nombre ?? 'desconocido'} el {fecha(v.creada)}
                    {v.publicada_en && <> · publicada el {fecha(v.publicada_en)}{v.revisor && <> por {v.revisor.nombre}</>}</>}
                  </div>
                  {comparando === v.id && <VistaDiferencias id={v.id} />}
                </div>
              )
            })}
          </div>
        )}
    </Modal>
  )
}

export function VistaDiferencias({ id, con }: { id: number; con?: number }) {
  const { datos, error } = useDatos((s) => get<Diferencias>(`/api/instrucciones/${id}/diferencias${con ? `?con=${con}` : ''}`, s), [id, con])
  if (error) return <ErrorCarga error={error} />
  if (!datos) return <Cargando texto="Comparando versiones…" />
  if (datos.sin_anterior) return <div className="pequeno apagado mt-1">Es la primera versión: no hay nada con qué compararla.</div>
  if (datos.sin_cambios) return <div className="pequeno apagado mt-1">No hay cambios entre la v{datos.de?.version} y la v{datos.a.version}.</div>
  return (
    <div className="ins-diferencias">
      {datos.generales.length > 0 && (
        <div className="ins-cambio">
          <div className="negrita mb-1">Datos generales</div>
          {datos.generales.map((c) => <Campo key={c.campo} c={c} />)}
        </div>
      )}
      {datos.pasos.map((p, i) => (
        <div key={i} className="ins-cambio">
          <div className="fila envolver">
            <Etiqueta tono={TIPOS[p.tipo].tono}>{TIPOS[p.tipo].texto}</Etiqueta>
            <span className="negrita">
              Paso {p.orden_despues ?? p.orden_antes}
              {p.tipo === 'movido' && p.orden_antes !== p.orden_despues && <span className="apagado"> (antes {p.orden_antes})</span>}
              {' · '}{p.titulo}
            </span>
          </div>
          {p.campos.map((c) => <Campo key={c.campo} c={c} />)}
        </div>
      ))}
    </div>
  )
}

function Campo({ c }: { c: CambioCampo }) {
  const medio = c.campo === 'imagen_ruta' || c.campo === 'clip_ruta'
  return (
    <div className="ins-cambio-campo">
      <div className="diminuto apagado negrita">{c.nombre}</div>
      {medio ? (
        <div className="fila">
          {c.campo === 'imagen_ruta' ? (
            <>
              {c.antes ? <img className="ins-dif-imagen" src={urlServidor(c.antes)} alt="Antes" /> : <span className="ins-dif-antes">sin imagen</span>}
              <ArrowRight size={16} />
              {c.despues ? <img className="ins-dif-imagen" src={urlServidor(c.despues)} alt="Después" /> : <span className="ins-dif-antes">sin imagen</span>}
            </>
          ) : <span className="ins-dif-despues">{c.despues ? 'Clip cambiado' : 'Clip quitado'}</span>}
        </div>
      ) : (
        <div className="ins-dif-textos">
          {c.antes ? <span className="ins-dif-antes">{c.antes}</span> : <span className="apagado diminuto">(vacío)</span>}
          <ArrowRight size={14} className="apagado" />
          {c.despues ? <span className="ins-dif-despues">{c.despues}</span> : <span className="apagado diminuto">(vacío)</span>}
        </div>
      )}
    </div>
  )
}
