// Respuesta del copiloto con sus citas: texto con [n] pulsables, chips de fuentes y detalle.

import { useState } from 'react'
import { BookMarked, ExternalLink, Loader2 } from 'lucide-react'
import { urlServidor } from '../../api'
import { Aviso, Modal, TextoFormato } from '../../ui'
import { etiquetaFuente, limpiarCitas, type Fuente, type Respuesta } from './copiloto'

export function RespuestaCopiloto({ respuesta, pensando = 'Buscando en la documentación…' }: {
  respuesta: Respuesta
  pensando?: string
}) {
  const [abierta, setAbierta] = useState<Fuente | null>(null)
  const fuentes = respuesta.fuentes ?? []
  const abrirCita = (n: number) => setAbierta(fuentes.find((f, i) => (f.n ?? i + 1) === n) ?? null)
  const texto = limpiarCitas(respuesta.texto, fuentes.map((f, i) => f.n ?? i + 1))
  return (
    <>
      {!respuesta.texto && !respuesta.terminado && (
        <div className="fila apagado pequeno"><Loader2 className="girando" size={16} /> {pensando}</div>
      )}
      {texto && <TextoFormato texto={texto} onCita={abrirCita} />}
      {respuesta.error && <div className="mt-1"><Aviso tono="alerta">{respuesta.error}</Aviso></div>}
      {respuesta.terminado && !respuesta.texto && !respuesta.error && (
        <div className="apagado pequeno">
          {respuesta.oculta ? 'La respuesta no se muestra: se basa en documentación a la que no tienes acceso.' : 'Sin respuesta.'}
        </div>
      )}
      {fuentes.length > 0 && (
        <div className="fuentes">
          {fuentes.map((f, i) => (
            <button key={i} type="button" className="fuente" onClick={() => setAbierta(f)} title={f.titulo}>
              <span className="n">{f.n ?? i + 1}</span>
              <span className="recortar">{etiquetaFuente(f)}</span>
            </button>
          ))}
        </div>
      )}
      <Modal abierto={!!abierta} titulo={abierta?.titulo ?? 'Fuente'} onCerrar={() => setAbierta(null)}>
        {abierta && (
          <div className="columna">
            <div className="fila apagado pequeno"><BookMarked size={16} /> {etiquetaFuente(abierta)}</div>
            {abierta.disponible === false
              ? <div className="apagado">Este documento se ha retirado o no tienes acceso a él.</div>
              : abierta.fragmento || abierta.texto
                ? <div className="pre">{abierta.fragmento || abierta.texto}</div>
                : <div className="apagado">Sin extracto disponible.</div>}
            {(abierta.autor || abierta.validador) && (
              <div className="pequeno apagado">
                {abierta.autor ? `Autor: ${abierta.autor}` : ''}
                {abierta.autor && abierta.validador ? ' · ' : ''}
                {abierta.validador ? `Validado por ${abierta.validador}` : ''}
              </div>
            )}
            {abierta.url && (
              <a href={urlServidor(abierta.url)} target="_blank" rel="noreferrer" className="fila pequeno" style={{ gap: 6 }}>
                <ExternalLink size={15} /> Abrir el documento
              </a>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
