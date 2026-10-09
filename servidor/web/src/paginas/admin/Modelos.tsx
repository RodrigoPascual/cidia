// Administración · Modelos permitidos: la lista que el gateway consulta antes de cada petición.
// Los modelos locales se cruzan con lo que hay descargado en el servidor; los de la nube
// quedan bloqueados mientras la política de la empresa no los permita.

import { useState } from 'react'
import { Brain, CheckCircle2, Cloud, Download, Eye, Info, Lock, Plus, RefreshCw, Server, ShieldCheck, Star, Trash2 } from 'lucide-react'
import { get, post, put, del } from '../../api'
import {
  Area, Aviso, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Interruptor, Modal, Selector, Tarjeta, Vacio,
  useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import type { ModeloIA, RespuestaModelos } from './tipos'
import './admin.css'

const GRUPOS: { clave: string; titulo: string; nota?: string; filtro: (m: ModeloIA) => boolean }[] = [
  { clave: 'chat', titulo: 'Chat y copiloto', filtro: (m) => m.ubicacion === 'local' && m.tipo === 'chat' },
  { clave: 'vision', titulo: 'Visión (fotos del modo planta)', filtro: (m) => m.ubicacion === 'local' && m.tipo === 'vision' },
  {
    clave: 'embeddings', titulo: 'Búsqueda por significado',
    nota: 'La fija el servidor: los documentos están indexados con ella y cambiarla obliga a reindexarlos todos.',
    filtro: (m) => m.ubicacion === 'local' && m.tipo === 'embeddings',
  },
  { clave: 'otros', titulo: 'Otros', filtro: (m) => m.ubicacion === 'local' && !['chat', 'vision', 'embeddings'].includes(m.tipo) },
  { clave: 'nube', titulo: 'En la nube', filtro: (m) => m.ubicacion === 'nube' },
]

export default function Modelos() {
  const { datos, error, recargar, setDatos, cargando } = useDatos((s) => get<RespuestaModelos>('/api/admin/modelos', s), [])
  const [anadir, setAnadir] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState<number | null>(null)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  const cambiar = async (m: ModeloIA, cambio: { permitido?: boolean; predeterminado?: boolean }, mensaje: string) => {
    setOcupado(m.id)
    try {
      const r = await put<RespuestaModelos>(`/api/admin/modelos/${m.id}`, cambio)
      setDatos(r)
      avisar(mensaje)
    } catch (e) {
      avisarError(e)
    } finally {
      setOcupado(null)
    }
  }
  const quitar = async (m: ModeloIA) => {
    const ok = await confirmar('¿Quitar el modelo de la lista?',
      <>«{m.nombre}» dejará de aparecer aquí. No se borra del servidor: puedes volver a añadirlo cuando quieras.</>, true)
    if (!ok) return
    try {
      setDatos(await del<RespuestaModelos>(`/api/admin/modelos/${m.id}`))
      avisar('Modelo quitado de la lista')
    } catch (e) {
      avisarError(e)
    }
  }

  return (
    <>
      <Cabecera
        antetitulo={<><Brain size={14} /> Administración</>}
        titulo="Modelos permitidos"
        subtitulo="Qué modelos de IA puede usar CidIA y para qué. Solo la administración puede cambiarlo y cada cambio queda registrado."
        acciones={<>
          <Boton variante="fantasma" icono={<RefreshCw className={cargando ? 'girando' : ''} />} onClick={recargar}>Comprobar servidor</Boton>
          <Boton variante="primario" icono={<Plus />} onClick={() => setAnadir('')}>Añadir modelo local</Boton>
        </>}
      />

      <div className="columna mb-2">
        <Aviso>
          <span className="fila envolver" style={{ gap: 6 }}>
            <ShieldCheck size={15} /> El gateway consulta esta lista antes de cada petición. En la app, las personas no ven la
            configuración de modelos ni de claves y no pueden añadir las suyas.
          </span>
        </Aviso>
        {datos && !datos.servidor.ok && (
          <Aviso tono="alerta" titulo="El servidor de modelos no responde">
            No se puede saber qué modelos están descargados. Revisa el estado en «Sistema».
            {datos.servidor.error && <div className="diminuto mono mt-1">{datos.servidor.error}</div>}
          </Aviso>
        )}
      </div>

      {error && !datos ? (
        <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
      ) : !datos ? (
        <Tarjeta><div className="columna">{[0, 1, 2, 3, 4].map((i) => <Esqueleto key={i} alto={44} />)}</div></Tarjeta>
      ) : !datos.modelos.length ? (
        <Tarjeta>
          <Vacio icono={<Brain />} titulo="No hay modelos en la lista" accion={<Boton variante="primario" icono={<Plus />} onClick={() => setAnadir('')}>Añadir modelo local</Boton>}>
            Mientras la lista esté vacía, CidIA usa los modelos configurados en el servidor.
          </Vacio>
        </Tarjeta>
      ) : (
        <Tarjeta relleno={false}>
          <div className="tabla-envoltorio">
            <table className="tabla adm-tabla">
              <thead>
                <tr><th>Modelo</th><th>Dónde se ejecuta</th><th>Quién lo usa</th><th>Estado</th><th>Predeterminado</th><th aria-label="Acciones" /></tr>
              </thead>
              {GRUPOS.map((g) => {
                const filas = datos.modelos.filter(g.filtro)
                if (!filas.length) return null
                return (
                  <tbody key={g.clave}>
                    <tr className="adm-grupo-fila">
                      <td colSpan={6}>{g.titulo}{g.nota && <span className="adm-grupo-nota"> · {g.nota}</span>}</td>
                    </tr>
                    {filas.map((m) => (
                      <FilaModelo key={m.id} m={m} ocupado={ocupado === m.id}
                        onPermitir={(v) => cambiar(m, { permitido: v }, v ? `«${m.nombre}» permitido` : `«${m.nombre}» desactivado`)}
                        onPredeterminado={() => cambiar(m, { predeterminado: true }, `«${m.nombre}» es ahora el predeterminado`)}
                        onQuitar={() => quitar(m)} />
                    ))}
                  </tbody>
                )
              })}
            </table>
          </div>
        </Tarjeta>
      )}

      {datos && datos.servidor.sin_registrar.length > 0 && (
        <Tarjeta className="mt-2" titulo="Descargados en el servidor y aún sin registrar" icono={<Download size={18} />}>
          <p className="pequeno apagado">Estos modelos ya están en el servidor de la empresa. Añádelos a la lista para poder permitirlos.</p>
          <div className="adm-chips">
            {datos.servidor.sin_registrar.map((ref) => (
              <button key={ref} className="adm-chip-boton" onClick={() => setAnadir(ref)}><Plus /> {ref}</button>
            ))}
          </div>
        </Tarjeta>
      )}

      {anadir !== null && datos && (
        <ModalAnadir inicial={anadir} sugerencias={datos.servidor.sin_registrar} descargados={datos.servidor.ok ? datos.servidor.descargados : null}
          onCerrar={() => setAnadir(null)}
          onCreado={(r) => { setDatos(r); setAnadir(null) }} />
      )}
      {dialogo}
    </>
  )
}

function FilaModelo({ m, ocupado, onPermitir, onPredeterminado, onQuitar }: {
  m: ModeloIA; ocupado: boolean; onPermitir: (v: boolean) => void; onPredeterminado: () => void; onQuitar: () => void
}) {
  return (
    <tr>
      <td>
        <div className="negrita">{m.nombre}</div>
        {m.ubicacion === 'local' && m.ref !== m.nombre && <div className="adm-modelo-ref">{m.ref}</div>}
        <div className="fila envolver mt-1" style={{ gap: 5 }}>
          {m.soporta_vision && m.tipo !== 'vision' && <Etiqueta tono="azul" icono={<Eye />}>Ve imágenes</Etiqueta>}
          {m.descargado === true && <Etiqueta tono="verde" icono={<CheckCircle2 />}>Descargado</Etiqueta>}
          {m.descargado === false && <Etiqueta tono="naranja" icono={<Download />} title={`Descárgalo en el servidor con «ollama pull ${m.ref}»`}>No descargado</Etiqueta>}
        </div>
        {m.descripcion && m.ubicacion === 'local' && <div className="diminuto apagado mt-1">{m.descripcion}</div>}
      </td>
      <td>
        <span className="adm-donde">
          {m.ubicacion === 'local' ? <Server /> : <Cloud />}
          {m.donde}
        </span>
      </td>
      <td className={m.uso === 'Nadie' ? 'apagado' : ''}>{m.uso}</td>
      <td>
        {m.bloqueado ? (
          <div className="columna" style={{ gap: 6, alignItems: 'flex-start' }}>
            <Interruptor activo={false} onCambio={() => {}} deshabilitado />
            <Etiqueta tono="roja" icono={<Lock />} title="Los datos saldrían del servidor de la empresa">bloqueado por la política de la empresa</Etiqueta>
          </div>
        ) : m.indexa_documentos && m.permitido ? (
          <span title="Los documentos están indexados con este modelo. Se cambia en la configuración del servidor.">
            <Interruptor activo onCambio={() => {}} deshabilitado etiqueta={<span className="pequeno">Permitido · indexa los documentos</span>} />
          </span>
        ) : (
          <Interruptor activo={m.permitido} onCambio={onPermitir} deshabilitado={ocupado}
            etiqueta={<span className="pequeno">{m.permitido ? 'Permitido' : 'Desactivado'}</span>} />
        )}
      </td>
      <td>
        {m.predeterminado ? (
          <Etiqueta tono="amarilla" icono={<Star />}>predeterminado</Etiqueta>
        ) : m.tipo === 'embeddings' && !m.indexa_documentos ? (
          <span className="diminuto apagado" title="El modelo de búsqueda lo fija el servidor">Fijado por el servidor</span>
        ) : !m.bloqueado ? (
          <Boton tamano="pequeno" variante="fantasma" icono={<Star />} disabled={ocupado || m.descargado === false} onClick={onPredeterminado}
            title={m.descargado === false ? 'Descárgalo antes en el servidor' : 'Usarlo por defecto para este tipo'}>
            Hacer predeterminado
          </Boton>
        ) : null}
      </td>
      <td>
        {m.ubicacion === 'local' && !m.permitido && (
          <Boton tamano="pequeno" variante="fantasma" icono={<Trash2 />} onClick={onQuitar} aria-label="Quitar de la lista" title="Quitar de la lista" />
        )}
      </td>
    </tr>
  )
}

function ModalAnadir({ inicial, sugerencias, descargados, onCerrar, onCreado }: {
  inicial: string; sugerencias: string[]; descargados: string[] | null; onCerrar: () => void; onCreado: (r: RespuestaModelos) => void
}) {
  const [ref, setRef] = useState(inicial)
  const [nombre, setNombre] = useState('')
  const [tipo, setTipo] = useState<'chat' | 'embeddings' | 'vision'>(/embed/i.test(inicial) ? 'embeddings' : 'chat')
  const [vision, setVision] = useState(false)
  const [permitir, setPermitir] = useState(true)
  const [descripcion, setDescripcion] = useState('')
  const [enviando, setEnviando] = useState(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const limpio = ref.trim()
  const noDescargado = descargados !== null && limpio && !descargados.includes(limpio) && !descargados.includes(`${limpio}:latest`)

  const crear = async () => {
    setEnviando(true)
    try {
      const r = await post<RespuestaModelos>('/api/admin/modelos', {
        ref: limpio, nombre: nombre || null, tipo, soporta_vision: vision || tipo === 'vision', permitido: permitir, descripcion: descripcion || null,
      })
      avisar(`«${r.creado?.nombre ?? limpio}» añadido a la lista`)
      onCreado(r)
    } catch (e) {
      avisarError(e)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal abierto titulo="Añadir un modelo local" onCerrar={onCerrar}
      pie={<>
        <Boton onClick={onCerrar}>Cancelar</Boton>
        <Boton variante="primario" icono={<Plus />} cargando={enviando} disabled={!limpio} onClick={crear}>Añadir</Boton>
      </>}>
      <Campo etiqueta="Referencia en el servidor" ayuda="El nombre exacto del modelo en Ollama, por ejemplo qwen3.5:9b.">
        <Entrada value={ref} onChange={(e) => setRef(e.target.value)} list="cidia-modelos-sugeridos" autoFocus className="entrada mono" placeholder="qwen3.5:9b" />
        <datalist id="cidia-modelos-sugeridos">{sugerencias.map((s) => <option key={s} value={s} />)}</datalist>
      </Campo>
      {noDescargado && (
        <div className="mb-2">
          <Aviso tono="amarillo" titulo="Aún no está en el servidor">
            Puedes añadirlo a la lista, pero no se podrá usar hasta que se descargue en el servidor con
            <span className="mono"> ollama pull {limpio}</span>.
          </Aviso>
        </div>
      )}
      <div className="adm-form-rejilla">
        <Campo etiqueta="Nombre visible (opcional)">
          <Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Qwen3.5 9B" maxLength={150} />
        </Campo>
        <Campo etiqueta="Para qué se usa">
          <Selector value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)} opciones={[
            { valor: 'chat', texto: 'Chat y copiloto' },
            { valor: 'vision', texto: 'Visión (fotos)' },
            { valor: 'embeddings', texto: 'Búsqueda por significado' },
          ]} />
        </Campo>
      </div>
      <Campo etiqueta="Descripción (opcional)">
        <Area rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Para qué lo queréis, pruebas, reserva…" />
      </Campo>
      <div className="columna">
        {tipo === 'chat' && <Interruptor activo={vision} onCambio={setVision} etiqueta="También entiende imágenes (multimodal)" />}
        <Interruptor activo={permitir} onCambio={setPermitir} etiqueta="Permitirlo ya" />
      </div>
      <div className="fila pequeno apagado mt-2" style={{ gap: 6 }}><Info size={14} /> Solo se pueden añadir modelos que se ejecutan en el servidor de la empresa.</div>
    </Modal>
  )
}
