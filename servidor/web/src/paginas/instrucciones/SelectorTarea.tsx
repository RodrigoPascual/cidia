// Selector de las tareas que la persona puede capturar o documentar (las de su departamento;
// la administración ve todas, agrupadas por departamento).

import type { ChangeEvent } from 'react'
import { get } from '../../api'
import { useDatos } from '../../ui'
import { textoTarea, type TareaGestionable } from './tipos'

export function useTareas() {
  return useDatos((s) => get<TareaGestionable[]>('/api/instrucciones/tareas', s), [])
}

export default function SelectorTarea({ tareas, valor, onCambio, vacio, cargando, id }: {
  tareas: TareaGestionable[] | null
  valor: string
  onCambio: (id: string) => void
  vacio?: string
  cargando?: boolean
  id?: string
}) {
  const lista = tareas ?? []
  const departamentos = [...new Set(lista.map((t) => t.departamento ?? 'Sin departamento'))].sort()
  const varios = departamentos.length > 1
  const alCambiar = (e: ChangeEvent<HTMLSelectElement>) => onCambio(e.target.value)
  return (
    <select id={id} className="selector" value={valor} onChange={alCambiar} disabled={cargando}>
      {cargando ? <option value="">Cargando tareas…</option> : vacio !== undefined && <option value="">{vacio}</option>}
      {varios
        ? departamentos.map((d) => (
          <optgroup key={d} label={d}>
            {lista.filter((t) => (t.departamento ?? 'Sin departamento') === d).map((t) => (
              <option key={t.id} value={t.id}>{textoTarea(t)}</option>
            ))}
          </optgroup>
        ))
        : lista.map((t) => <option key={t.id} value={t.id}>{textoTarea(t)}</option>)}
    </select>
  )
}
