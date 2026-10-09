// Formación de una tarea: estado ILUO y avance, micro-lecciones navegables, resumen de la
// instrucción vigente, acceso al cuestionario, práctica en el modo planta y tutor socrático.

import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BookOpen, ClipboardCheck, Eye, FileVideo, GraduationCap, HardHat,
  RefreshCw, ScrollText, ShieldAlert, Sparkles, Wrench,
} from 'lucide-react'
import { fecha, get, post, urlServidor } from '../../api'
import {
  Aviso, BarraProgreso, Boton, Cabecera, Cargando, ErrorCarga, Esqueleto, Etiqueta, Iluo, NOMBRE_ILUO, Tarjeta, Vacio,
  useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import { Lecciones } from './Lecciones'
import { Tutor } from './Tutor'
import type { DetalleTarea } from './tipos'
import './formacion.css'

function Hito({ icono, ok, valor, texto }: { icono: ReactNode; ok: boolean; valor: ReactNode; texto: string }) {
  return (
    <div className={`ft-hito ${ok ? 'ok' : ''}`}>
      <div className="icono">{icono}</div>
      <div><span className="valor">{valor}</span><span className="texto">{texto}</span></div>
    </div>
  )
}

function Estado({ d }: { d: DetalleTarea }) {
  const ml = d.microlecciones
  return (
    <div className="tarjeta ft-estado">
      <div className="ft-estado-nivel">
        <Iluo nivel={d.nivel} tamano={56} caducado={d.caducado} />
        <div>
          <div className="ft-letra">{d.nivel ? `Nivel ${d.nivel_letra}` : 'Sin iniciar'}</div>
          <div className="pequeno apagado">
            {NOMBRE_ILUO[d.nivel]}{d.caduca ? ` · válido hasta el ${fecha(d.caduca)}` : ''}
          </div>
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="fila entre pequeno"><span className="negrita">Avance hacia la autonomía</span><span className="negrita">{d.avance} %</span></div>
        <div className="mt-1"><BarraProgreso valor={d.avance} tono={d.avance >= 100 ? undefined : 'amarilla'} /></div>
        <div className="fm-siguiente"><ArrowRight /> <span><strong>Siguiente:</strong> {d.siguiente.texto}</span></div>
      </div>
      <div className="ft-hitos">
        <Hito icono={<BookOpen />} ok={ml.total > 0 && ml.vistas === ml.total} valor={ml.total ? `${ml.vistas} de ${ml.total}` : 'Sin preparar'}
          texto="Micro-lecciones" />
        <Hito icono={<ClipboardCheck />} ok={d.cuestionario.aprobado}
          valor={d.cuestionario.aprobado ? 'Aprobado' : d.cuestionario.disponible ? 'Pendiente' : 'En preparación'} texto="Cuestionario" />
        <Hito icono={<Wrench />} ok={d.ejecuciones.completadas >= d.ejecuciones.objetivo}
          valor={`${Math.min(d.ejecuciones.completadas, d.ejecuciones.objetivo)} de ${d.ejecuciones.objetivo}`} texto="Ejecuciones" />
        <Hito icono={<Eye />} ok={d.observacion_aprobada} valor={d.observacion_aprobada ? 'Aprobada' : 'Pendiente'} texto="Observación" />
      </div>
    </div>
  )
}

function Instruccion({ d }: { d: DetalleTarea }) {
  const ins = d.instruccion!
  const riesgos = [ins.riesgos, d.riesgos_prl].filter(Boolean).join('\n')
  return (
    <Tarjeta titulo="La instrucción" icono={<ScrollText size={18} />}
      acciones={<Etiqueta>{ins.codigo ?? 'Instrucción'} · v{ins.version}</Etiqueta>}>
      {ins.resumen && <p className="apagado">{ins.resumen}</p>}
      {riesgos && <div className="ft-ficha roja"><ShieldAlert /><div className="pre"><strong>Riesgos</strong>{riesgos}</div></div>}
      {ins.epis && <div className="ft-ficha"><HardHat /><div><strong>EPI</strong>{ins.epis}</div></div>}
      {ins.herramientas && <div className="ft-ficha"><Wrench /><div><strong>Herramientas</strong>{ins.herramientas}</div></div>}
      <ol className="ft-pasos" aria-label="Pasos">
        {ins.pasos.map((p) => (
          <li key={p.id} className={p.es_critico ? 'critico' : ''}>
            <span className="n">{p.numero}</span>
            <span className="crece">{p.titulo}</span>
            {p.es_seguridad && <ShieldAlert className="seguridad-icono" aria-label="Seguridad" />}
            {p.es_critico && <AlertTriangle className="critico-icono" aria-label="Paso crítico" />}
          </li>
        ))}
      </ol>
      <div className="fila entre envolver mt-2 pequeno apagado">
        <span>{ins.publicada_en ? `Publicada el ${fecha(ins.publicada_en)}` : ''}</span>
        {ins.video_url && (
          <a href={urlServidor(ins.video_url)} target="_blank" rel="noreferrer" className="fila" style={{ gap: 6 }}>
            <FileVideo size={16} /> Ver el vídeo del experto
          </a>
        )}
      </div>
    </Tarjeta>
  )
}

function EsqueletoTarea() {
  return (
    <>
      <Esqueleto alto={14} ancho={160} className="mb-1" />
      <Esqueleto alto={30} ancho="55%" className="mb-3" />
      <Esqueleto alto={110} className="mb-3" />
      <div className="ft-rejilla">
        <Esqueleto alto={420} />
        <div className="ft-lateral"><Esqueleto alto={260} /><Esqueleto alto={200} /></div>
      </div>
    </>
  )
}

export default function Tarea() {
  const { id } = useParams()
  const navegar = useNavigate()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const { datos: d, error, cargando, recargar, setDatos } = useDatos((s) => get<DetalleTarea>(`/api/formacion/tareas/${id}`, s), [id])
  const [empezando, setEmpezando] = useState(false)

  // Actualiza en silencio (sin esqueleto) para no perder la micro-lección abierta.
  const refrescar = () => get<DetalleTarea>(`/api/formacion/tareas/${id}`).then(setDatos).catch(() => undefined)

  // Mientras se generan las micro-lecciones, consulta el trabajo y recarga al terminar.
  const generando = d?.generacion && ['pendiente', 'en_curso'].includes(d.generacion.estado) ? d.generacion.trabajo_id : null
  useEffect(() => {
    if (!generando) return
    const t = setInterval(async () => {
      try {
        const r = await get<{ estado: string }>(`/api/trabajos/${generando}`)
        if (r.estado === 'pendiente' || r.estado === 'en_curso') return
        clearInterval(t)
        if (r.estado === 'completado') avisar('Micro-lecciones listas.')
        refrescar()
      } catch {
        /* se reintenta en la siguiente vuelta */
      }
    }, 2500)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generando])

  async function practicar() {
    if (!d) return
    setEmpezando(true)
    try {
      const ej = await post<{ id: number }>('/api/planta/ejecuciones', { tarea_id: d.tarea_id })
      navegar(`/planta/ejecucion/${ej.id}`)
    } catch (e) {
      avisarError(e)
      setEmpezando(false)
    }
  }

  async function regenerar() {
    if (!d) return
    const ok = await confirmar('Regenerar las micro-lecciones',
      'Se escribirán de nuevo a partir de los pasos de la instrucción vigente. Quien ya las haya visto tendrá que verlas otra vez.')
    if (!ok) return
    try {
      const r = await post<{ trabajo_id: number }>(`/api/formacion/tareas/${d.tarea_id}/generar`)
      setDatos({ ...d, generacion: { trabajo_id: r.trabajo_id, estado: 'pendiente', mensaje: null } })
      avisar('Preparando las micro-lecciones. Tardará unos segundos.', 'info')
    } catch (e) {
      avisarError(e)
    }
  }

  async function vista(leccionId: number) {
    await post(`/api/formacion/microlecciones/${leccionId}/vista`)
    refrescar()
  }

  if (cargando && !d) return <EsqueletoTarea />
  if (error || !d) {
    return (
      <>
        <Boton variante="fantasma" tamano="pequeno" className="ft-volver" icono={<ArrowLeft />} onClick={() => navegar('/formacion')}>Formación</Boton>
        <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
      </>
    )
  }

  const ins = d.instruccion
  const irCuestionario = () => navegar(`/evaluacion?tarea=${d.tarea_id}`)
  const botonPracticar = (
    <Boton variante="primario" icono={<Wrench />} cargando={empezando} disabled={!ins} onClick={practicar}>
      Practicar en modo planta
    </Boton>
  )
  const botonCuestionario = (
    <Boton icono={<ClipboardCheck />} disabled={!ins} onClick={irCuestionario}
      title={d.cuestionario.disponible ? undefined : 'El experto todavía no ha aprobado las preguntas'}>
      {d.cuestionario.aprobado ? 'Ver cuestionario' : d.cuestionario.disponible ? 'Hacer el cuestionario' : 'Cuestionario'}
    </Boton>
  )

  let lecciones: ReactNode
  if (!ins) {
    lecciones = (
      <Tarjeta>
        <Vacio icono={<ScrollText />} titulo="Esta tarea aún no tiene instrucción publicada">
          Cuando el experto la publique, aquí aparecerán sus micro-lecciones y podrás practicarla en el modo planta.
        </Vacio>
      </Tarjeta>
    )
  } else if (generando) {
    lecciones = <Tarjeta><Cargando texto="Preparando las micro-lecciones a partir de la instrucción…" /></Tarjeta>
  } else if (!d.lecciones.length) {
    lecciones = (
      <Tarjeta>
        <Vacio icono={<BookOpen />} titulo="Todavía no hay micro-lecciones"
          accion={d.puede_generar && <Boton variante="primario" icono={<Sparkles />} onClick={regenerar}>Generarlas ahora</Boton>}>
          {d.generacion?.estado === 'error'
            ? 'La última preparación falló. Puedes practicar en el modo planta mientras tanto.'
            : 'Se preparan automáticamente al publicar la instrucción. Mientras tanto, puedes practicar en el modo planta.'}
        </Vacio>
      </Tarjeta>
    )
  } else {
    lecciones = (
      <Lecciones key={ins.id} lecciones={d.lecciones} onVista={vista}
        alTerminar={<>{d.cuestionario.disponible && !d.cuestionario.aprobado ? botonCuestionario : null}{botonPracticar}</>} />
    )
  }

  return (
    <>
      <Boton variante="fantasma" tamano="pequeno" className="ft-volver" icono={<ArrowLeft />} onClick={() => navegar('/formacion')}>
        Formación
      </Boton>
      <Cabecera
        antetitulo={<><GraduationCap size={14} /> {[d.codigo, d.departamento].filter(Boolean).join(' · ') || 'Formación'}</>}
        titulo={d.nombre}
        subtitulo={ins
          ? `${ins.codigo ?? 'Instrucción'} · versión ${ins.version} · ${ins.pasos.length} pasos, ${ins.pasos.filter((p) => p.es_critico).length} críticos`
          : d.descripcion ?? 'Sin instrucción publicada todavía.'}
        acciones={<>
          {d.puede_generar && ins && (
            <Boton variante="fantasma" icono={<RefreshCw />} disabled={!!generando} onClick={regenerar}>Regenerar micro-lecciones</Boton>
          )}
          {botonCuestionario}
          {botonPracticar}
        </>}
      />

      {d.requiere_reevaluacion && (
        <div className="mb-2">
          <Aviso tono="amarillo" titulo="Hay una versión nueva de la instrucción">
            Repasa lo que ha cambiado y vuelve a hacer el cuestionario para mantener tu nivel.
          </Aviso>
        </div>
      )}
      {d.origen === 'formacion' && d.formacion && (
        <div className="mb-2">
          <Aviso titulo={`Formación en ${d.formacion.departamento}`}>
            Esta tarea forma parte de tu formación{d.formacion.fin_previsto ? ` hasta el ${fecha(d.formacion.fin_previsto)}` : ''}.
          </Aviso>
        </div>
      )}

      <Estado d={d} />

      <div className="ft-rejilla">
        <div className="columna" style={{ gap: 16 }}>
          {lecciones}
          {d.evaluacion.ultimo && (
            <Tarjeta titulo="Tu último cuestionario" icono={<ClipboardCheck size={18} />}
              acciones={<Etiqueta tono={d.evaluacion.ultimo.aprobado ? 'verde' : 'roja'}>{d.evaluacion.ultimo.aprobado ? 'Aprobado' : 'No superado'}</Etiqueta>}>
              <div className="fila entre envolver">
                <span>
                  {d.evaluacion.ultimo.aciertos} de {d.evaluacion.ultimo.total} aciertos ({Math.round(d.evaluacion.ultimo.puntuacion * 100)} %)
                  · {d.evaluacion.intentos} {d.evaluacion.intentos === 1 ? 'intento' : 'intentos'}
                </span>
                <span className="pequeno apagado">{fecha(d.evaluacion.ultimo.creado, true)}</span>
              </div>
            </Tarjeta>
          )}
        </div>
        <div className="ft-lateral">
          {ins && <Instruccion d={d} />}
          <Tutor tareaId={d.tarea_id} />
        </div>
      </div>
      {dialogo}
    </>
  )
}
