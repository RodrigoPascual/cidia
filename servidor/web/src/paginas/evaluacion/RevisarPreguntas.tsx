// «Revisar preguntas» (expertos): las preguntas propuestas por la IA se aprueban, se editan o se
// descartan antes de que entren en el cuestionario. También se pueden generar más o escribir otras.

import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, CheckCircle2, ListChecks, Loader2, Plus, RotateCcw, Save, Sparkles, Trash2, X } from 'lucide-react'
import { del, get, post, put } from '../../api'
import {
  Area, Boton, Entrada, ErrorCarga, Esqueleto, Etiqueta, Pestanas, Selector, Tarjeta, useAvisarError, useAvisos,
  useConfirmar, useDatos, Vacio,
} from '../../ui'
import {
  LETRAS_OPCION, NOMBRE_ESTADO_INSTRUCCION, type InstruccionRevision, type ListaPreguntas, type PasoInstruccion, type Pregunta,
} from './tipos'

type Filtro = 'propuesta' | 'aprobada' | 'descartada'
const NOMBRE_ESTADO: Record<Filtro, string> = { propuesta: 'Propuesta', aprobada: 'Aprobada', descartada: 'Descartada' }
const TONO_ESTADO: Record<Filtro, 'amarilla' | 'verde' | undefined> = { propuesta: 'amarilla', aprobada: 'verde', descartada: undefined }

interface Borrador { enunciado: string; opciones: string[]; correcta: number; explicacion: string; paso_id: number | null }

function borradorDe(p?: Pregunta | null): Borrador {
  return p
    ? { enunciado: p.enunciado, opciones: [...p.opciones], correcta: p.correcta, explicacion: p.explicacion ?? '', paso_id: p.paso_id }
    : { enunciado: '', opciones: ['', '', ''], correcta: 0, explicacion: '', paso_id: null }
}

function PreguntaEditable({ p, pasos, instruccionId, onGuardada, onBorrada, onCancelar }: {
  p: Pregunta | null; pasos: PasoInstruccion[]; instruccionId: number
  onGuardada: (p: Pregunta, nueva: boolean) => void; onBorrada?: (id: number) => void; onCancelar?: () => void
}) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const [b, setB] = useState<Borrador>(() => borradorDe(p))
  const [ocupado, setOcupado] = useState<string | null>(null)
  useEffect(() => setB(borradorDe(p)), [p])

  const original = useMemo(() => borradorDe(p), [p])
  const sucio = JSON.stringify(b) !== JSON.stringify(original)
  const valida = b.enunciado.trim().length >= 5 && b.opciones.length >= 2 && b.opciones.every((o) => o.trim())
  const estado: Filtro | 'nueva' = p ? p.estado : 'nueva'
  const paso = pasos.find((x) => x.id === b.paso_id)

  const cambiar = (c: Partial<Borrador>) => setB((x) => ({ ...x, ...c }))
  function cambiarOpcion(i: number, texto: string) {
    setB((x) => ({ ...x, opciones: x.opciones.map((o, j) => (j === i ? texto : o)) }))
  }
  function quitarOpcion(i: number) {
    setB((x) => ({
      ...x, opciones: x.opciones.filter((_, j) => j !== i),
      correcta: x.correcta === i ? 0 : x.correcta > i ? x.correcta - 1 : x.correcta,
    }))
  }

  async function guardar(nuevoEstado?: Filtro, accion = 'guardar') {
    setOcupado(accion)
    try {
      const campos = { enunciado: b.enunciado, opciones: b.opciones, correcta: b.correcta,
        explicacion: b.explicacion || null, paso_id: b.paso_id }
      let r: Pregunta
      if (!p) {
        r = await post<Pregunta>('/api/evaluacion/preguntas', { instruccion_id: instruccionId, ...campos })
        avisar('Pregunta añadida y aprobada.')
      } else {
        r = await put<Pregunta>(`/api/evaluacion/preguntas/${p.id}`, { ...(sucio ? campos : {}), ...(nuevoEstado ? { estado: nuevoEstado } : {}) })
        avisar(nuevoEstado === 'aprobada' ? 'Pregunta aprobada.' : nuevoEstado === 'descartada' ? 'Pregunta descartada.'
          : nuevoEstado === 'propuesta' ? 'Pregunta recuperada.' : 'Cambios guardados.')
      }
      onGuardada(r, !p)
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }

  async function borrar() {
    if (!p) return
    if (!await confirmar('Eliminar la pregunta', `Se borrará para siempre «${p.enunciado}».`, true)) return
    setOcupado('borrar')
    try {
      await del(`/api/evaluacion/preguntas/${p.id}`)
      avisar('Pregunta eliminada.')
      onBorrada?.(p.id)
    } catch (e) {
      avisarError(e)
      setOcupado(null)
    }
  }

  return (
    <Tarjeta className={`ev-editable ${estado}`}>
      <div className="fila envolver entre" style={{ gap: 8 }}>
        <div className="fila envolver" style={{ gap: 6 }}>
          {estado === 'nueva' ? <Etiqueta tono="azul">Nueva</Etiqueta> : <Etiqueta tono={TONO_ESTADO[estado]}>{NOMBRE_ESTADO[estado]}</Etiqueta>}
          {paso?.es_critico && <Etiqueta tono="roja">Paso crítico</Etiqueta>}
        </div>
        <div className="fila" style={{ gap: 6 }}>
          <Selector aria-label="Paso de origen" className="selector ev-selector-paso" value={b.paso_id ?? ''}
            onChange={(e) => cambiar({ paso_id: e.target.value ? Number(e.target.value) : null })}
            vacio="Sin paso concreto"
            opciones={pasos.map((x) => ({ valor: x.id, texto: `Paso ${x.orden}${x.es_critico ? ' (crítico)' : ''} · ${x.titulo}` }))} />
          {p && <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} aria-label="Eliminar" title="Eliminar"
            cargando={ocupado === 'borrar'} onClick={borrar} />}
        </div>
      </div>

      <textarea className="area ev-campo-enunciado mt-1" rows={2} value={b.enunciado} placeholder="Escribe la pregunta"
        aria-label="Enunciado" onChange={(e) => cambiar({ enunciado: e.target.value })} />

      <div className="columna mt-1" style={{ gap: 6 }}>
        {b.opciones.map((o, i) => (
          <div key={i} className={`ev-opcion-editable ${b.correcta === i ? 'correcta' : ''}`}>
            <button type="button" className="ev-marca-correcta" aria-pressed={b.correcta === i}
              title={b.correcta === i ? 'Opción correcta' : 'Marcar como correcta'} onClick={() => cambiar({ correcta: i })}>
              {b.correcta === i ? <Check size={15} /> : LETRAS_OPCION[i]}
            </button>
            <Entrada value={o} placeholder={`Opción ${LETRAS_OPCION[i]}`} aria-label={`Opción ${LETRAS_OPCION[i]}`}
              onChange={(e) => cambiarOpcion(i, e.target.value)} />
            {b.opciones.length > 2 && (
              <Boton variante="fantasma" tamano="pequeno" icono={<X />} aria-label="Quitar opción" onClick={() => quitarOpcion(i)} />
            )}
          </div>
        ))}
        {b.opciones.length < 6 && (
          <div><Boton variante="fantasma" tamano="pequeno" icono={<Plus />}
            onClick={() => cambiar({ opciones: [...b.opciones, ''] })}>Añadir opción</Boton></div>
        )}
      </div>

      <Area className="area mt-1" rows={2} value={b.explicacion} aria-label="Explicación"
        placeholder="Explicación que verá quien falle (por qué la correcta lo es)"
        onChange={(e) => cambiar({ explicacion: e.target.value })} style={{ minHeight: 60 }} />

      <div className="fila envolver mt-1" style={{ gap: 8, justifyContent: 'flex-end' }}>
        {estado === 'nueva' && <>
          <Boton variante="fantasma" onClick={onCancelar}>Cancelar</Boton>
          <Boton variante="verde" icono={<CheckCircle2 />} disabled={!valida} cargando={ocupado === 'guardar'} onClick={() => guardar()}>
            Guardar y aprobar
          </Boton>
        </>}
        {estado === 'propuesta' && <>
          <Boton variante="peligro" icono={<X />} cargando={ocupado === 'descartar'} onClick={() => guardar('descartada', 'descartar')}>Descartar</Boton>
          {sucio && <Boton icono={<Save />} disabled={!valida} cargando={ocupado === 'guardar'} onClick={() => guardar()}>Guardar</Boton>}
          <Boton variante="verde" icono={<CheckCircle2 />} disabled={!valida} cargando={ocupado === 'aprobar'}
            onClick={() => guardar('aprobada', 'aprobar')}>{sucio ? 'Guardar y aprobar' : 'Aprobar'}</Boton>
        </>}
        {estado === 'aprobada' && <>
          <Boton variante="peligro" icono={<X />} cargando={ocupado === 'descartar'} onClick={() => guardar('descartada', 'descartar')}>Descartar</Boton>
          {sucio && <Boton variante="verde" icono={<Save />} disabled={!valida} cargando={ocupado === 'guardar'} onClick={() => guardar()}>Guardar cambios</Boton>}
        </>}
        {estado === 'descartada' && (
          <Boton icono={<RotateCcw />} cargando={ocupado === 'recuperar'} onClick={() => guardar('propuesta', 'recuperar')}>Recuperar</Boton>
        )}
      </div>
      {dialogo}
    </Tarjeta>
  )
}

function PanelPreguntas({ instruccionId, onCambio }: { instruccionId: number; onCambio: () => void }) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { datos, error, recargar, setDatos } = useDatos(
    (s) => get<ListaPreguntas>(`/api/evaluacion/preguntas?instruccion_id=${instruccionId}`, s), [instruccionId])
  const [filtro, setFiltro] = useState<Filtro | null>(null)
  const [nueva, setNueva] = useState(false)
  const [lanzando, setLanzando] = useState(false)

  // Mientras la IA genera, se consulta cada pocos segundos.
  useEffect(() => {
    if (!datos?.generando) return
    const t = setTimeout(() => { recargar(); onCambio() }, 3500)
    return () => clearTimeout(t)
  }, [datos, recargar, onCambio])

  useEffect(() => { setFiltro(null); setNueva(false) }, [instruccionId])

  if (error) return <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
  if (!datos) return <div className="columna" style={{ gap: 12 }}><Esqueleto alto={60} /><Esqueleto alto={220} /><Esqueleto alto={220} /></div>

  const cuenta = (e: Filtro) => datos.preguntas.filter((p) => p.estado === e).length
  const activo: Filtro = filtro ?? (cuenta('propuesta') ? 'propuesta' : 'aprobada')
  const lista = datos.preguntas.filter((p) => p.estado === activo)

  async function generar() {
    setLanzando(true)
    try {
      const r = await post<{ mensaje: string }>(`/api/evaluacion/instrucciones/${instruccionId}/generar-preguntas`, { n: 6 })
      avisar(r.mensaje, 'info')
      setFiltro('propuesta')
      recargar()
      onCambio()
    } catch (e) {
      avisarError(e)
    } finally {
      setLanzando(false)
    }
  }

  function guardada(p: Pregunta, esNueva: boolean) {
    setDatos((d) => d && ({
      ...d,
      preguntas: esNueva ? [...d.preguntas, p] : d.preguntas.map((x) => (x.id === p.id ? p : x)),
    }))
    if (esNueva) setNueva(false)
    onCambio()
  }

  const ins = datos.instruccion
  return (
    <div className="columna" style={{ gap: 14 }}>
      <Tarjeta>
        <div className="fila envolver entre" style={{ gap: 12 }}>
          <div style={{ minWidth: 0 }}>
            <div className="diminuto apagado">{[ins.codigo, `versión ${ins.version}`, NOMBRE_ESTADO_INSTRUCCION[ins.estado] ?? ins.estado].filter(Boolean).join(' · ')}</div>
            <div className="negrita">{ins.titulo}</div>
            <div className="diminuto apagado">{ins.pasos.length} pasos · {ins.pasos.filter((p) => p.es_critico).length} críticos</div>
          </div>
          <div className="fila envolver" style={{ gap: 8 }}>
            <Boton icono={<Plus />} onClick={() => { setNueva(true); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>Añadir pregunta</Boton>
            <Boton variante="primario" icono={datos.generando ? <Loader2 className="girando" /> : <Sparkles />}
              disabled={datos.generando} cargando={lanzando} onClick={generar}>
              {datos.generando ? 'Generando…' : 'Generar más'}
            </Boton>
          </div>
        </div>
        {datos.generando && (
          <div className="ev-generando mt-2">
            <Loader2 className="girando" size={16} /> La IA está preparando preguntas a partir de los pasos. Aparecerán como propuestas.
          </div>
        )}
      </Tarjeta>

      {nueva && (
        <PreguntaEditable p={null} pasos={ins.pasos} instruccionId={ins.id} onGuardada={guardada} onCancelar={() => setNueva(false)} />
      )}

      <Pestanas<Filtro>
        activa={activo}
        onCambio={setFiltro}
        pestanas={[
          { id: 'propuesta', texto: 'Por revisar', contador: cuenta('propuesta') },
          { id: 'aprobada', texto: 'Aprobadas', contador: cuenta('aprobada') },
          { id: 'descartada', texto: 'Descartadas', contador: cuenta('descartada') },
        ]}
      />

      {lista.length === 0 ? (
        <Tarjeta>
          <Vacio icono={<ListChecks />} titulo={activo === 'propuesta' ? 'No hay preguntas por revisar' : activo === 'aprobada'
            ? 'Todavía no hay preguntas aprobadas' : 'No hay preguntas descartadas'}
            accion={activo !== 'descartada' && !datos.generando
              ? <Boton variante="primario" icono={<Sparkles />} cargando={lanzando} onClick={generar}>Generar preguntas con la IA</Boton>
              : undefined}>
            {activo === 'aprobada'
              ? 'El cuestionario de esta tarea solo usa preguntas aprobadas. Revisa las propuestas o añade las tuyas.'
              : activo === 'propuesta' ? 'Genera preguntas a partir de los pasos o escribe las tuyas.' : undefined}
          </Vacio>
        </Tarjeta>
      ) : (
        lista.map((p) => (
          <PreguntaEditable key={p.id} p={p} pasos={ins.pasos} instruccionId={ins.id} onGuardada={guardada}
            onBorrada={(id) => { setDatos((d) => d && ({ ...d, preguntas: d.preguntas.filter((x) => x.id !== id) })); onCambio() }} />
        ))
      )}
    </div>
  )
}

export default function RevisarPreguntas({ instrucciones, onCambio }: { instrucciones: InstruccionRevision[]; onCambio: () => void }) {
  const [params, setParams] = useSearchParams()
  const pedida = Number(params.get('instruccion')) || null
  const elegida = instrucciones.find((i) => i.id === pedida)?.id ?? instrucciones[0]?.id ?? null

  if (!instrucciones.length) {
    return (
      <Tarjeta>
        <Vacio icono={<ListChecks />} titulo="No hay instrucciones de tu departamento">
          Cuando un experto publique una instrucción, CidIA propondrá preguntas a partir de sus pasos y aparecerán aquí para revisarlas.
        </Vacio>
      </Tarjeta>
    )
  }
  const elegir = (id: number) => setParams((p) => { p.set('pestana', 'preguntas'); p.set('instruccion', String(id)); return p })
  return (
    <div className="ev-revision">
      <div className="ev-instrucciones">
        <Selector className="selector ev-solo-movil" aria-label="Instrucción" value={elegida ?? ''}
          onChange={(e) => elegir(Number(e.target.value))}
          opciones={instrucciones.map((i) => ({ valor: i.id, texto: `${i.tarea ?? i.titulo} (v${i.version})${i.propuestas ? ` · ${i.propuestas} por revisar` : ''}` }))} />
        <div className="ev-lista-instrucciones">
          {instrucciones.map((i) => (
            <button key={i.id} className={`ev-instruccion ${i.id === elegida ? 'activa' : ''}`} onClick={() => elegir(i.id)}>
              <div className="crece" style={{ minWidth: 0 }}>
                <div className="negrita pequeno recortar">{i.tarea ?? i.titulo}</div>
                <div className="diminuto apagado recortar">{[i.codigo, `v${i.version}`, i.estado !== 'publicada' ? NOMBRE_ESTADO_INSTRUCCION[i.estado] ?? i.estado : null].filter(Boolean).join(' · ')}</div>
                <div className="diminuto apagado">{i.aprobadas} aprobadas</div>
              </div>
              {i.generando ? <Loader2 size={15} className="girando" />
                : i.propuestas > 0 ? <span className="ev-contador">{i.propuestas}</span> : null}
            </button>
          ))}
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        {elegida !== null && <PanelPreguntas instruccionId={elegida} onCambio={onCambio} />}
      </div>
    </div>
  )
}
