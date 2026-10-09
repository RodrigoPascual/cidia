// Lagunas: lo que el equipo pregunta y el copiloto todavía no sabe responder con respaldo.
// Cada laguna es una necesidad formativa concreta: se pide a quien lo sepa que aporte la
// respuesta, o se descarta si no procede.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Ban, Building2, CheckCircle2, Copy, HelpCircle, Inbox, MessageSquare, RotateCcw, Share2, Wrench } from 'lucide-react'
import { BASE_APP, EMBEBIDA, ErrorApi, fecha, get, hace, post } from '../../api'
import { useSesion } from '../../sesion'
import {
  Area, Boton, Cabecera, ErrorCarga, Esqueleto, Etiqueta, Modal, Pestanas, Selector, Tarjeta, Vacio,
  useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import { Plegable } from './comun'
import { copiarTexto, nombreTarea, veces, type EstadoLaguna, type Laguna, type RespuestaLagunas } from './tipos'
import './aportaciones.css'

type Orden = 'frecuencia' | 'reciente'

export default function Lagunas() {
  const { perfil } = useSesion()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()
  const [estado, setEstado] = useState<EstadoLaguna>('abierta')
  const [orden, setOrden] = useState<Orden>('frecuencia')
  const [ocupada, setOcupada] = useState<number | null>(null)
  const [compartir, setCompartir] = useState<{ laguna: Laguna; texto: string } | null>(null)
  const datos = useDatos((s) => get<RespuestaLagunas>(`/api/lagunas?estado=${estado}&orden=${orden}`, s), [estado, orden])

  const lista = datos.datos?.lagunas ?? []
  const maximo = Math.max(1, ...lista.map((l) => l.frecuencia))
  const c = datos.datos?.contadores
  const esAdmin = perfil?.rol === 'admin'

  async function cambiarEstado(l: Laguna, accion: 'descartar' | 'reabrir') {
    if (accion === 'descartar') {
      const ok = await confirmar('Descartar laguna',
        <>«{l.pregunta}» dejará de aparecer como pregunta pendiente para tu equipo. Podrás reabrirla cuando quieras.</>, true)
      if (!ok) return
    }
    setOcupada(l.id)
    try {
      await post(`/api/lagunas/${l.id}/${accion}`)
      avisar(accion === 'descartar' ? 'Laguna descartada.' : 'Laguna reabierta: vuelve a estar entre las preguntas pendientes.')
      datos.recargar()
    } catch (e) {
      avisarError(e)
      // Otra persona ya la cambió (o ya no existe): se muestra el estado real.
      if (e instanceof ErrorApi && (e.estado === 409 || e.estado === 404)) datos.recargar()
    } finally {
      setOcupada(null)
    }
  }

  function textoParaCompartir(l: Laguna): string {
    const dep = l.departamento?.nombre ?? perfil?.departamento?.nombre
    const enlace = EMBEBIDA ? '' : `\n${window.location.origin}${BASE_APP}/aportaciones?laguna=${l.id}`
    return [
      `Hola. En CidIA hay una pregunta que el copiloto todavía no sabe responder${dep ? ` en ${dep}` : ''}:`,
      `«${l.pregunta}»`,
      `Se ha preguntado ${veces(l.frecuencia)}${l.tarea ? ` (tarea ${nombreTarea(l.tarea)})` : ''}.`,
      `Si sabes la respuesta, entra en CidIA › Aportaciones › Preguntas pendientes y pulsa «Yo sé la respuesta». ¡Gracias!${enlace}`,
    ].join('\n')
  }

  async function copiar() {
    if (!compartir) return
    try {
      await copiarTexto(compartir.texto)
      avisar('Texto copiado. Pégalo en el chat o en el tablón de tu equipo.')
      setCompartir(null)
    } catch (e) {
      avisarError(e)
    }
  }

  return (
    <>
      <Cabecera
        antetitulo={<><HelpCircle size={14} /> Mi equipo</>}
        titulo="Lagunas de conocimiento"
        subtitulo="Lo que tu equipo pregunta y el copiloto todavía no sabe responder con la documentación."
      />

      <Tarjeta className="apo-explicacion" relleno={false}>
        <div className="apo-explicacion-cuerpo">
          <div className="apo-hero-icono alerta"><HelpCircle /></div>
          <div>
            <div className="negrita">¿Qué es una laguna?</div>
            <div className="pequeno apagado">
              Una pregunta que el copiloto no ha podido responder con respaldo. CidIA junta las preguntas parecidas y cuenta
              cuántas veces se han hecho: las más repetidas son las necesidades formativas más claras. Se cierra cuando alguien
              aporta la respuesta y la validas: desde ese momento el copiloto la responde citando a su autor.
            </div>
          </div>
        </div>
      </Tarjeta>

      <div className="apo-barra-filtros">
        <Pestanas<EstadoLaguna>
          activa={estado}
          onCambio={setEstado}
          pestanas={[
            { id: 'abierta', texto: 'Abiertas', icono: <HelpCircle size={16} />, contador: c?.abierta },
            { id: 'resuelta', texto: 'Resueltas', icono: <CheckCircle2 size={16} />, contador: c?.resuelta },
            { id: 'descartada', texto: 'Descartadas', icono: <Ban size={16} />, contador: c?.descartada },
          ]}
        />
        <Selector value={orden} onChange={(e) => setOrden(e.target.value as Orden)} aria-label="Ordenar"
          opciones={[{ valor: 'frecuencia', texto: 'Más preguntadas' }, { valor: 'reciente', texto: 'Más recientes' }]} />
      </div>

      {datos.cargando && !datos.datos ? (
        <div className="columna">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={96} />)}</div>
      ) : datos.error ? (
        <Tarjeta><ErrorCarga error={datos.error} reintentar={datos.recargar} /></Tarjeta>
      ) : lista.length === 0 ? (
        <Tarjeta>
          {estado === 'abierta' ? (
            <Vacio icono={<CheckCircle2 />} titulo="Sin lagunas abiertas">
              El copiloto está respondiendo con respaldo todo lo que pregunta tu equipo. Si algo se le escapa, aparecerá aquí.
            </Vacio>
          ) : estado === 'resuelta' ? (
            <Vacio icono={<MessageSquare />} titulo="Todavía no hay lagunas resueltas">
              Cuando valides una aportación que responde a una laguna, aparecerá aquí.
            </Vacio>
          ) : (
            <Vacio icono={<Ban />} titulo="No hay lagunas descartadas" />
          )}
        </Tarjeta>
      ) : (
        <div className={`columna ${datos.cargando ? 'apo-recargando' : ''}`}>
          {lista.map((l) => (
            <div key={l.id} className={`tarjeta apo-laguna estado-${l.estado}`}>
              <div className="apo-frecuencia" title={`Preguntada ${veces(l.frecuencia)}`}>
                <strong>{l.frecuencia}</strong>
                <span>{l.frecuencia === 1 ? 'vez' : 'veces'}</span>
              </div>
              <div className="crece apo-laguna-cuerpo">
                <div className="apo-laguna-pregunta">«{l.pregunta}»</div>
                <div className="apo-intensidad"><div style={{ width: `${(l.frecuencia / maximo) * 100}%` }} /></div>
                <div className="fila envolver diminuto apagado">
                  {l.ultima_vez && <span>Última vez {hace(l.ultima_vez)}</span>}
                  {l.primera_vez && <span>· desde el {fecha(l.primera_vez)}</span>}
                  {l.tarea && <Etiqueta icono={<Wrench />}>{nombreTarea(l.tarea)}</Etiqueta>}
                  {esAdmin && l.departamento?.nombre && <Etiqueta icono={<Building2 />}>{l.departamento.nombre}</Etiqueta>}
                </div>
                {l.respuestas_en_revision > 0 && (
                  <div className="fila envolver">
                    <Etiqueta tono="azul" icono={<Inbox />}>
                      {l.respuestas_en_revision === 1 ? '1 respuesta en revisión' : `${l.respuestas_en_revision} respuestas en revisión`}
                    </Etiqueta>
                    <Link to="/validar" className="pequeno">Revisar ahora</Link>
                  </div>
                )}
                {l.estado === 'resuelta' && l.aportacion && (
                  <div className="fila envolver">
                    <Etiqueta tono="verde" icono={<CheckCircle2 />}>Resuelta con «{l.aportacion.titulo ?? 'una aportación'}»</Etiqueta>
                    {l.aportacion.documento_id && (
                      <Link to={`/copiloto?pregunta=${encodeURIComponent(l.pregunta)}`} className="pequeno">
                        Probar la pregunta en el copiloto
                      </Link>
                    )}
                  </div>
                )}
                {l.ejemplos.length > 1 && (
                  <Plegable titulo={`Ver las ${l.ejemplos.length} formas en que se ha preguntado`}>
                    <ul className="apo-ejemplos">
                      {l.ejemplos.map((e, i) => (
                        <li key={i}>«{e.pregunta}»{e.fecha && <span className="apagado"> · {hace(e.fecha)}</span>}</li>
                      ))}
                    </ul>
                  </Plegable>
                )}
              </div>
              <div className="apo-laguna-acciones">
                {l.estado === 'abierta' ? (
                  <>
                    <Boton variante="primario" tamano="pequeno" icono={<Share2 />} disabled={ocupada === l.id}
                      onClick={() => setCompartir({ laguna: l, texto: textoParaCompartir(l) })}>
                      Pedir a alguien que la responda
                    </Boton>
                    <Boton variante="fantasma" tamano="pequeno" icono={<Ban />} cargando={ocupada === l.id}
                      onClick={() => cambiarEstado(l, 'descartar')}>
                      Descartar
                    </Boton>
                  </>
                ) : (
                  <Boton tamano="pequeno" icono={<RotateCcw />} cargando={ocupada === l.id} onClick={() => cambiarEstado(l, 'reabrir')}>
                    Reabrir
                  </Boton>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal abierto={!!compartir} titulo="Pedir a alguien que la responda" onCerrar={() => setCompartir(null)}
        pie={<>
          <Boton onClick={() => setCompartir(null)}>Cancelar</Boton>
          <Boton variante="primario" icono={<Copy />} onClick={copiar}>Copiar texto</Boton>
        </>}>
        <p className="apagado">
          Copia este mensaje y compártelo con quien creas que lo sabe, o en el canal de tu equipo. Puedes retocarlo antes.
        </p>
        <Area value={compartir?.texto ?? ''} rows={7} onChange={(e) => compartir && setCompartir({ ...compartir, texto: e.target.value })} />
      </Modal>
      {dialogo}
    </>
  )
}
