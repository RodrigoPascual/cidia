// Instrucciones de trabajo agrupadas por tarea: cada tarea con sus versiones (borrador, publicada
// u obsoleta), autor, revisor y fecha. Desde aquí se crea una instrucción nueva.

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight, FilePlus2, ListChecks, Plus, Search, ShieldAlert, Video } from 'lucide-react'
import { fecha, get, post } from '../../api'
import { useSesion } from '../../sesion'
import {
  Aviso, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Modal, Pestanas, Selector, Tarjeta, Vacio,
  useAvisarError, useAvisos, useDatos,
} from '../../ui'
import SelectorTarea, { useTareas } from './SelectorTarea'
import { ESTADOS, textoTarea, type EstadoInstruccion, type Instruccion } from './tipos'
import './instrucciones.css'

type Filtro = 'todas' | EstadoInstruccion

export default function Instrucciones() {
  const navegar = useNavigate()
  const { perfil } = useSesion()
  const { datos, error, cargando, recargar } = useDatos((s) => get<Instruccion[]>('/api/instrucciones', s), [])
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const [busqueda, setBusqueda] = useState('')
  const [departamento, setDepartamento] = useState('')
  const [nueva, setNueva] = useState(false)

  const lista = datos ?? []
  // Sin datos todavía, las pestañas no muestran contadores (un «0» mientras carga confunde).
  const cuenta = (e: EstadoInstruccion) => (datos ? lista.filter((i) => i.estado === e).length : undefined)
  const departamentos = useMemo(() => {
    const m = new Map<number, string>()
    for (const i of lista) if (i.tarea.departamento_id) m.set(i.tarea.departamento_id, i.tarea.departamento ?? '')
    return [...m.entries()].map(([valor, texto]) => ({ valor, texto })).sort((a, b) => a.texto.localeCompare(b.texto))
  }, [lista])

  // Filtrado en el cliente (la lista ya llega limitada a lo que la persona puede gestionar).
  const grupos = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    const visibles = lista.filter((i) =>
      (filtro === 'todas' || i.estado === filtro)
      && (!departamento || String(i.tarea.departamento_id) === departamento)
      && (!q || [i.titulo, i.codigo, i.tarea.nombre, i.tarea.codigo, i.autor?.nombre].some((x) => x?.toLowerCase().includes(q))))
    const porTarea = new Map<number, Instruccion[]>()
    for (const i of visibles) porTarea.set(i.tarea_id, [...(porTarea.get(i.tarea_id) ?? []), i])
    return [...porTarea.values()]
      .map((v) => v.sort((a, b) => b.version - a.version))
      .sort((a, b) => a[0].tarea.nombre.localeCompare(b[0].tarea.nombre))
  }, [lista, filtro, busqueda, departamento])

  return (
    <>
      <Cabecera
        antetitulo={<><ListChecks size={14} />Conocimiento</>}
        titulo="Instrucciones de trabajo"
        subtitulo="Cada tarea con sus versiones: borradores por revisar, la vigente que usa el copiloto y el historial."
        acciones={<>
          <Boton icono={<Video />} onClick={() => navegar('/captura')}>Capturar desde vídeo</Boton>
          <Boton variante="primario" icono={<Plus />} onClick={() => setNueva(true)}>Nueva instrucción</Boton>
        </>}
      />

      <div className="ins-filtros">
        <div className="entrada-icono crece">
          <Search />
          <Entrada value={busqueda} onChange={(e) => setBusqueda(e.target.value)} placeholder="Buscar por tarea, código, título o autor" />
        </div>
        {perfil?.rol === 'admin' && departamentos.length > 1 && (
          <Selector opciones={departamentos} vacio="Todos los departamentos" value={departamento}
            onChange={(e) => setDepartamento(e.target.value)} style={{ maxWidth: 260 }} />
        )}
      </div>
      <Pestanas<Filtro>
        activa={filtro}
        onCambio={setFiltro}
        pestanas={[
          { id: 'todas', texto: 'Todas', contador: datos ? lista.length : undefined },
          { id: 'borrador', texto: 'Borradores', contador: cuenta('borrador') },
          { id: 'publicada', texto: 'Publicadas', contador: cuenta('publicada') },
          { id: 'obsoleta', texto: 'Obsoletas', contador: cuenta('obsoleta') },
        ]}
      />

      {error ? <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
        : cargando && !datos ? (
          <div className="columna">{[0, 1, 2].map((i) => <Esqueleto key={i} alto={120} />)}</div>
        ) : !lista.length ? (
          <Tarjeta>
            <Vacio icono={<ListChecks />} titulo="Aún no hay instrucciones"
              accion={<div className="fila envolver" style={{ justifyContent: 'center' }}>
                <Boton variante="primario" icono={<Video />} onClick={() => navegar('/captura')}>Grabar un vídeo de la tarea</Boton>
                <Boton icono={<FilePlus2 />} onClick={() => setNueva(true)}>Escribirla a mano</Boton>
              </div>}>
              La forma más rápida es grabar al experto haciendo la tarea mientras la explica: CidIA propone los pasos, con imagen y clip.
            </Vacio>
          </Tarjeta>
        ) : !grupos.length ? (
          <Tarjeta><Vacio icono={<Search />} titulo="Nada coincide con el filtro">Prueba con otras palabras o con otra pestaña.</Vacio></Tarjeta>
        ) : (
          <div className="columna ins-grupos">
            {grupos.map((versiones) => <GrupoTarea key={versiones[0].tarea_id} versiones={versiones} />)}
          </div>
        )}

      <NuevaInstruccion abierto={nueva} onCerrar={() => setNueva(false)} />
    </>
  )
}

function GrupoTarea({ versiones }: { versiones: Instruccion[] }) {
  const navegar = useNavigate()
  const t = versiones[0].tarea
  const vigente = versiones.find((v) => v.estado === 'publicada')
  return (
    <Tarjeta relleno={false} className="ins-grupo">
      <div className="ins-grupo-cabecera">
        <div className="crece">
          <div className="fila envolver">
            {t.codigo && <span className="ins-codigo">{t.codigo}</span>}
            <h3 className="recortar">{t.nombre}</h3>
          </div>
          <div className="pequeno apagado">{[t.departamento, t.puesto].filter(Boolean).join(' · ')}</div>
        </div>
        {vigente ? <Etiqueta tono="verde">Vigente v{vigente.version}</Etiqueta> : <Etiqueta>Sin versión publicada</Etiqueta>}
      </div>
      <div className="tabla-envoltorio">
        <table className="tabla ins-tabla">
          <thead>
            <tr>
              <th>Versión</th><th>Título</th><th>Estado</th><th className="ins-col-oculta">Autor</th>
              <th className="ins-col-oculta">Revisor</th><th>Fecha</th><th className="ins-col-oculta">Pasos</th><th aria-label="Abrir" />
            </tr>
          </thead>
          <tbody>
            {versiones.map((i) => (
              <tr key={i.id} className="pulsable" onClick={() => navegar(`/instrucciones/${i.id}`)}>
                <td><span className="ins-version">{i.codigo ?? ''} v{i.version}</span></td>
                <td className="ins-col-titulo"><span className="recortar">{i.titulo}</span></td>
                <td><Etiqueta tono={ESTADOS[i.estado].tono}>{ESTADOS[i.estado].texto}</Etiqueta></td>
                <td className="ins-col-oculta">{i.autor?.nombre ?? '-'}</td>
                <td className="ins-col-oculta">{i.revisor?.nombre ?? '-'}</td>
                <td className="pequeno">{fecha(i.publicada_en ?? i.creada)}</td>
                <td className="ins-col-oculta">
                  <span className="fila" style={{ gap: 6 }}>
                    {i.n_pasos}
                    {i.pasos_criticos > 0 && <span className="ins-marca critico" title={`${i.pasos_criticos} pasos críticos`}><AlertTriangle />{i.pasos_criticos}</span>}
                    {i.pasos_seguridad > 0 && <span className="ins-marca seguridad" title={`${i.pasos_seguridad} pasos de seguridad`}><ShieldAlert />{i.pasos_seguridad}</span>}
                  </span>
                </td>
                <td className="ins-col-flecha"><ChevronRight size={18} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Tarjeta>
  )
}

/** Alta de una instrucción: según la tarea, se crea un borrador nuevo, se abre el que ya hay o se
 *  parte de la versión publicada. */
function NuevaInstruccion({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const navegar = useNavigate()
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const tareas = useTareas()
  const [tareaId, setTareaId] = useState('')
  const [titulo, setTitulo] = useState('')
  const [creando, setCreando] = useState(false)
  const tarea = tareas.datos?.find((t) => String(t.id) === tareaId)

  async function crear() {
    if (!tarea) return
    setCreando(true)
    try {
      if (tarea.borrador) {
        navegar(`/instrucciones/${tarea.borrador.id}`)
      } else if (tarea.publicada) {
        const r = await post<Instruccion>(`/api/instrucciones/${tarea.publicada.id}/nueva-version`)
        avisar(`Versión ${r.version} creada como borrador a partir de la v${tarea.publicada.version}.`)
        navegar(`/instrucciones/${r.id}`)
      } else {
        const r = await post<Instruccion>('/api/instrucciones', { tarea_id: tarea.id, titulo: titulo.trim() || tarea.nombre })
        avisar('Borrador creado. Añade los pasos.')
        navegar(`/instrucciones/${r.id}`)
      }
    } catch (e) {
      avisarError(e)
      setCreando(false)
    }
  }

  const texto = !tarea ? 'Crear borrador' : tarea.borrador ? `Abrir el borrador v${tarea.borrador.version}`
    : tarea.publicada ? `Crear la versión ${tarea.publicada.version + 1}` : 'Crear borrador'

  return (
    <Modal abierto={abierto} titulo="Nueva instrucción" onCerrar={onCerrar}
      pie={<>
        <Boton onClick={onCerrar}>Cancelar</Boton>
        <Boton variante="primario" onClick={crear} disabled={!tarea} cargando={creando}>{texto}</Boton>
      </>}>
      {tareas.error ? <ErrorCarga error={tareas.error} reintentar={tareas.recargar} /> : (
        <>
          <Campo etiqueta="Tarea">
            <SelectorTarea tareas={tareas.datos} valor={tareaId} onCambio={setTareaId} cargando={tareas.cargando} vacio="Elige la tarea" />
          </Campo>
          {tarea?.borrador ? (
            <Aviso tono="amarillo">Esta tarea ya tiene un borrador (v{tarea.borrador.version}). Ábrelo para seguir editándolo.</Aviso>
          ) : tarea?.publicada ? (
            <Aviso>La versión vigente es la v{tarea.publicada.version}. La nueva versión partirá de ella para que solo cambies lo necesario.</Aviso>
          ) : (
            <Campo etiqueta="Título" ayuda="Por defecto, el nombre de la tarea.">
              <Entrada value={titulo} maxLength={300} onChange={(e) => setTitulo(e.target.value)} placeholder={tarea?.nombre ?? ''} />
            </Campo>
          )}
          {tareas.datos && !tareas.datos.length && (
            <Aviso tono="amarillo">No hay tareas en tu departamento. Pide a la administración que las dé de alta o captura un vídeo con un tema libre.</Aviso>
          )}
          {tarea && <div className="pequeno apagado mt-1">{textoTarea(tarea)} · {tarea.departamento}</div>}
        </>
      )}
    </Modal>
  )
}
