// Consola de depuración de la búsqueda: qué fragmentos encuentra una pregunta y con qué puntuación.

import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  Building2, CheckCircle2, Database, GraduationCap, Globe, HelpCircle, Info, ScanSearch, Search, ShieldCheck,
  Type, UserRound, XCircle,
} from 'lucide-react'
import { post } from '../../api'
import { Boton, Campo, Etiqueta, Selector, Tarjeta, Vacio, useAvisarError } from '../../ui'
import { MetaFragmento, NivelMinimo } from './comunes'
import { numero, type Opciones, type RespuestaBusqueda, type ResultadoBusqueda } from './tipos'

const EJEMPLOS = [
  '¿Qué hago si se atasca la prensa?',
  '¿Qué EPI necesito en la línea 2?',
  '¿A cuánto se aprietan los tornillos de la brida?',
  'IT-023',
]

/** Marca en el texto las palabras de la pregunta (por su raíz, para casar «atasca» con «atasco»). */
function resaltar(texto: string, consulta: string): ReactNode[] {
  const raices = Array.from(new Set(
    (consulta.toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}\-./]*/gu) ?? [])
      .filter((p) => p.length >= 3 || /\d/.test(p))
      .map((p) => p.slice(0, Math.max(3, Math.min(p.length, 5))).replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')),
  ))
  if (!raices.length) return [texto]
  const patron = new RegExp(`(${raices.map((r) => `${r}[\\p{L}\\p{N}]*`).join('|')})`, 'giu')
  return texto.split(patron).map((trozo, i) => (i % 2 === 1 ? <mark key={i}>{trozo}</mark> : trozo))
}

function Similitud({ valor, umbral }: { valor: number | null; umbral: number }) {
  if (valor === null) return <span className="apagado">sin dato</span>
  const ok = valor >= umbral
  return (
    <span className={`doc-similitud ${ok ? 'ok' : ''}`} title={`Umbral de respaldo: ${numero(umbral)}`}>
      <span className="pista">
        <span className="relleno" style={{ width: `${Math.max(0, Math.min(1, valor)) * 100}%` }} />
        <span className="umbral" style={{ left: `calc(${umbral * 100}% - 1px)` }} />
      </span>
      <span className="valor">{numero(valor)}</span>
    </span>
  )
}

function Resultado({ r, consulta, umbral, onAbrir }: {
  r: ResultadoBusqueda; consulta: string; umbral: number; onAbrir: (id: number) => void
}) {
  const [abierto, setAbierto] = useState(false)
  const meta = r.metadatos
  const largo = r.texto.length > 420
  return (
    <div className={`doc-resultado ${r.supera_umbral ? 'respaldo' : ''}`}>
      <div className="pos" title={r.supera_umbral ? 'Supera el umbral de respaldo' : 'Por debajo del umbral'}>{r.posicion}</div>
      <div style={{ minWidth: 0 }}>
        <div className="fila entre arriba envolver" style={{ gap: 8 }}>
          {r.puede_abrir ? (
            <button className="doc-enlace titulo" onClick={() => onAbrir(r.documento_id)}>{r.titulo}</button>
          ) : (
            <span className="titulo">{r.titulo}</span>
          )}
          <div className="fila envolver" style={{ gap: 6 }}>
            {r.departamento && <Etiqueta icono={<Building2 />}>{r.departamento}</Etiqueta>}
            {r.nivel_minimo !== null && <Etiqueta><NivelMinimo nivel={r.nivel_minimo} nombre={r.nivel_nombre} compacto /></Etiqueta>}
            {r.es_formacion && <Etiqueta tono="azul" icono={<GraduationCap />}>Formación</Etiqueta>}
            {r.es_publico && <Etiqueta tono="verde" icono={<Globe />}>Público</Etiqueta>}
          </div>
        </div>
        <div className="fila envolver mt-1" style={{ gap: 6 }}>
          <MetaFragmento metadatos={meta} />
          {meta.coincidencia_texto === true && <span className="doc-meta"><Type size={12} /> Coincide por palabras</span>}
        </div>
        <div className={`texto ${largo && !abierto ? 'recortado' : ''}`}>{resaltar(r.texto, consulta)}</div>
        {largo && <button className="doc-enlace mt-1" onClick={() => setAbierto(!abierto)}>{abierto ? 'Ver menos' : 'Ver todo'}</button>}
        <div className="doc-puntos">
          <span title="Fusión RRF de la búsqueda por significado y por palabras: ordena los resultados">
            RRF <span className="valor">{numero(r.puntuacion, 4)}</span>
          </span>
          <span className="fila" style={{ gap: 6 }} title="Parecido semántico con la pregunta (0 a 1)">
            Similitud <Similitud valor={r.similitud} umbral={umbral} />
          </span>
          {typeof meta.puntuacion_motor === 'number' && (
            <span title="Puntuación que da WeKnora (con reranker, si lo hay)">
              WeKnora <span className="valor">{numero(meta.puntuacion_motor as number, 3)}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ProbarBusqueda({ opciones, onAbrir }: { opciones: Opciones; onAbrir: (id: number) => void }) {
  const avisarError = useAvisarError()
  const [consulta, setConsulta] = useState('')
  const [como, setComo] = useState('')
  const [k, setK] = useState(String(Math.min(20, opciones.fragmentos_por_consulta || 6)))
  const [buscando, setBuscando] = useState(false)
  const [resultado, setResultado] = useState<RespuestaBusqueda | null>(null)
  // Las cantidades habituales más la que usa el copiloto en este servidor (máximo 20, como el servidor).
  const cantidades = useMemo(
    () => Array.from(new Set([3, 6, 10, 20, Math.min(20, opciones.fragmentos_por_consulta || 6)])).sort((a, b) => a - b),
    [opciones.fragmentos_por_consulta],
  )

  const personas = useMemo(() => [
    { valor: '', texto: 'Yo mismo' },
    { valor: 'invitado', texto: 'Invitado sin sesión' },
    ...(opciones.personas ?? []).map((p) => ({
      valor: String(p.id), texto: `${p.nombre}${p.departamento ? ` · ${p.departamento}` : ''}${p.nivel ? ` · ${p.nivel}` : ''}`,
    })),
  ], [opciones.personas])

  async function buscar(pregunta = consulta) {
    const q = pregunta.trim()
    if (!q) return
    setConsulta(q)
    setBuscando(true)
    try {
      const cuerpo: Record<string, unknown> = { consulta: q, k: Number(k) }
      if (como === 'invitado') cuerpo.como_invitado = true
      else if (como) cuerpo.como_usuario_id = Number(como)
      setResultado(await post<RespuestaBusqueda>('/api/documentos/probar-busqueda', cuerpo))
    } catch (e) {
      avisarError(e)
    } finally {
      setBuscando(false)
    }
  }

  const enviar = (e: FormEvent) => { e.preventDefault(); buscar() }

  return (
    <div className="doc-busqueda">
      <div className="columna" style={{ gap: 16 }}>
        <Tarjeta>
          <form onSubmit={enviar}>
            <div className="doc-pregunta">
              <div className="entrada-icono">
                <Search />
                <input className="entrada" value={consulta} onChange={(e) => setConsulta(e.target.value)} maxLength={2000}
                  placeholder="Escribe una pregunta como la haría alguien en planta" aria-label="Pregunta" autoFocus />
              </div>
              <Boton variante="primario" tamano="grande" icono={<ScanSearch />} cargando={buscando} disabled={!consulta.trim()} type="submit">
                Buscar
              </Boton>
            </div>
            <div className="fila envolver mt-2" style={{ gap: 12, alignItems: 'flex-end' }}>
              {opciones.es_admin && (
                <div style={{ flex: '1 1 260px' }}>
                  <Campo etiqueta="Buscar como">
                    <Selector value={como} onChange={(e) => setComo(e.target.value)} opciones={personas} />
                  </Campo>
                </div>
              )}
              <div style={{ flex: '0 0 170px' }}>
                <Campo etiqueta="Fragmentos">
                  <Selector value={k} onChange={(e) => setK(e.target.value)}
                    opciones={cantidades.map((n) => ({ valor: String(n), texto: `${n} fragmentos` }))} />
                </Campo>
              </div>
            </div>
          </form>
          {!resultado && (
            <div className="doc-ejemplos">
              {EJEMPLOS.map((e) => (
                <button key={e} type="button" className="doc-chip" onClick={() => buscar(e)}>{e}</button>
              ))}
            </div>
          )}
        </Tarjeta>

        {!resultado ? (
          <Tarjeta>
            <Vacio icono={<ScanSearch />} titulo="Comprueba qué encontraría el copiloto">
              Escribe una pregunta y verás los fragmentos que llegarían al copiloto, en orden, con su puntuación y si
              bastan para responder con respaldo. Así puedes detectar documentos mal etiquetados o que faltan.
            </Vacio>
          </Tarjeta>
        ) : (
          <Tarjeta relleno={false}>
            <div className="tarjeta-cabecera">
              <div className="doc-resumen-busqueda" style={{ margin: 0 }}>
                <strong>{resultado.resultados.length} {resultado.resultados.length === 1 ? 'fragmento' : 'fragmentos'}</strong>
                <span className="apagado pequeno">en {resultado.duracion_ms} ms · motor {resultado.motor === 'weknora' ? 'WeKnora' : 'propio'}</span>
              </div>
              {resultado.con_respaldo
                ? <Etiqueta tono="verde" icono={<CheckCircle2 />}>Con respaldo</Etiqueta>
                : <Etiqueta tono="roja" icono={<XCircle />}>Sin respaldo</Etiqueta>}
            </div>
            {resultado.resultados.length === 0 ? (
              <Vacio icono={<HelpCircle />} titulo="No ha encontrado nada">
                Con este alcance no hay fragmentos parecidos. El copiloto diría que no tiene esa información y la
                anotaría como laguna.
              </Vacio>
            ) : (
              <>
                {!resultado.con_respaldo && (
                  <div className="tarjeta-cuerpo" style={{ paddingBottom: 0 }}>
                    <div className="aviso amarillo">
                      <Info />
                      <div>Ningún fragmento llega al umbral de similitud ({numero(resultado.umbral_respaldo)}): el copiloto
                        respondería que no tiene información suficiente y lo anotaría como laguna.</div>
                    </div>
                  </div>
                )}
                {resultado.resultados.map((r) => (
                  <Resultado key={`${r.posicion}-${r.fragmento_id}`} r={r} consulta={resultado.consulta}
                    umbral={resultado.umbral_respaldo} onAbrir={onAbrir} />
                ))}
              </>
            )}
          </Tarjeta>
        )}
      </div>

      <div className="columna" style={{ gap: 16 }}>
        {resultado && (
          <Tarjeta titulo="Alcance de la búsqueda" icono={<ShieldCheck size={17} />}>
            <div className="doc-alcance">
              <div className="linea"><UserRound /><span><strong>{resultado.como.nombre}</strong>
                {resultado.como.departamento ? ` · ${resultado.como.departamento}` : ''}
                {resultado.como.nivel ? ` · ${resultado.como.nivel}` : ''}</span></div>
              {resultado.alcance.map((a) => (
                <div key={a.texto} className="linea">
                  {a.tipo === 'publico' ? <Globe /> : a.tipo === 'formacion' ? <GraduationCap /> : <Building2 />}
                  <span>{a.texto}</span>
                </div>
              ))}
            </div>
            {resultado.ambitos && (
              <>
                <div className="separador" />
                <div className="doc-seccion-titulo"><Database /> Búsquedas en WeKnora</div>
                {resultado.ambitos.length === 0 ? (
                  <p className="pequeno apagado">Ninguna: aún no hay bases para este alcance.</p>
                ) : resultado.ambitos.map((a) => (
                  <div key={`${a.base}-${a.descripcion}`} className="mb-1">
                    <div className="pequeno">{a.descripcion}</div>
                    <div className="doc-ambito">{a.base}</div>
                  </div>
                ))}
              </>
            )}
          </Tarjeta>
        )}
        <Tarjeta titulo="Cómo leer los resultados" icono={<Info size={17} />}>
          <div className="pequeno columna" style={{ gap: 8 }}>
            <p><strong>Orden (RRF).</strong> Combina la búsqueda por significado y la búsqueda por palabras exactas
              (códigos como IT-023 o S4). Cuanto más alto, antes aparece.</p>
            <p><strong>Similitud.</strong> Va de 0 a 1 e indica cuánto se parece el fragmento a la pregunta. La raya
              negra marca el umbral ({numero(opciones.umbral_respaldo)}): por debajo, el copiloto no lo usa como respaldo.</p>
            <p className="apagado">La búsqueda respeta siempre los permisos: solo salen documentos que esa persona
              puede ver por departamento, nivel, formación o por ser públicos.</p>
          </div>
        </Tarjeta>
      </div>
    </div>
  )
}
