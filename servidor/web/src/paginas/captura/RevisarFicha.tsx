// Revisión de la ficha que CidIA ha preparado a partir de una nota de voz o de una entrevista:
// el experto corrige el título, el contenido y las etiquetas y la publica (entonces se indexa).

import { useEffect, useState, type KeyboardEvent } from 'react'
import { BookOpen, CheckCircle2, Eye, Pencil, Save, Send, Tag, X } from 'lucide-react'
import { get, post, put, urlServidor } from '../../api'
import {
  Area, Aviso, Boton, Campo, Cargando, Entrada, ErrorCarga, Etiqueta, Modal, Pestanas, TextoFormato,
  useAvisarError, useAvisos, useConfirmar,
} from '../../ui'
import { mmss, type Captura } from './tipos'

export default function RevisarFicha({ capturaId, onCerrar, onCambio }: {
  capturaId: number | null
  onCerrar: () => void
  onCambio?: (c: Captura) => void
}) {
  const [cap, setCap] = useState<Captura | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [titulo, setTitulo] = useState('')
  const [contenido, setContenido] = useState('')
  const [etiquetas, setEtiquetas] = useState<string[]>([])
  const [nueva, setNueva] = useState('')
  const [modo, setModo] = useState<'editar' | 'vista'>('vista')
  const [sucio, setSucio] = useState(false)
  const [ocupado, setOcupado] = useState<'guardar' | 'publicar' | null>(null)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  function cargarFicha(c: Captura) {
    setCap(c)
    setTitulo(c.ficha?.titulo ?? '')
    setContenido(c.ficha?.contenido ?? '')
    setEtiquetas(c.ficha?.etiquetas ?? [])
    setSucio(false)
  }

  useEffect(() => {
    if (capturaId === null) return
    setCap(null)
    setError(null)
    setModo('vista')
    const ctl = new AbortController()
    get<Captura>(`/api/captura/${capturaId}`, ctl.signal).then(cargarFicha).catch((e) => {
      if (e?.name !== 'AbortError') setError(e)
    })
    return () => ctl.abort()
  }, [capturaId])

  const ficha = cap?.ficha
  const publicada = !!ficha?.publicada

  function anadirEtiqueta() {
    const e = nueva.trim().toLowerCase().replace(/,$/, '')
    if (e && !etiquetas.includes(e)) {
      setEtiquetas([...etiquetas, e])
      setSucio(true)
    }
    setNueva('')
  }

  function teclaEtiqueta(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      anadirEtiqueta()
    }
  }

  async function guardar(silencioso = false): Promise<boolean> {
    if (!cap) return false
    if (!titulo.trim()) {
      avisar('La ficha necesita un título.', 'error')
      return false
    }
    setOcupado('guardar')
    try {
      const c = await put<Captura>(`/api/captura/${cap.id}/ficha`, { titulo, contenido, etiquetas })
      cargarFicha(c)
      onCambio?.(c)
      if (!silencioso) avisar('Ficha guardada')
      return true
    } catch (e) {
      avisarError(e)
      return false
    } finally {
      setOcupado(null)
    }
  }

  async function publicar() {
    if (!cap || !ficha) return
    const ok = await confirmar('Publicar la ficha', (
      <>
        <p>«{titulo}» se añadirá al conocimiento de <strong>{ficha.departamento ?? 'tu departamento'}</strong>.
          El copiloto podrá encontrarla y citarla, y quedará constancia de quién la contó
          {cap.autor ? ` (${cap.autor.nombre})` : ''} y de quién la validó (tú).</p>
        <p className="mb-1">Revisa que no haya datos personales ni nada que no quieras compartir.</p>
      </>
    ))
    if (!ok) return
    if (sucio && !(await guardar(true))) return
    setOcupado('publicar')
    try {
      const c = await post<Captura>(`/api/captura/${cap.id}/ficha/publicar`)
      cargarFicha(c)
      onCambio?.(c)
      avisar('Ficha publicada. Ya forma parte del conocimiento de tu departamento.')
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }

  async function cerrar() {
    if (sucio && !(await confirmar('Cambios sin guardar', 'Hay cambios sin guardar en la ficha. ¿Cerrar igualmente?'))) return
    onCerrar()
  }

  const origen = cap?.tipo === 'entrevista' ? 'la entrevista' : 'tu nota de voz'
  const pie = ficha && (publicada ? (
    <>
      <Etiqueta tono="verde" icono={<CheckCircle2 />}>Publicada{ficha.validador ? ` por ${ficha.validador}` : ''}</Etiqueta>
      <Boton onClick={onCerrar}>Cerrar</Boton>
    </>
  ) : (
    <>
      <Boton icono={<Save />} onClick={() => guardar()} cargando={ocupado === 'guardar'} disabled={!sucio || !!ocupado}>
        Guardar
      </Boton>
      <Boton variante="verde" icono={<Send />} onClick={publicar} cargando={ocupado === 'publicar'} disabled={!!ocupado}>
        Publicar ficha
      </Boton>
    </>
  ))

  return (
    <Modal abierto={capturaId !== null} titulo={publicada ? 'Ficha publicada' : 'Revisar la ficha'} onCerrar={cerrar} ancho pie={pie}>
      {error ? <ErrorCarga error={error} /> : !cap ? <Cargando texto="Abriendo la ficha…" /> : !ficha ? (
        <Aviso tono="amarillo">Esta captura todavía no tiene ficha.</Aviso>
      ) : (
        <div className="cap-ficha">
          {!publicada && (
            <Aviso tono="amarillo" titulo="Borrador preparado por CidIA">
              Lo ha ordenado el copiloto a partir de {origen}. Corrige lo que haga falta: nada se publica sin tu visto bueno.
            </Aviso>
          )}
          {ficha.estado === 'procesando' && (
            <Aviso>Publicada. CidIA la está añadiendo al conocimiento de tu departamento; en unos instantes el copiloto podrá citarla.</Aviso>
          )}
          {ficha.estado === 'error' && (
            <Aviso tono="alerta" titulo="No se ha podido indexar">
              La ficha está publicada, pero el copiloto todavía no la encuentra. Pide a tu jefe o a la administración que la reindexe desde Documentos.
            </Aviso>
          )}
          <Campo etiqueta="Título">
            {publicada ? <div className="cap-ficha-titulo"><BookOpen />{titulo}</div> : (
              <Entrada value={titulo} maxLength={300} onChange={(e) => { setTitulo(e.target.value); setSucio(true) }} />
            )}
          </Campo>
          <div className="campo">
            <div className="fila entre">
              <label className="etiqueta-campo">Contenido</label>
              {!publicada && (
                <Pestanas pestanas={[{ id: 'vista', texto: 'Vista previa', icono: <Eye size={15} /> },
                  { id: 'editar', texto: 'Editar', icono: <Pencil size={15} /> }]}
                  activa={modo} onCambio={setModo} />
              )}
            </div>
            {modo === 'editar' && !publicada ? (
              <>
                <Area value={contenido} rows={14} className="area mono-suave"
                  onChange={(e) => { setContenido(e.target.value); setSucio(true) }} />
                <div className="ayuda">Formato sencillo: «## Sección» para títulos y «- » para listas.</div>
              </>
            ) : (
              <div className="cap-ficha-vista">
                {contenido.trim() ? <TextoFormato texto={contenido} /> : <span className="apagado">Sin contenido todavía.</span>}
              </div>
            )}
          </div>
          <Campo etiqueta="Etiquetas" ayuda={publicada ? undefined : 'Palabras clave para encontrarla: máquinas, piezas, defectos… Pulsa Intro para añadir.'}>
            <div className="cap-etiquetas">
              {etiquetas.map((e) => (
                <span key={e} className="etiqueta azul">
                  <Tag />{e}
                  {!publicada && (
                    <button type="button" className="cap-quitar" aria-label={`Quitar ${e}`}
                      onClick={() => { setEtiquetas(etiquetas.filter((x) => x !== e)); setSucio(true) }}><X /></button>
                  )}
                </span>
              ))}
              {!publicada && (
                <input className="cap-etiqueta-nueva" value={nueva} placeholder="Añadir etiqueta" maxLength={40}
                  onChange={(e) => setNueva(e.target.value)} onKeyDown={teclaEtiqueta} onBlur={anadirEtiqueta} />
              )}
              {publicada && !etiquetas.length && <span className="apagado pequeno">Sin etiquetas</span>}
            </div>
          </Campo>
          {(cap.transcripcion?.texto || cap.original_url) && (
            <details className="cap-detalles">
              <summary>
                {cap.original_url ? 'Escuchar la nota y ver la transcripción' : 'Ver la transcripción original'}
                {cap.duracion ? ` (${mmss(cap.duracion)})` : ''}
              </summary>
              {cap.original_url && <audio controls preload="none" src={urlServidor(cap.original_url)} />}
              {cap.transcripcion?.texto && <p className="pre pequeno">{cap.transcripcion.texto}</p>}
            </details>
          )}
        </div>
      )}
      {dialogo}
    </Modal>
  )
}
