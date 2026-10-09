// Vista previa de un fichero del espacio de trabajo: texto, Markdown, CSV en tabla, imágenes y PDF.

import { useState } from 'react'
import { Download, EyeOff, X } from 'lucide-react'
import { fecha, get, hace, tamano, urlServidor } from '../../api'
import { Aviso, Boton, ErrorCarga, Esqueleto, TextoFormato, Vacio, useDatos } from '../../ui'
import { IconoElemento, leerCsv, type Elemento, type Fichero } from './comun'

function TablaCsv({ texto }: { texto: string }) {
  const { filas, mas } = leerCsv(texto)
  if (!filas.length) return <Vacio titulo="El fichero CSV está vacío" />
  const [cabecera, ...resto] = filas
  return (
    <>
      <div className="tabla-envoltorio espacio-csv">
        <table className="tabla">
          <thead><tr>{cabecera.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
          <tbody>
            {resto.map((f, i) => <tr key={i}>{cabecera.map((_, j) => <td key={j}>{f[j] ?? ''}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
      {mas && <div className="pequeno apagado mt-1">Se muestran las primeras {filas.length - 1} filas. Descárgalo para verlo entero.</div>}
    </>
  )
}

function Cuerpo({ f, comoTexto }: { f: Fichero; comoTexto: boolean }) {
  if (f.vista === 'imagen' && f.url) {
    return <div className="espacio-imagen"><img src={urlServidor(f.url)} alt={f.nombre} /></div>
  }
  if (f.vista === 'pdf' && f.url) {
    return <iframe className="espacio-pdf" src={urlServidor(f.url)} title={f.nombre} />
  }
  if (!f.es_texto || f.contenido === null) {
    return (
      <Vacio icono={<EyeOff />} titulo="Sin vista previa"
        accion={<a className="boton secundario" href={urlServidor(f.url_descarga)} download><Download />Descargar</a>}>
        Este tipo de fichero no se puede ver aquí. Descárgalo para abrirlo con su programa.
      </Vacio>
    )
  }
  if (!f.contenido.trim()) return <Vacio titulo="El fichero está vacío" />
  if (!comoTexto && f.vista === 'markdown') return <div className="espacio-markdown"><TextoFormato texto={f.contenido} /></div>
  if (!comoTexto && f.vista === 'csv') return <TablaCsv texto={f.contenido} />
  return <pre className="espacio-texto">{f.contenido}</pre>
}

export default function VistaPrevia({ elemento, onCerrar }: { elemento: Elemento; onCerrar: () => void }) {
  const [comoTexto, setComoTexto] = useState(false)
  const { datos: f, error, cargando, recargar } = useDatos(
    (senal) => get<Fichero>(`/api/espacio/fichero?ruta=${encodeURIComponent(elemento.ruta)}`, senal),
    [elemento.ruta, elemento.modificado],
  )
  const conVistas = elemento.vista === 'markdown' || elemento.vista === 'csv'
  return (
    <div className="espacio-vista">
      <div className="espacio-vista-cabecera">
        <IconoElemento el={elemento} tamano={22} />
        <div className="crece">
          <div className="negrita recortar" title={elemento.ruta}>{elemento.nombre}</div>
          <div className="diminuto apagado" title={fecha(elemento.modificado, true)}>
            {tamano(elemento.tamano)} · {hace(elemento.modificado)}
          </div>
        </div>
        {conVistas && (
          <div className="espacio-alternar" role="group" aria-label="Forma de verlo">
            <button className={!comoTexto ? 'activo' : ''} onClick={() => setComoTexto(false)}>
              {elemento.vista === 'csv' ? 'Tabla' : 'Vista'}
            </button>
            <button className={comoTexto ? 'activo' : ''} onClick={() => setComoTexto(true)}>Texto</button>
          </div>
        )}
        {elemento.url_descarga && (
          <a className="boton secundario pequeno icono" href={urlServidor(elemento.url_descarga)} download
            title="Descargar" aria-label="Descargar"><Download /></a>
        )}
        <Boton variante="fantasma" tamano="pequeno" icono={<X />} onClick={onCerrar} aria-label="Cerrar la vista previa" />
      </div>
      <div className="espacio-vista-cuerpo">
        {cargando && !f ? (
          <div className="columna">
            <Esqueleto alto={18} ancho="60%" />
            <Esqueleto alto={14} />
            <Esqueleto alto={14} ancho="85%" />
            <Esqueleto alto={14} ancho="70%" />
          </div>
        ) : error ? (
          <ErrorCarga error={error} reintentar={recargar} />
        ) : f ? (
          <>
            {f.truncado && (
              <div className="mb-2">
                <Aviso tono="amarillo">Es un fichero grande: solo se muestra el principio. Descárgalo para verlo entero.</Aviso>
              </div>
            )}
            <Cuerpo f={f} comoTexto={comoTexto} />
          </>
        ) : null}
      </div>
    </div>
  )
}
