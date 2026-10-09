// Ficha de un documento: etiquetas, datos, acciones y los fragmentos tal como los guarda el motor.

import { useEffect, useState } from 'react'
import {
  Download, GraduationCap, Globe, Layers, Pencil, RefreshCw, ScanText, Trash2, Workflow,
} from 'lucide-react'
import { fecha, get, hace, tamano, urlServidor } from '../../api'
import { Aviso, BarraProgreso, Boton, ErrorCarga, Esqueleto, Etiqueta, Vacio, useDatos } from '../../ui'
import type { AccionesDocumento } from './acciones'
import { Cajon, EstadoEtiqueta, IconoTipo, MetaFragmento, NivelMinimo } from './comunes'
import { NOMBRE_ORIGEN, type DetalleDocumento as Detalle, type FragmentoMuestra } from './tipos'

const ESTADO_TRABAJO: Record<string, string> = {
  pendiente: 'En cola', en_curso: 'En curso', completado: 'Completado', error: 'Error',
}

function Fragmento({ f, internas }: { f: FragmentoMuestra; internas: boolean }) {
  const [abierto, setAbierto] = useState(false)
  const largo = f.texto.length > 320
  return (
    <div className="doc-fragmento">
      <div className="cabeza">
        <span className="orden">#{f.orden + 1}</span>
        <MetaFragmento metadatos={f.metadatos} internas={internas} />
        <span className="crece" />
        <span title={f.con_vector ? 'Tiene vector para la búsqueda por significado' : 'Sin vector local (lo tiene el motor externo)'}>
          {f.caracteres} car.{f.con_vector ? ' · con vector' : ''}
        </span>
      </div>
      <div className={`texto ${largo && !abierto ? 'recortado' : ''}`}>{f.texto}</div>
      {largo && (
        <button className="doc-enlace mt-1" onClick={() => setAbierto(!abierto)}>{abierto ? 'Ver menos' : 'Ver todo'}</button>
      )}
    </div>
  )
}

export default function DetalleDocumento({ documentoId, version, acciones, onCerrar }: {
  documentoId: number | null; version: number; acciones: AccionesDocumento; onCerrar: () => void
}) {
  const [limite, setLimite] = useState(12)
  const [internas, setInternas] = useState(false)
  const [verTexto, setVerTexto] = useState(false)
  const { datos: d, error, cargando, recargar } = useDatos<Detalle | null>(
    (s) => (documentoId ? get<Detalle>(`/api/documentos/${documentoId}?fragmentos=${limite}`, s) : Promise.resolve(null)),
    [documentoId, limite, version],
  )

  useEffect(() => { setLimite(12); setVerTexto(false) }, [documentoId])

  // Mientras se indexa, se consulta cada 4 s.
  useEffect(() => {
    if (!d?.indexando) return
    const t = setInterval(recargar, 4000)
    return () => clearInterval(t)
  }, [d?.indexando, recargar])

  const actual = d && d.id === documentoId ? d : null
  const trabajo = actual?.trabajos[0]
  const ocupado = actual ? acciones.ocupado === actual.id : false

  const cabecera = actual ? (
    <div className="fila arriba">
      <IconoTipo tipo={actual.tipo} nombre={actual.nombre_fichero} grande titulo={actual.tipo_nombre} />
      <div className="crece">
        <h2>{actual.titulo}</h2>
        <div className="fila envolver mt-1" style={{ gap: 6 }}>
          <EstadoEtiqueta estado={actual.estado} mensaje={actual.mensaje_estado} interrumpido={actual.interrumpido} />
          <Etiqueta>{actual.departamento ?? 'Sin departamento'}</Etiqueta>
          <Etiqueta><NivelMinimo nivel={actual.nivel_minimo} nombre={actual.nivel_nombre} /></Etiqueta>
          {actual.es_formacion && <Etiqueta tono="azul" icono={<GraduationCap />}>Formación</Etiqueta>}
          {actual.es_publico && <Etiqueta tono="verde" icono={<Globe />}>Público</Etiqueta>}
        </div>
      </div>
    </div>
  ) : (
    <div className="columna"><Esqueleto alto={22} ancho="70%" /><Esqueleto alto={20} ancho="45%" /></div>
  )

  const pie = actual && (
    <>
      {actual.url_descarga && (
        <a className="boton secundario pequeno" href={urlServidor(actual.url_descarga)} download>
          <Download /> Descargar original
        </a>
      )}
      {actual.puede_editar && (
        <>
          <Boton tamano="pequeno" icono={<Pencil />} onClick={() => acciones.editar(actual)}>Editar etiquetas</Boton>
          <Boton tamano="pequeno" icono={<RefreshCw />} cargando={ocupado} disabled={actual.indexando}
            onClick={() => acciones.reindexar(actual)}>Reindexar</Boton>
          <span className="crece" />
          <Boton tamano="pequeno" variante="peligro" icono={<Trash2 />} disabled={ocupado}
            onClick={() => acciones.borrar(actual)}>Borrar</Boton>
        </>
      )}
    </>
  )

  return (
    <Cajon abierto={documentoId !== null} onCerrar={onCerrar} cabecera={cabecera} pie={pie || undefined}>
      {error && !actual ? <ErrorCarga error={error} reintentar={recargar} /> : !actual ? (
        <div className="columna">{[1, 2, 3, 4].map((i) => <Esqueleto key={i} alto={18} />)}<Esqueleto alto={90} /></div>
      ) : (
        <>
          {actual.estado === 'error' && (
            <div className="mb-2">
              <Aviso tono="alerta" titulo="No se ha podido indexar">
                {actual.mensaje_estado ?? 'Error desconocido.'}
                {actual.puede_editar && ' Corrige el problema y pulsa «Reindexar».'}
              </Aviso>
            </div>
          )}
          {actual.estado === 'procesando' && !actual.interrumpido && (
            <div className="mb-2">
              <Aviso tono="amarillo" titulo="Indexando">
                {trabajo?.mensaje ?? 'CidIA está leyendo y troceando el documento.'}
                <div className="mt-1"><BarraProgreso valor={trabajo?.progreso ?? 5} tono="amarilla" /></div>
              </Aviso>
            </div>
          )}
          {actual.interrumpido && (
            <div className="mb-2">
              <Aviso tono="alerta" titulo="Indexado interrumpido">
                El indexado se cortó antes de terminar (por ejemplo, porque se reinició el servidor) y no seguirá solo.
                {actual.puede_editar ? ' Pulsa «Reindexar» para terminarlo.' : ' Avisa a quien gestiona este documento.'}
              </Aviso>
            </div>
          )}
          {!actual.puede_editar && (
            <div className="mb-2">
              <Aviso>
                {actual.departamento
                  ? `Es un documento público de ${actual.departamento}: puedes consultarlo, pero no cambiarlo.`
                  : 'Es un documento público general: puedes consultarlo, pero solo la administración puede cambiarlo.'}
              </Aviso>
            </div>
          )}
          {actual.descripcion && <p className="apagado">{actual.descripcion}</p>}

          <dl className="doc-ficha">
            {actual.nombre_fichero && (
              <><dt>Fichero</dt><dd>{actual.nombre_fichero}{actual.tamano ? ` · ${tamano(actual.tamano)}` : ''}</dd></>
            )}
            <dt>Tipo</dt><dd>{actual.tipo_nombre}{actual.version > 1 ? ` · versión ${actual.version}` : ''}</dd>
            <dt>Origen</dt><dd>{NOMBRE_ORIGEN[actual.origen] ?? actual.origen}</dd>
            {actual.autor && <><dt>Autor</dt><dd>{actual.autor}</dd></>}
            {actual.validador && <><dt>Validado por</dt><dd>{actual.validador}</dd></>}
            {actual.subido_por && actual.subido_por !== actual.autor && <><dt>Subido por</dt><dd>{actual.subido_por}</dd></>}
            <dt>Creado</dt><dd>{fecha(actual.creado, true)}</dd>
            {actual.actualizado && <><dt>Actualizado</dt><dd>{hace(actual.actualizado)}</dd></>}
            <dt>Fragmentos</dt><dd>{actual.fragmentos_total}</dd>
            <dt>Motor</dt>
            <dd>
              {actual.motor === 'weknora' ? 'WeKnora' : 'Propio (PostgreSQL)'}
              {actual.motor_id && <span className="mono apagado"> · {actual.motor_id}</span>}
            </dd>
          </dl>

          {actual.texto_extraido && (
            <div className="mt-3">
              <div className="fila entre">
                <div className="doc-seccion-titulo"><ScanText /> Texto {actual.tipo === 'audio' ? 'transcrito' : actual.tipo === 'imagen' ? 'descrito' : 'de origen'}</div>
                <button className="doc-enlace" onClick={() => setVerTexto(!verTexto)}>{verTexto ? 'Ocultar' : 'Mostrar'}</button>
              </div>
              {verTexto && (
                <div className="doc-texto-extraido">
                  {actual.texto_extraido}{actual.texto_extraido_recortado ? '…' : ''}
                </div>
              )}
            </div>
          )}

          <div className="mt-3">
            <div className="fila entre">
              <div className="doc-seccion-titulo"><Layers /> Fragmentos indexados</div>
              <label className="casilla pequeno">
                <input type="checkbox" checked={internas} onChange={(e) => setInternas(e.target.checked)} />
                Metadatos internos
              </label>
            </div>
            {actual.fragmentos_muestra.length === 0 ? (
              <Vacio icono={<Layers />} titulo="Sin fragmentos">
                {actual.estado === 'procesando' ? 'Aparecerán cuando termine el indexado.' : 'Este documento no tiene texto indexado.'}
              </Vacio>
            ) : (
              <>
                {actual.fragmentos_muestra.map((f) => <Fragmento key={f.id} f={f} internas={internas} />)}
                {actual.fragmentos_total > actual.fragmentos_muestra.length && (
                  <div className="fila entre mt-1 pequeno apagado">
                    <span>Mostrando {actual.fragmentos_muestra.length} de {actual.fragmentos_total}</span>
                    <Boton tamano="pequeno" cargando={cargando} onClick={() => setLimite(200)}>
                      {actual.fragmentos_total > 200 ? 'Ver los 200 primeros' : 'Ver todos'}
                    </Boton>
                  </div>
                )}
              </>
            )}
          </div>

          {actual.trabajos.length > 0 && (
            <div className="mt-3">
              <div className="doc-seccion-titulo"><Workflow /> Últimos indexados</div>
              {actual.trabajos.map((t) => (
                <div key={t.id} className="doc-trabajo">
                  <Etiqueta tono={t.estado === 'completado' ? 'verde' : t.estado === 'error' ? 'roja' : 'amarilla'}>
                    {ESTADO_TRABAJO[t.estado] ?? t.estado}
                  </Etiqueta>
                  <span className="crece recortar apagado" title={t.mensaje ?? undefined}>{t.mensaje ?? ''}</span>
                  <span className="diminuto apagado">{hace(t.actualizado ?? t.creado)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Cajon>
  )
}
