// Fotos del resultado para el jefe del departamento (y la administración): las que CidIA no ha
// podido confirmar (sin visión, con diferencias o con dudas del modelo) esperan su revisión.
// Cada tarjeta abre la ejecución en solo lectura directamente en la foto (?revisar=1).

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera, CheckCircle2, ChevronRight, ImageOff, XCircle } from 'lucide-react'
import { get, hace, urlServidor } from '../../api'
import { ErrorCarga, Esqueleto, Etiqueta, Tarjeta, Vacio, useDatos } from '../../ui'
import type { FotoPorRevisar } from './tipos'

export interface ListaRevisiones {
  elementos: FotoPorRevisar[]
  pendientes: number
}

type Filtro = 'pendientes' | 'revisadas' | 'todas'

const FILTROS: { id: Filtro; texto: string }[] = [
  { id: 'pendientes', texto: 'Pendientes' },
  { id: 'revisadas', texto: 'Revisadas' },
  { id: 'todas', texto: 'Todas' },
]

function motivo(f: FotoPorRevisar): string {
  const v = f.foto
  if (v.estado === 'comparando') return 'Comparando con la referencia…'
  if (v.estado === 'sin_vision') return 'Sin modelo con visión'
  if (v.estado === 'sin_referencia') return 'Sin imagen de referencia'
  if (v.estado === 'error') return 'No se pudo comparar'
  if (v.coincide === false) return 'El modelo ve diferencias'
  if (v.necesita_revision) return 'El modelo tiene dudas'
  return 'El modelo cree que coincide'
}

function TarjetaFoto({ f }: { f: FotoPorRevisar }) {
  const navegar = useNavigate()
  const foto = urlServidor(f.foto.foto_url)
  const ref = urlServidor(f.foto.referencia_url)
  const r = f.foto.revision
  const abrir = () => navegar(`/planta/ejecucion/${f.id}?revisar=1`)
  return (
    <button type="button" className={`rv-tarjeta ${f.pendiente ? 'pendiente' : ''}`} onClick={abrir}>
      <div className="rv-fotos">
        <figure>
          {ref ? <img src={ref} alt="" loading="lazy" /> : <div className="rv-sin"><ImageOff /></div>}
          <figcaption>Referencia</figcaption>
        </figure>
        <figure>
          {foto ? <img src={foto} alt={`Foto de ${f.persona?.nombre ?? 'la persona'}`} loading="lazy" /> : <div className="rv-sin"><Camera /></div>}
          <figcaption>Resultado</figcaption>
        </figure>
      </div>
      <div className="rv-cuerpo">
        <div className="rv-cabeza">
          <span className="rv-persona">{f.persona?.nombre ?? 'Persona'}</span>
          {r ? (
            r.estado === 'aprobada'
              ? <Etiqueta tono="verde" icono={<CheckCircle2 />}>Dada por buena</Etiqueta>
              : <Etiqueta tono="roja" icono={<XCircle />}>Rechazada</Etiqueta>
          ) : f.pendiente ? <Etiqueta tono="amarilla">Por revisar</Etiqueta> : <Etiqueta>Sin revisar</Etiqueta>}
        </div>
        <div className="rv-tarea recortar">
          {f.tarea?.codigo && <span className="rv-codigo">{f.tarea.codigo}</span>}{f.tarea?.nombre}
        </div>
        <div className="rv-detalle">
          {motivo(f)} · {f.estado === 'completada' ? `terminada ${hace(f.fin)}` : 'sin finalizar todavía'}
        </div>
        {r?.comentario && <div className="rv-comentario recortar">«{r.comentario}»</div>}
      </div>
      <ChevronRight className="rv-flecha" />
    </button>
  )
}

export default function Revisiones({ pendientes, recargarPendientes }: {
  pendientes: { datos: ListaRevisiones | null; error: unknown; cargando: boolean }
  recargarPendientes: () => void
}) {
  const [filtro, setFiltro] = useState<Filtro>('pendientes')
  const otras = useDatos(
    (s) => (filtro === 'pendientes' ? Promise.resolve(null) : get<ListaRevisiones>(`/api/planta/revisiones?estado=${filtro}`, s)),
    [filtro],
  )
  const actual = filtro === 'pendientes' ? pendientes : otras
  const lista = actual.datos?.elementos ?? []

  return (
    <section className="rv">
      <div className="rv-filtros" role="group" aria-label="Qué fotos ver">
        {FILTROS.map((x) => (
          <button key={x.id} type="button" className={`rv-filtro ${filtro === x.id ? 'activo' : ''}`} aria-pressed={filtro === x.id}
            onClick={() => setFiltro(x.id)}>
            {x.texto}
            {x.id === 'pendientes' && !!pendientes.datos?.pendientes && <span className="rv-contador">{pendientes.datos.pendientes}</span>}
          </button>
        ))}
      </div>
      {(filtro === 'pendientes' ? pendientes.cargando && !pendientes.datos : otras.cargando) ? (
        <div className="rv-rejilla">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={128} />)}</div>
      ) : actual.error ? (
        <Tarjeta><ErrorCarga error={actual.error} reintentar={filtro === 'pendientes' ? recargarPendientes : otras.recargar} /></Tarjeta>
      ) : lista.length === 0 ? (
        <Tarjeta>
          <Vacio icono={<CheckCircle2 />} titulo={filtro === 'pendientes' ? 'No hay fotos pendientes de revisar' : 'Todavía no hay fotos aquí'}>
            {filtro === 'pendientes'
              ? 'Cuando alguien de tu departamento termine una tarea y CidIA no pueda confirmar la foto del resultado (sin visión, con diferencias o con dudas), aparecerá aquí para que la revises.'
              : 'Aquí verás las fotos del resultado de las tareas de tu departamento y lo que decidiste sobre cada una.'}
          </Vacio>
        </Tarjeta>
      ) : (
        <div className="rv-rejilla">{lista.map((f) => <TarjetaFoto key={f.id} f={f} />)}</div>
      )}
    </section>
  )
}
