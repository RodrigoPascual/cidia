// Consola sencilla del espacio de trabajo: ejecuta una orden en un contenedor aislado del servidor
// (sin red, con la carpeta del usuario en /trabajo) y muestra la salida.

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Play, ShieldCheck, SquareTerminal, Trash2 } from 'lucide-react'
import { post } from '../../api'
import { Boton, Etiqueta, Tarjeta } from '../../ui'
import type { Ejecucion } from './comun'

interface Linea { id: number; orden: string; res?: Ejecucion; error?: string }

const EJEMPLOS = ['ls -la', 'python3 --version', 'head -n 5 datos.csv']

function Resultado({ r }: { r: Ejecucion }) {
  const avisos = [
    r.tiempo_agotado && 'se detuvo por tiempo',
    r.memoria_agotada && 'se quedó sin memoria',
    r.cuota_superada && 'la carpeta llegó a su límite',
    r.recortada && 'salida recortada',
  ].filter(Boolean) as string[]
  return (
    <>
      {r.salida && <pre className="consola-salida">{r.salida}</pre>}
      <div className="consola-pie">
        <span className={r.codigo === 0 ? 'ok' : 'mal'}>
          {r.codigo === 0 ? 'Terminó bien' : `Código ${r.codigo ?? '?'}`}
        </span>
        <span>{r.duracion.toLocaleString('es-ES', { maximumFractionDigits: 1 })} s</span>
        {avisos.map((a) => <span key={a} className="mal">{a}</span>)}
      </div>
    </>
  )
}

export default function Consola({ tiempoMax = 120, alTerminar }: { tiempoMax?: number; alTerminar: () => void }) {
  const [orden, setOrden] = useState('')
  const [lineas, setLineas] = useState<Linea[]>([])
  const [ocupada, setOcupada] = useState(false)
  const [historial, setHistorial] = useState<string[]>([])
  const [pos, setPos] = useState(-1)
  const caja = useRef<HTMLDivElement>(null)
  const entrada = useRef<HTMLInputElement>(null)

  // Baja hasta la última salida dentro de la consola (sin mover la página).
  useEffect(() => {
    const c = caja.current
    if (c) c.scrollTop = c.scrollHeight
  }, [lineas])

  async function ejecutar(texto = orden) {
    const o = texto.trim()
    if (!o || ocupada) return
    const id = Date.now()
    setLineas((l) => [...l.slice(-19), { id, orden: o }])
    setHistorial((h) => [o, ...h.filter((x) => x !== o)].slice(0, 30))
    setPos(-1)
    setOrden('')
    setOcupada(true)
    try {
      const res = await post<Ejecucion>('/api/espacio/ejecutar', { orden: o, tiempo_max: tiempoMax })
      setLineas((l) => l.map((x) => (x.id === id ? { ...x, res } : x)))
      alTerminar()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setLineas((l) => l.map((x) => (x.id === id ? { ...x, error: msg } : x)))
    } finally {
      setOcupada(false)
      entrada.current?.focus()
    }
  }

  function tecla(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') { e.preventDefault(); ejecutar() }
    else if (e.key === 'ArrowUp' && historial.length) {
      e.preventDefault()
      const p = Math.min(pos + 1, historial.length - 1)
      setPos(p); setOrden(historial[p])
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const p = pos - 1
      setPos(Math.max(p, -1)); setOrden(p >= 0 ? historial[p] : '')
    }
  }

  return (
    <Tarjeta
      titulo="Consola"
      icono={<SquareTerminal size={18} />}
      acciones={<>
        <Etiqueta tono="verde" icono={<ShieldCheck />} title="Contenedor aislado: sin red, sin privilegios y con límites de tiempo y memoria">
          Aislada · sin red
        </Etiqueta>
        {lineas.length > 0 && (
          <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} onClick={() => setLineas([])} aria-label="Limpiar la consola" />
        )}
      </>}
    >
      <p className="pequeno apagado">
        Las órdenes se ejecutan en el servidor, en un contenedor aislado y sin red, con tu carpeta en <code>/trabajo</code>.
        Tienes Python 3 con pandas, openpyxl, python-docx, matplotlib y reportlab. Cada orden puede durar como mucho {Math.round(tiempoMax / 60)} minutos.
      </p>
      <div className="consola" ref={caja} onClick={() => entrada.current?.focus()}>
        {lineas.length === 0 && (
          <div className="consola-vacia">
            Prueba con {EJEMPLOS.map((e, i) => (
              <span key={e}>{i > 0 && ', '}<button className="consola-ejemplo" onClick={() => ejecutar(e)}>{e}</button></span>
            ))}.
          </div>
        )}
        {lineas.map((l) => (
          <div key={l.id} className="consola-bloque">
            <div className="consola-orden"><span className="consola-prompt">/trabajo $</span> {l.orden}</div>
            {l.res ? <Resultado r={l.res} /> : l.error ? <div className="consola-error">{l.error}</div>
              : <div className="consola-espera">Ejecutando…</div>}
          </div>
        ))}
      </div>
      <div className="consola-entrada">
        <span className="consola-prompt">$</span>
        <input
          ref={entrada}
          value={orden}
          onChange={(e) => setOrden(e.target.value)}
          onKeyDown={tecla}
          placeholder="Escribe una orden, por ejemplo: python3 informe.py"
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          aria-label="Orden"
          disabled={ocupada}
        />
        <Boton variante="verde" tamano="pequeno" icono={<Play />} cargando={ocupada} disabled={!orden.trim()} onClick={() => ejecutar()}>
          Ejecutar
        </Boton>
      </div>
    </Tarjeta>
  )
}
