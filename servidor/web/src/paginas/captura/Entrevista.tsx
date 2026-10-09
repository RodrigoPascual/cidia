// Entrevista guiada: el copiloto pregunta, una cosa cada vez y siguiendo un guion, y el experto
// responde escribiendo o por voz. Al terminar se genera una ficha (o un borrador de instrucción).

import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle2, Circle, CircleDot, FileText, Lightbulb, ListChecks, Loader2, MessagesSquare, Mic,
  RotateCcw, Send, SkipForward,
} from 'lucide-react'
import { enviarFormulario, get, post } from '../../api'
import { useSesion } from '../../sesion'
import {
  Aviso, BarraProgreso, Boton, Cabecera, Cargando, ErrorCarga, LogoCidia, Tarjeta, Vacio, useAvisarError,
  useAvisos, useConfirmar, useDatos,
} from '../../ui'
import GrabadorVoz from './GrabadorVoz'
import RevisarFicha from './RevisarFicha'
import { enProceso, type Captura, type Mensaje, type TemaGuion } from './tipos'
import './captura.css'

export default function Entrevista() {
  const { id } = useParams()
  const navegar = useNavigate()
  const { perfil } = useSesion()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const { datos: cap, error, cargando, recargar, setDatos } = useDatos((s) => get<Captura>(`/api/captura/${id}`, s), [id])
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [pendiente, setPendiente] = useState<Mensaje | null>(null)
  const [finalizando, setFinalizando] = useState(false)
  const [ficha, setFicha] = useState<number | null>(null)
  const fin = useRef<HTMLDivElement>(null)
  const area = useRef<HTMLTextAreaElement>(null)

  // Mientras se genera el borrador, se consulta cada 3 s.
  const procesando = !!cap && enProceso(cap)
  useEffect(() => {
    if (!procesando) return
    const t = setInterval(() => {
      get<Captura>(`/api/captura/${id}`).then(setDatos).catch(() => { /* siguiente ciclo */ })
    }, 3000)
    return () => clearInterval(t)
  }, [procesando, id, setDatos])

  // La conversación siempre muestra lo último.
  const n = cap?.conversacion?.length ?? 0
  useEffect(() => {
    fin.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [n, pendiente, enviando])

  if (cargando && !cap) return <Cargando texto="Abriendo la entrevista…" />
  if (error) return <ErrorCarga error={error} reintentar={recargar} />
  if (!cap) return null
  if (cap.tipo !== 'entrevista') {
    return <Vacio icono={<MessagesSquare />} titulo="Esta captura no es una entrevista"
      accion={<Boton onClick={() => navegar('/captura')}>Volver a Captura</Boton>} />
  }

  const temas = cap.entrevista?.temas ?? []
  const titulos: Record<string, string> = Object.fromEntries(temas.map((t) => [t.clave, t.titulo]))
  const terminada = !!cap.entrevista?.terminada
  const respuestas = cap.entrevista?.respuestas ?? 0
  // Su jefe o la administración pueden abrirla, pero solo quien la hace puede responderla.
  const propia = !cap.autor || cap.autor.id === perfil?.id
  const enCurso = cap.estado === 'en_curso' && propia

  async function mandar(cuerpo: { texto?: string; saltar?: boolean }, provisional: Mensaje) {
    setEnviando(true)
    setPendiente(provisional)
    try {
      setDatos(await post<Captura>(`/api/captura/${id}/entrevista/responder`, cuerpo))
      return true
    } catch (e) {
      avisarError(e)
      return false
    } finally {
      setEnviando(false)
      setPendiente(null)
    }
  }

  async function enviarTexto() {
    const t = texto.trim()
    if (!t || enviando) return
    setTexto('')
    if (area.current) area.current.style.height = 'auto'
    const ok = await mandar({ texto: t }, { rol: 'experto', texto: t, tema: '', momento: '' })
    if (!ok) setTexto(t)
    area.current?.focus()
  }

  async function responderVoz(audio: Blob) {
    setEnviando(true)
    setPendiente({ rol: 'experto', texto: 'Transcribiendo tu respuesta…', tema: '', momento: '', voz: true })
    const fd = new FormData()
    fd.append('fichero', audio, audio.type.includes('ogg') ? 'respuesta.ogg' : 'respuesta.webm')
    try {
      setDatos(await enviarFormulario<Captura>(`/api/captura/${id}/entrevista/responder-audio`, fd))
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
      setPendiente(null)
    }
  }

  function teclear(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      enviarTexto()
    }
  }

  function crecer(e: ChangeEvent<HTMLTextAreaElement>) {
    setTexto(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(180, e.target.scrollHeight)}px`
  }

  async function terminar(generar: 'ficha' | 'instruccion') {
    if (!cap) return
    const quedan = temas.filter((t) => t.estado === 'pendiente' || t.estado === 'actual').length
    if (!terminada && quedan > 0) {
      const ok = await confirmar('Terminar la entrevista', (
        <p>Quedan {quedan} {quedan === 1 ? 'tema' : 'temas'} del guion sin tratar. Puedes terminar igualmente:
          el borrador se hará con lo que has contado y podrás completarlo al revisarlo.</p>
      ))
      if (!ok) return
    }
    setFinalizando(true)
    try {
      setDatos(await post<Captura>(`/api/captura/${id}/entrevista/finalizar`, { generar }))
      avisar(generar === 'ficha' ? 'Entrevista terminada. Preparando la ficha…' : 'Entrevista terminada. Preparando el borrador…')
    } catch (e) {
      avisarError(e)
    } finally {
      setFinalizando(false)
    }
  }

  async function reintentar() {
    try {
      setDatos(await post<Captura>(`/api/captura/${id}/reintentar`))
    } catch (e) {
      avisarError(e)
    }
  }

  return (
    <>
      <Cabecera
        antetitulo={<><MessagesSquare size={14} />Entrevista guiada</>}
        titulo={cap.tarea?.nombre ?? cap.titulo ?? 'Entrevista'}
        subtitulo="Responde con tus palabras, escribiendo o por voz. El copiloto hace una pregunta cada vez y se adapta a lo que cuentas."
        acciones={<Boton variante="fantasma" icono={<ArrowLeft />} onClick={() => navegar('/captura')}>Volver a Captura</Boton>}
      />
      <div className="cap-entrevista">
        <Tarjeta relleno={false} className="cap-chat">
          <div className="cap-mensajes" aria-live="polite">
            {(cap.conversacion ?? []).map((m, i) => <Burbuja key={i} m={m} titulos={titulos} />)}
            {pendiente && <Burbuja m={pendiente} titulos={titulos} provisional />}
            {enviando && (
              <div className="cap-msg copiloto">
                <LogoCidia tamano={30} />
                <div className="cap-globo cap-pensando" aria-label="El copiloto está pensando"><span /><span /><span /></div>
              </div>
            )}
            <div ref={fin} />
          </div>

          {enCurso ? (
            <div className="cap-chat-pie">
              {terminada && (
                <Aviso tono="exito">Ya habéis repasado todo el guion. Añade algo más si quieres o termina para generar la ficha.</Aviso>
              )}
              <div className="chat-entrada">
                <textarea ref={area} rows={1} value={texto} onChange={crecer} onKeyDown={teclear} disabled={enviando}
                  placeholder="Escribe tu respuesta… (Intro para enviar, Mayús+Intro para otra línea)" aria-label="Tu respuesta" />
                <GrabadorVoz compacto ocupado={enviando} maxSegundos={300} onAudio={(a) => responderVoz(a)} />
                {!terminada && (
                  <Boton variante="fantasma" icono={<SkipForward />} disabled={enviando} title="Saltar esta pregunta"
                    aria-label="Saltar esta pregunta"
                    onClick={() => mandar({ saltar: true }, { rol: 'experto', texto: '', tema: '', momento: '', saltada: true })} />
                )}
                <Boton variante="primario" icono={<Send />} onClick={enviarTexto} disabled={!texto.trim() || enviando}
                  aria-label="Enviar la respuesta" />
              </div>
            </div>
          ) : (
            <div className="cap-chat-pie">
              {cap.estado === 'en_curso' ? (
                <Aviso>Entrevista en curso de {cap.autor?.nombre ?? 'otra persona'}. Solo quien la hace puede responderla.</Aviso>
              ) : procesando ? (
                <div className="cap-chat-final">
                  <Loader2 className="girando" />
                  <div className="crece">
                    <div className="negrita">Preparando el borrador con lo que has contado…</div>
                    <BarraProgreso valor={cap.progreso} tono="amarilla" />
                  </div>
                </div>
              ) : cap.estado === 'error' ? (
                <Aviso tono="alerta" titulo="No se ha podido generar el borrador">
                  <div>{cap.mensaje}</div>
                  <Boton tamano="pequeno" icono={<RotateCcw />} className="mt-1" onClick={reintentar}>Reintentar</Boton>
                </Aviso>
              ) : cap.borrador ? (
                <div className="cap-chat-final listo">
                  <CheckCircle2 />
                  <div className="crece">
                    <div className="negrita">{cap.borrador.tipo === 'ficha' ? 'La ficha está lista para revisar' : 'El borrador de la instrucción está listo'}</div>
                    <div className="pequeno apagado">Nada se publica sin tu visto bueno.</div>
                  </div>
                  {cap.borrador.tipo === 'ficha' ? (
                    <Boton variante="primario" icono={<FileText />} onClick={() => setFicha(cap.id)}>
                      {cap.borrador.estado === 'publicada' ? 'Ver la ficha' : 'Revisar la ficha'}
                    </Boton>
                  ) : (
                    <Boton variante="primario" icono={<ListChecks />} onClick={() => navegar(`/instrucciones/${cap.borrador!.id}`)}>
                      Abrir el borrador
                    </Boton>
                  )}
                </div>
              ) : (
                <Aviso>El borrador que generó esta entrevista se ha eliminado. La conversación se conserva aquí.</Aviso>
              )}
            </div>
          )}
        </Tarjeta>

        <aside className="cap-lado">
          <Tarjeta titulo="Guion" icono={<ListChecks size={18} />}>
            <BarraProgreso valor={cap.progreso} tono="amarilla" />
            <div className="pequeno apagado mt-1">{temas.filter((t) => t.estado === 'hecho' || t.estado === 'saltado').length} de {temas.length} temas</div>
            <ol className="cap-guion">
              {temas.map((t) => <TemaLinea key={t.clave} t={t} />)}
            </ol>
          </Tarjeta>
          {enCurso && (
            <div className="columna">
              <Boton variante="primario" bloque icono={<FileText />} onClick={() => terminar('ficha')}
                cargando={finalizando} disabled={!respuestas || enviando}>
                Terminar y generar ficha
              </Boton>
              <Boton bloque icono={<ListChecks />} onClick={() => terminar('instruccion')}
                disabled={!respuestas || enviando || finalizando}>
                Generar borrador de instrucción
              </Boton>
              <div className="pequeno apagado">La ficha recoge trucos, errores y criterios; la instrucción, los pasos en orden.</div>
            </div>
          )}
          <div className="cap-consejo">
            <Lightbulb />
            <div className="pequeno">Cuenta lo que harías con las manos y por qué. Lo más valioso son los trucos y los errores que solo se aprenden con los años.</div>
          </div>
        </aside>
      </div>
      <RevisarFicha capturaId={ficha} onCerrar={() => setFicha(null)} onCambio={setDatos} />
      {dialogo}
    </>
  )
}

function Burbuja({ m, titulos, provisional }: { m: Mensaje; titulos: Record<string, string>; provisional?: boolean }) {
  if (m.rol === 'copiloto') {
    return (
      <div className="cap-msg copiloto">
        <LogoCidia tamano={30} />
        <div className="cap-globo">
          {titulos[m.tema] && <div className="cap-msg-tema">{titulos[m.tema]}</div>}
          {m.texto}
        </div>
      </div>
    )
  }
  return (
    <div className={`cap-msg experto ${provisional ? 'provisional' : ''} ${m.saltada ? 'saltada' : ''}`}>
      {m.saltada ? <><SkipForward size={14} /> Pregunta saltada</> : <>{m.voz && <Mic size={14} className="cap-msg-voz" />}{m.texto}</>}
    </div>
  )
}

function TemaLinea({ t }: { t: TemaGuion }) {
  const icono = t.estado === 'hecho' ? <CheckCircle2 /> : t.estado === 'actual' ? <CircleDot />
    : t.estado === 'saltado' ? <SkipForward /> : <Circle />
  return <li className={t.estado}>{icono}<span>{t.titulo}</span>{t.estado === 'saltado' && <span className="diminuto apagado">saltado</span>}</li>
}
