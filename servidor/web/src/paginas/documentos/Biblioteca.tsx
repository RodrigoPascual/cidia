// Biblioteca de documentos: cifras, filtros, tabla paginada y recarga automática mientras se indexa.

import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download, FileText, FilterX, Globe, GraduationCap,
  ListChecks, Loader2, Pencil, RefreshCw, Search, Trash2, Upload,
} from 'lucide-react'
import { fecha, get, hace, tamano, urlServidor } from '../../api'
import { Boton, Dato, ErrorCarga, Esqueleto, Selector, Tarjeta, Vacio, useDatos } from '../../ui'
import type { AccionesDocumento } from './acciones'
import { EstadoEtiqueta, IconoTipo, NivelMinimo } from './comunes'
import { NOMBRE_ORIGEN, sePuedeReindexar, type Documento, type ListaDocumentos, type Opciones } from './tipos'

interface Filtros {
  texto: string
  departamento_id: string
  tipo: string
  estado: string
  es_formacion: boolean
  es_publico: boolean
}
const SIN_FILTROS: Filtros = { texto: '', departamento_id: '', tipo: '', estado: '', es_formacion: false, es_publico: false }
const POR_PAGINA = 25

function parametros(f: Filtros, pagina: number): string {
  const p = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) })
  if (f.texto.trim()) p.set('texto', f.texto.trim())
  if (f.departamento_id) p.set('departamento_id', f.departamento_id)
  if (f.tipo) p.set('tipo', f.tipo)
  if (f.estado) p.set('estado', f.estado)
  if (f.es_formacion) p.set('es_formacion', 'true')
  if (f.es_publico) p.set('es_publico', 'true')
  return p.toString()
}

function Fila({ d, maxNivel, acciones, onAbrir }: {
  d: Documento; maxNivel: number; acciones: AccionesDocumento; onAbrir: () => void
}) {
  const ocupado = acciones.ocupado === d.id
  const parar = (e: MouseEvent) => e.stopPropagation()
  return (
    <tr onClick={onAbrir} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onAbrir()}>
      <td>
        <div className="doc-titulo">
          <IconoTipo tipo={d.tipo} nombre={d.nombre_fichero} titulo={d.tipo_nombre} />
          <div className="textos">
            <div className="nombre">{d.titulo}</div>
            <div className="sub">
              {d.estado === 'error' ? (
                <span className="error recortar" title={d.mensaje_estado ?? undefined} style={{ maxWidth: 360 }}>
                  {d.mensaje_estado ?? 'No se ha podido indexar.'}
                </span>
              ) : (
                <>
                  <span>{d.nombre_fichero ?? NOMBRE_ORIGEN[d.origen] ?? d.tipo_nombre}</span>
                  {d.tamano ? <span>· {tamano(d.tamano)}</span> : null}
                  {d.estado === 'listo' && <span>· {d.fragmentos} {d.fragmentos === 1 ? 'fragmento' : 'fragmentos'}</span>}
                </>
              )}
            </div>
          </div>
        </div>
      </td>
      <td className="ocultar-m">{d.departamento ?? <span className="apagado">General</span>}</td>
      <td className="ocultar-m"><NivelMinimo nivel={d.nivel_minimo} nombre={d.nivel_nombre} maximo={maxNivel} /></td>
      <td className="col-icono ocultar-t" title={d.es_formacion ? 'Material de formación' : 'No es material de formación'}>
        <GraduationCap className={d.es_formacion ? 'si azul' : 'no'} />
      </td>
      <td className="col-icono ocultar-t" title={d.es_publico ? 'Público' : 'No es público'}>
        <Globe className={d.es_publico ? 'si' : 'no'} />
      </td>
      <td><EstadoEtiqueta estado={d.estado} mensaje={d.mensaje_estado} interrumpido={d.interrumpido} /></td>
      <td className="ocultar-t ocultar-p">{d.autor ?? d.subido_por ?? <span className="apagado">-</span>}</td>
      <td className="ocultar-m doc-fecha" title={fecha(d.creado, true)}><span className="pequeno">{hace(d.creado)}</span></td>
      <td className="doc-acciones" onClick={parar}>
        {d.url_descarga && (
          <a className="boton fantasma pequeno icono" href={urlServidor(d.url_descarga)} download
            title="Descargar original" aria-label={`Descargar ${d.titulo}`}><Download /></a>
        )}
        {d.puede_editar && (
          <>
            <Boton variante="fantasma" tamano="pequeno" icono={<Pencil />} title="Editar etiquetas"
              aria-label={`Editar ${d.titulo}`} onClick={() => acciones.editar(d)} />
            {sePuedeReindexar(d) && (
              <Boton variante="fantasma" tamano="pequeno" icono={<RefreshCw />} cargando={ocupado}
                title={d.indexando ? 'Se está indexando' : 'Reindexar'}
                aria-label={`Reindexar ${d.titulo}`} disabled={d.indexando} onClick={() => acciones.reindexar(d)} />
            )}
            {d.origen === 'instruccion' ? (
              <Link className="boton fantasma pequeno icono" to={`/instrucciones/${d.origen_id}`}
                title="Se gestiona desde Instrucciones" aria-label={`Abrir la instrucción ${d.titulo}`}><ListChecks /></Link>
            ) : (
              <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} title="Borrar" disabled={ocupado}
                aria-label={`Borrar ${d.titulo}`} onClick={() => acciones.borrar(d)} />
            )}
          </>
        )}
      </td>
    </tr>
  )
}

export default function Biblioteca({ opciones, version, acciones, onAbrir, onSubir }: {
  opciones: Opciones; version: number; acciones: AccionesDocumento; onAbrir: (id: number) => void; onSubir: () => void
}) {
  const [filtros, setFiltros] = useState<Filtros>(SIN_FILTROS)
  const [texto, setTexto] = useState('')
  const [pagina, setPagina] = useState(1)

  // Cualquier cambio de filtro vuelve a la primera página.
  const cambiar = (c: Partial<Filtros>) => { setFiltros((f) => ({ ...f, ...c })); setPagina(1) }

  // La búsqueda por texto espera a que se deje de escribir.
  useEffect(() => {
    const t = setTimeout(() => {
      if (texto !== filtros.texto) cambiar({ texto })
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto])

  const { datos, error, cargando, recargar } = useDatos<ListaDocumentos>(
    (s) => get<ListaDocumentos>(`/api/documentos?${parametros(filtros, pagina)}`, s),
    [filtros, pagina, version],
  )

  // Mientras haya documentos indexándose, la lista se refresca sola cada 4 s (sin atenuar la tabla).
  // Cuenta solo los que tienen un trabajo vivo: uno interrumpido no avanza y no merece sondeo.
  const procesando = datos?.resumen.indexando ?? 0
  useEffect(() => {
    if (!procesando) return
    const t = setInterval(recargar, 4000)
    return () => clearInterval(t)
  }, [procesando, recargar])

  // Si al borrar se vacía la última página, se vuelve a la anterior que tenga documentos.
  useEffect(() => {
    if (datos && !datos.documentos.length && datos.total > 0 && pagina > datos.paginas) setPagina(datos.paginas)
  }, [datos, pagina])

  const hayFiltros = JSON.stringify({ ...filtros, texto }) !== JSON.stringify(SIN_FILTROS)
  const limpiar = () => { setTexto(''); setFiltros(SIN_FILTROS); setPagina(1) }
  const maxNivel = Math.max(4, ...opciones.niveles.map((n) => n.orden))
  const r = datos?.resumen

  const cifra = (estado: string, icono: ReactNode, valor: number | undefined, etiqueta: string, tono?: 'verde' | 'alerta' | 'info') => (
    <button
      className={`doc-cifra ${filtros.estado === estado ? 'activa' : ''}`}
      onClick={() => cambiar({ estado: filtros.estado === estado ? '' : estado })}
      aria-pressed={filtros.estado === estado} title={estado ? `Ver solo: ${etiqueta.toLowerCase()}` : 'Ver todos'}
    >
      <Dato icono={icono} valor={valor ?? '·'} etiqueta={etiqueta} tono={tono} />
    </button>
  )

  return (
    <>
      <div className="doc-cifras">
        {cifra('', <FileText />, r?.total, 'Documentos')}
        {cifra('listo', <CheckCircle2 />, r?.listo, 'Listos para el copiloto', 'verde')}
        {cifra('procesando', <Loader2 className={procesando ? 'girando' : ''} />, r?.procesando, 'Indexándose', 'info')}
        {cifra('error', <AlertTriangle />, r?.error, 'Con error', 'alerta')}
      </div>

      <Tarjeta relleno={false}>
        <div className="doc-filtros">
          <div className="entrada-icono">
            <Search />
            <input className="entrada" value={texto} onChange={(e) => setTexto(e.target.value)}
              placeholder="Buscar por título, descripción o fichero" aria-label="Buscar documentos" />
          </div>
          <Selector
            value={filtros.departamento_id} onChange={(e) => cambiar({ departamento_id: e.target.value })}
            vacio="Todos los departamentos" aria-label="Departamento"
            opciones={[...opciones.departamentos.map((d) => ({ valor: d.id, texto: d.nombre })), { valor: 0, texto: 'Sin departamento' }]}
          />
          <Selector value={filtros.tipo} onChange={(e) => cambiar({ tipo: e.target.value })} vacio="Todos los tipos"
            aria-label="Tipo" opciones={opciones.tipos} />
          <button className={`doc-chip ${filtros.es_formacion ? 'activo' : ''}`} aria-pressed={filtros.es_formacion}
            onClick={() => cambiar({ es_formacion: !filtros.es_formacion })}>
            <GraduationCap /> Formación
          </button>
          <button className={`doc-chip ${filtros.es_publico ? 'activo' : ''}`} aria-pressed={filtros.es_publico}
            onClick={() => cambiar({ es_publico: !filtros.es_publico })}>
            <Globe /> Públicos
          </button>
          {hayFiltros && <Boton variante="fantasma" tamano="pequeno" icono={<FilterX />} onClick={limpiar}>Limpiar</Boton>}
        </div>

        {error && !datos ? (
          <ErrorCarga error={error} reintentar={recargar} />
        ) : !datos ? (
          <div className="tarjeta-cuerpo columna">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="fila"><Esqueleto alto={36} ancho={36} /><div className="crece columna" style={{ gap: 6 }}>
                <Esqueleto alto={14} ancho="55%" /><Esqueleto alto={11} ancho="30%" /></div></div>
            ))}
          </div>
        ) : datos.documentos.length === 0 ? (
          hayFiltros ? (
            <Vacio icono={<Search />} titulo="Ningún documento coincide" accion={<Boton icono={<FilterX />} onClick={limpiar}>Quitar filtros</Boton>}>
              Prueba con otras palabras o quita algún filtro.
            </Vacio>
          ) : (
            <Vacio icono={<Upload />} titulo="Aún no hay documentos" accion={<Boton variante="primario" icono={<Upload />} onClick={onSubir}>Subir conocimiento</Boton>}>
              Sube procedimientos, manuales, hojas de cálculo, notas de voz o fotos de carteles. CidIA los trocea y el
              copiloto los cita al responder, siempre respetando departamento y nivel.
            </Vacio>
          )
        ) : (
          <>
            <div className={`tabla-envoltorio ${cargando && !procesando ? 'doc-actualizando' : ''}`}>
              <table className="tabla doc-tabla">
                <thead>
                  <tr>
                    <th>Documento</th>
                    <th className="ocultar-m">Departamento</th>
                    <th className="ocultar-m">Nivel mínimo</th>
                    <th className="col-icono ocultar-t" title="Material de formación">Form.</th>
                    <th className="col-icono ocultar-t" title="Público">Púb.</th>
                    <th>Estado</th>
                    <th className="ocultar-t ocultar-p">Autor</th>
                    <th className="ocultar-m">Subido</th>
                    <th><span className="sr-solo">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {datos.documentos.map((d) => (
                    <Fila key={d.id} d={d} maxNivel={maxNivel} acciones={acciones} onAbrir={() => onAbrir(d.id)} />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="doc-paginacion">
              <span>
                {datos.total === 1 ? '1 documento' : `${(datos.pagina - 1) * datos.por_pagina + 1}-${Math.min(datos.total, datos.pagina * datos.por_pagina)} de ${datos.total} documentos`}
              </span>
              {datos.paginas > 1 && (
                <div className="fila">
                  <Boton tamano="pequeno" icono={<ChevronLeft />} disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>Anterior</Boton>
                  <span className="pequeno">Página {datos.pagina} de {datos.paginas}</span>
                  <Boton tamano="pequeno" disabled={pagina >= datos.paginas} onClick={() => setPagina(pagina + 1)}>
                    Siguiente <ChevronRight />
                  </Boton>
                </div>
              )}
            </div>
          </>
        )}
      </Tarjeta>
    </>
  )
}
