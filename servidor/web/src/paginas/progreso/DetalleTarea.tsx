// Detalle de una persona en una tarea: nivel y validez, camino al siguiente nivel,
// curva de autonomía y evidencias con fechas. Se usa en el pasaporte y en la matriz del equipo.

import { useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle, Award, CheckCircle2, Circle, ClipboardCheck, Eye, Lightbulb, RefreshCw, TrendingUp, Wrench,
} from 'lucide-react'
import { fecha } from '../../api'
import { Boton, Etiqueta, Iluo, LETRA_ILUO, NOMBRE_ILUO, Tarjeta } from '../../ui'
import CurvaAutonomia from './CurvaAutonomia'
import { mesAnio, type EntradaHistorial, type TareaProgreso } from './tipos'

interface Hito { clave: string; fecha: string; icono: ReactNode; tono?: 'verde' | 'roja' | 'amarilla'; titulo: ReactNode; detalle?: ReactNode }

function textoHistorial(h: EntradaHistorial): { titulo: string; detalle?: string; tono?: Hito['tono'] } {
  const letra = (n?: number) => (n ? LETRA_ILUO[n] : 'sin nivel')
  switch (h.tipo) {
    case 'subida': return { titulo: `Alcanzó el nivel ${letra(h.nivel)}`, tono: 'verde' }
    case 'caducidad':
      return { titulo: `Caducó el nivel ${letra(h.nivel_anterior)}`, tono: 'roja',
        detalle: h.nivel ? `Se renovó con las evidencias recientes: nivel ${letra(h.nivel)}.` : 'No había evidencias recientes para renovarlo.' }
    case 'reevaluacion': return { titulo: 'Versión nueva de la instrucción: reevaluación pendiente', tono: 'amarilla' }
    case 'reevaluado': return { titulo: `Reevaluado con la versión vigente (nivel ${letra(h.nivel)})`, tono: 'verde' }
    case 'ajuste':
      return { titulo: `Nivel ajustado de ${letra(h.nivel_anterior)} a ${letra(h.nivel)}${h.por ? ` por ${h.por}` : ''}`,
        detalle: h.motivo ? `Motivo: ${h.motivo}` : undefined }
    case 'importado':
      return { titulo: `Nivel ${letra(h.nivel)} traído de la matriz anterior`,
        detalle: 'Venía de la matriz de competencias en papel, de antes de CidIA.' }
    default: return { titulo: h.nivel ? `Cambio de nivel: ${letra(h.nivel)}` : 'Cambio de nivel' }
  }
}

function hitos(t: TareaProgreso): Hito[] {
  const ev = t.evidencias
  const lista: Hito[] = []
  for (const c of ev.cuestionarios) {
    lista.push({
      clave: `c${c.id}`, fecha: c.fecha, icono: <ClipboardCheck />, tono: c.aprobado ? 'verde' : 'roja',
      titulo: `${c.aprobado ? 'Cuestionario aprobado' : 'Cuestionario no superado'} · ${Math.round(c.puntuacion * 100)} %`,
      detalle: `${c.aciertos} de ${c.total} aciertos · versión ${c.version ?? '-'}${c.vigente ? ' (vigente)' : ''}`,
    })
  }
  for (const o of ev.observaciones) {
    lista.push({
      clave: `o${o.id}`, fecha: o.fecha, icono: <Eye />, tono: o.aprobada ? 'verde' : 'roja',
      titulo: `${o.aprobada ? 'Observación aprobada' : 'Observación no superada'}${o.evaluador ? ` por ${o.evaluador}` : ''}`,
      detalle: <>{o.pasos_ok} de {o.pasos} pasos bien{o.comentario ? <> · «{o.comentario}»</> : null}</>,
    })
  }
  for (const e of ev.ejecuciones) {
    const estado = e.estado === 'completada' ? 'Ejecución completada' : e.estado === 'en_curso' ? 'Ejecución en curso' : 'Ejecución abandonada'
    lista.push({
      clave: `e${e.id}`, fecha: e.fin ?? e.inicio, icono: <Wrench />, tono: e.consultas_criticos > 0 ? 'amarilla' : undefined,
      titulo: estado,
      detalle: `${e.consultas} ${e.consultas === 1 ? 'consulta' : 'consultas'} al copiloto${e.consultas_criticos ? ` · ${e.consultas_criticos} en pasos críticos` : ''}`,
    })
  }
  for (const a of ev.aportaciones) {
    lista.push({ clave: `a${a.id}`, fecha: a.fecha, icono: <Lightbulb />, tono: 'verde', titulo: 'Aportación validada', detalle: a.titulo })
  }
  if (ev.formador?.fecha) {
    lista.push({ clave: 'f', fecha: ev.formador.fecha, icono: <Award />, tono: 'verde',
      titulo: `Validado como formador${ev.formador.por ? ` por ${ev.formador.por}` : ''}` })
  }
  t.historial.forEach((h, i) => {
    const x = textoHistorial(h)
    lista.push({ clave: `h${i}`, fecha: h.fecha, icono: <TrendingUp />, tono: x.tono, titulo: x.titulo, detalle: x.detalle })
  })
  return lista.filter((h) => h.fecha).sort((a, b) => b.fecha.localeCompare(a.fecha))
}

/** Camino I → L → U → O con los requisitos de cada nivel marcados. */
function Camino({ t }: { t: TareaProgreso }) {
  const micro = t.evidencias.microlecciones
  return (
    <div className="pp-camino">
      {[1, 2, 3, 4].map((n) => {
        const reqs = t.requisitos.filter((r) => r.nivel === n)
        const alcanzado = t.nivel >= n
        const siguiente = t.nivel + 1 === n
        return (
          <div key={n} className={`pp-camino-nivel ${alcanzado ? 'alcanzado' : ''} ${siguiente ? 'siguiente' : ''}`}>
            <div className="fila" style={{ gap: 8 }}>
              <Iluo nivel={n} tamano={22} />
              <div className="crece">
                <div className="negrita pequeno">{LETRA_ILUO[n]} · {NOMBRE_ILUO[n]}</div>
              </div>
              {alcanzado && <CheckCircle2 size={16} className="pp-ok" />}
            </div>
            <ul>
              {reqs.map((r) => (
                <li key={r.clave} className={r.cumplido ? 'cumplido' : ''}>
                  {r.cumplido ? <CheckCircle2 size={15} /> : <Circle size={15} />}
                  <span>{r.texto}</span>
                </li>
              ))}
              {n === 1 && micro.total > 0 && (
                <li className={micro.vistas >= micro.total ? 'cumplido' : ''}>
                  {micro.vistas >= micro.total ? <CheckCircle2 size={15} /> : <Circle size={15} />}
                  <span>Micro-lecciones vistas: {micro.vistas} de {micro.total}</span>
                </li>
              )}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

export default function DetalleTarea({ t, acciones, persona }: { t: TareaProgreso; acciones?: ReactNode; persona?: string }) {
  const [todos, setTodos] = useState(false)
  const lista = useMemo(() => hitos(t), [t])
  const visibles = todos ? lista : lista.slice(0, 8)
  return (
    <div className="columna" style={{ gap: 16 }}>
      <Tarjeta>
        <div className="pp-detalle-cabecera">
          <div className="pp-iluo-grande">
            <Iluo nivel={t.nivel} tamano={64} caducado={t.caducado} />
            <span>{LETRA_ILUO[t.nivel]}</span>
          </div>
          <div className="crece">
            <div className="diminuto apagado">{[t.tarea.codigo, t.tarea.puesto].filter(Boolean).join(' · ')}</div>
            <h2 className="pp-detalle-titulo">{t.tarea.nombre}</h2>
            <div className="fila envolver mt-1" style={{ gap: 6 }}>
              <Etiqueta tono={t.nivel >= 3 ? 'verde' : t.nivel > 0 ? 'amarilla' : undefined}>{t.nombre_nivel}</Etiqueta>
              {t.requiere_reevaluacion && <Etiqueta tono="naranja" icono={<RefreshCw />}>Reevaluación pendiente</Etiqueta>}
              {t.caducado && <Etiqueta tono="roja" icono={<AlertTriangle />}>Caducado</Etiqueta>}
              {!t.caducado && t.caduca_pronto && <Etiqueta tono="naranja">Caduca en {t.dias_para_caducar} días</Etiqueta>}
              {t.formador_validado && <Etiqueta tono="oscura" icono={<Award />}>Formador</Etiqueta>}
            </div>
            <div className="pequeno apagado mt-1">
              {t.nivel > 0 && t.desde ? <>Nivel desde el {fecha(t.desde)}</> : 'Sin nivel todavía'}
              {t.nivel > 0 && t.caduca ? <> · válido hasta {mesAnio(t.caduca)}</> : null}
              {t.instruccion ? <> · instrucción vigente v{t.instruccion.version}</> : <> · sin instrucción publicada</>}
            </div>
          </div>
        </div>
        {t.siguiente?.texto && (
          <div className="pp-siguiente mt-2">
            <span className="pp-siguiente-etiqueta">Para el nivel {t.siguiente.letra}</span>
            <span>{t.siguiente.texto}</span>
          </div>
        )}
        {acciones && <div className="fila envolver mt-2" style={{ gap: 8 }}>{acciones}</div>}
      </Tarjeta>

      <Tarjeta titulo="Camino al siguiente nivel">
        <Camino t={t} />
      </Tarjeta>

      <Tarjeta titulo={`Curva de autonomía${persona ? ` · ${persona}` : ''}`} icono={<TrendingUp size={18} />}>
        <CurvaAutonomia puntos={t.curva} />
      </Tarjeta>

      <Tarjeta titulo="Evidencias" acciones={<span className="pequeno apagado">{lista.length}</span>}>
        {lista.length === 0 ? (
          <div className="pequeno apagado">Todavía no hay evidencias en esta tarea.</div>
        ) : (
          <>
            <ol className="pp-linea-tiempo">
              {visibles.map((h) => (
                <li key={h.clave} className={h.tono ?? ''}>
                  <span className="pp-hito-icono">{h.icono}</span>
                  <div className="crece">
                    <div className="fila entre arriba" style={{ gap: 10 }}>
                      <span className="negrita pequeno">{h.titulo}</span>
                      <span className="diminuto apagado" style={{ whiteSpace: 'nowrap' }}>{fecha(h.fecha)}</span>
                    </div>
                    {h.detalle && <div className="diminuto apagado">{h.detalle}</div>}
                  </div>
                </li>
              ))}
            </ol>
            {lista.length > 8 && (
              <Boton variante="fantasma" tamano="pequeno" className="mt-1" onClick={() => setTodos(!todos)}>
                {todos ? 'Ver menos' : `Ver todas (${lista.length})`}
              </Boton>
            )}
          </>
        )}
      </Tarjeta>
    </div>
  )
}
