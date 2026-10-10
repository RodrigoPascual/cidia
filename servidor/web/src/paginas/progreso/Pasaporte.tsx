// Pasaporte de habilidades de una persona: cabecera con resumen, una fila por tarea con su
// cuadrado ILUO y su avance, y el detalle de la tarea elegida. Lo usan «Mi progreso» y la
// ficha de una persona en la matriz del equipo.

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Award, ChevronRight, RefreshCw } from 'lucide-react'
import { Aviso, Avatar, BarraProgreso, Etiqueta, Iluo, LETRA_ILUO, NOMBRE_ILUO, Tarjeta } from '../../ui'
import DetalleTarea from './DetalleTarea'
import { textoEstado, type Progreso, type TareaProgreso } from './tipos'
import './progreso.css'

export function FilaTarea({ t, activa, onClick }: { t: TareaProgreso; activa?: boolean; onClick: () => void }) {
  return (
    <button className={`pp-fila ${activa ? 'activa' : ''}`} onClick={onClick} aria-pressed={activa}>
      <div className="pp-fila-iluo">
        <Iluo nivel={t.nivel} tamano={38} caducado={t.caducado} />
        <span className={t.caducado ? 'caducado' : ''}>{LETRA_ILUO[t.nivel]}</span>
      </div>
      <div className="crece">
        <div className="fila entre" style={{ gap: 8 }}>
          <span className="negrita recortar">{t.tarea.nombre}</span>
          <span className="diminuto apagado" style={{ flexShrink: 0 }}>{t.porcentaje} %</span>
        </div>
        <div className="mt-1"><BarraProgreso valor={t.porcentaje} /></div>
        <div className="fila mt-1" style={{ gap: 6, minWidth: 0 }}>
          {t.requiere_reevaluacion && <RefreshCw size={13} className="pp-icono-aviso" />}
          {t.caducado && <AlertTriangle size={13} className="pp-icono-alerta" />}
          {t.formador_validado && <Award size={13} className="pp-icono-formador" />}
          <span className={`diminuto recortar ${t.caducado ? 'pp-texto-alerta' : 'apagado'}`}>{textoEstado(t)}</span>
        </div>
      </div>
      <ChevronRight size={18} className="pp-fila-flecha" />
    </button>
  )
}

export default function Pasaporte({ datos, propio = false, acciones, tareaInicial }: {
  datos: Progreso
  propio?: boolean
  acciones?: (t: TareaProgreso) => ReactNode
  tareaInicial?: number
}) {
  const { persona, resumen, tareas } = datos
  // Sin tarea pedida, se abre la que más enseña: la primera con curva de autonomía, si no la
  // primera con nivel, y si no la primera (una tarea recién añadida no debe dejar la curva vacía).
  const [elegida, setElegida] = useState<number | null>(() => tareaInicial
    ?? (tareas.find((t) => t.curva.length > 0) ?? tareas.find((t) => t.nivel > 0) ?? tareas[0])?.tarea.id ?? null)
  const detalle = useRef<HTMLDivElement>(null)
  const actual = tareas.find((t) => t.tarea.id === elegida) ?? tareas[0]

  useEffect(() => {
    if (elegida !== null && !tareas.some((t) => t.tarea.id === elegida)) setElegida(tareas[0]?.tarea.id ?? null)
  }, [tareas, elegida])

  function elegir(id: number) {
    setElegida(id)
    // En pantallas estrechas el detalle va debajo: se lleva la vista hasta él.
    if (window.innerWidth < 1100) setTimeout(() => detalle.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }

  const ubicacion = [persona.puesto, persona.departamento].filter(Boolean).join(' · ')
  return (
    <div className="columna" style={{ gap: 18 }}>
      <Tarjeta>
        <div className="pp-cabecera">
          <Avatar nombre={persona.nombre} iniciales={persona.iniciales} tamano="g" />
          <div className="crece">
            <h2>{persona.nombre}</h2>
            <div className="pequeno apagado">
              {ubicacion && <>{ubicacion} · </>}
              {resumen.tareas} {resumen.tareas === 1 ? 'tarea' : 'tareas'} en {propio ? 'tu' : 'su'} itinerario
            </div>
            {persona.formaciones.length > 0 && (
              <div className="fila envolver mt-1" style={{ gap: 6 }}>
                {persona.formaciones.map((f, i) => (
                  <Etiqueta key={i} tono="azul">En formación: {f.departamento}{f.puesto ? ` · ${f.puesto}` : ''}</Etiqueta>
                ))}
              </div>
            )}
          </div>
          <div className="pp-contadores" aria-label="Tareas por nivel">
            {([1, 2, 3, 4] as const).map((n) => (
              <div key={n} className="pp-contador" title={NOMBRE_ILUO[n]}>
                <Iluo nivel={n} tamano={24} />
                <div>
                  <div className="valor">{resumen.por_nivel[LETRA_ILUO[n] as 'I' | 'L' | 'U' | 'O']}</div>
                  <div className="diminuto apagado">{NOMBRE_ILUO[n]}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Tarjeta>

      {(resumen.reevaluaciones > 0 || resumen.caducan_pronto > 0) && (
        <div className="columna" style={{ gap: 8 }}>
          {resumen.reevaluaciones > 0 && (
            <Aviso tono="amarillo" titulo="Hay versiones nuevas de instrucciones">
              {resumen.reevaluaciones === 1 ? 'Una tarea necesita' : `${resumen.reevaluaciones} tareas necesitan`} reevaluación.{' '}
              {propio ? 'Haz de nuevo el cuestionario de la versión vigente para mantener tu nivel.' : 'Tiene que aprobar el cuestionario de la versión vigente.'}
            </Aviso>
          )}
          {resumen.caducan_pronto > 0 && (
            <Aviso tono="alerta" titulo="Niveles a punto de caducar">
              {resumen.caducan_pronto === 1 ? 'Un nivel caduca' : `${resumen.caducan_pronto} niveles caducan`} en los próximos 60 días
              o ya ha caducado. Se renuevan solos si hay evidencias recientes (cuestionario, ejecuciones y observación).
            </Aviso>
          )}
        </div>
      )}

      <div className="pp-rejilla">
        <div className="columna" style={{ gap: 8 }}>
          {tareas.map((t) => (
            <FilaTarea key={t.tarea.id} t={t} activa={actual?.tarea.id === t.tarea.id} onClick={() => elegir(t.tarea.id)} />
          ))}
        </div>
        <div ref={detalle} className="pp-detalle">
          {actual && <DetalleTarea t={actual} acciones={acciones?.(actual)} persona={propio ? undefined : persona.nombre} />}
        </div>
      </div>
    </div>
  )
}
