// Curva de autonomía: consultas al copiloto en cada ejecución completada de una tarea.
// SVG propio: una línea verde de 2 px con puntos; las ejecuciones con consultas en pasos
// críticos llevan el punto en rojo (con leyenda). Al pasar el ratón (o con el teclado) se
// muestra el detalle de cada ejecución.

import { useEffect, useRef, useState } from 'react'
import { TrendingDown } from 'lucide-react'
import { fecha } from '../../api'
import { Vacio } from '../../ui'
import type { PuntoCurva } from './tipos'

const ALTO = 210
const M = { izq: 34, der: 16, arr: 16, aba: 30 }

/** Máximo «redondo» del eje Y (mínimo 4 para que una curva plana no parezca enorme). */
function maximoEje(v: number): number {
  if (v <= 4) return 4
  for (const paso of [2, 5, 10, 20, 50, 100]) {
    const tope = Math.ceil(v / paso) * paso
    if (tope / paso <= 5) return tope
  }
  return Math.ceil(v / 100) * 100
}

/** Paso entre marcas del eje Y: como mucho 5 tramos. */
function pasoEje(max: number): number {
  for (const p of [1, 2, 5, 10, 20, 25, 50, 100, 200, 500]) if (max % p === 0 && max / p <= 5) return p
  return max
}

function Grafico({ puntos }: { puntos: PuntoCurva[] }) {
  const caja = useRef<HTMLDivElement>(null)
  const [ancho, setAncho] = useState(520)
  const [activo, setActivo] = useState<number | null>(null)

  useEffect(() => {
    const el = caja.current
    if (!el) return
    const ro = new ResizeObserver((e) => setAncho(Math.max(260, Math.round(e[0].contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const n = puntos.length
  const maxY = maximoEje(Math.max(...puntos.map((p) => p.consultas)))
  const pasoY = pasoEje(maxY)
  const ticksY = Array.from({ length: Math.floor(maxY / pasoY) + 1 }, (_, i) => i * pasoY)
  const util = ancho - M.izq - M.der - 24
  const x = (i: number) => (n === 1 ? M.izq + 12 + util / 2 : M.izq + 12 + (i * util) / (n - 1))
  const y = (v: number) => M.arr + (ALTO - M.arr - M.aba) * (1 - v / maxY)
  const cadaX = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(util / 34))))
  const linea = puntos.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.consultas).toFixed(1)}`).join(' ')
  const area = `${linea} L${x(n - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`

  function alMover(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * ancho
    let mejor = 0
    puntos.forEach((_, i) => { if (Math.abs(x(i) - px) < Math.abs(x(mejor) - px)) mejor = i })
    setActivo(mejor)
  }

  const p = activo !== null ? puntos[activo] : null
  return (
    <div className="pp-curva" ref={caja}>
      <svg width={ancho} height={ALTO} viewBox={`0 0 ${ancho} ${ALTO}`} role="img"
        aria-label={`Consultas por ejecución: ${puntos.map((q) => q.consultas).join(', ')}`}
        onPointerMove={alMover} onPointerLeave={() => setActivo(null)}>
        {ticksY.map((t) => (
          <g key={t}>
            <line className="pp-curva-rejilla" x1={M.izq} x2={ancho - M.der} y1={y(t)} y2={y(t)} />
            <text className="pp-curva-eje" x={M.izq - 8} y={y(t) + 4} textAnchor="end">{t}</text>
          </g>
        ))}
        {puntos.map((q, i) => (i % cadaX === 0 || i === n - 1) && (
          <text key={q.ejecucion_id} className="pp-curva-eje" x={x(i)} y={ALTO - M.aba + 18} textAnchor="middle">{q.n}</text>
        ))}
        {n > 1 && <path className="pp-curva-area" d={area} />}
        {n > 1 && <path className="pp-curva-linea" d={linea} />}
        {p && <line className="pp-curva-guia" x1={x(activo!)} x2={x(activo!)} y1={M.arr} y2={ALTO - M.aba} />}
        {puntos.map((q, i) => (
          <g key={q.ejecucion_id} tabIndex={0} role="button" aria-label={`Ejecución ${q.n}: ${q.consultas} consultas`}
            onFocus={() => setActivo(i)} onBlur={() => setActivo(null)} className="pp-curva-punto">
            <circle cx={x(i)} cy={y(q.consultas)} r={12} fill="transparent" />
            <circle className={q.consultas_criticos > 0 ? 'critico' : ''} cx={x(i)} cy={y(q.consultas)}
              r={activo === i ? 6 : 4.5} />
          </g>
        ))}
      </svg>
      {p && (
        <div className="pp-curva-tooltip" style={{
          left: Math.min(Math.max(x(activo!), 90), ancho - 90),
          top: Math.max(0, y(p.consultas) - 74),
        }}>
          <div className="negrita">Ejecución {p.n}</div>
          <div className="diminuto apagado">{fecha(p.fecha, true)}</div>
          <div className="pp-curva-fila"><span className="clave verde" /><strong>{p.consultas}</strong> {p.consultas === 1 ? 'consulta' : 'consultas'}</div>
          {p.consultas_criticos > 0 && (
            <div className="pp-curva-fila"><span className="clave roja" /><strong>{p.consultas_criticos}</strong> en pasos críticos</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function CurvaAutonomia({ puntos }: { puntos: PuntoCurva[] }) {
  if (!puntos.length) {
    return (
      <Vacio icono={<TrendingDown />} titulo="Aún no hay ejecuciones completadas">
        Cada vez que se completa la tarea en modo planta, aquí aparece cuántas veces se preguntó al copiloto.
        Si la curva baja, hay más autonomía.
      </Vacio>
    )
  }
  const primera = puntos[0].consultas
  const ultima = puntos[puntos.length - 1].consultas
  const conCriticos = puntos.some((q) => q.consultas_criticos > 0)
  return (
    <div>
      <div className="fila envolver entre mb-1">
        <div className="pequeno apagado">
          {puntos.length === 1
            ? <>Primera ejecución: <strong className="pp-tinta">{primera}</strong> {primera === 1 ? 'consulta' : 'consultas'}</>
            : <>De <strong className="pp-tinta">{primera}</strong> consultas en la primera ejecución a{' '}
              <strong className="pp-tinta">{ultima}</strong> en la última</>}
        </div>
        <div className="fila pequeno apagado" style={{ gap: 14 }}>
          <span className="fila" style={{ gap: 6 }}><span className="clave-linea" />Consultas por ejecución</span>
          {conCriticos && <span className="fila" style={{ gap: 6 }}><span className="clave-punto critico" />Con consultas en pasos críticos</span>}
        </div>
      </div>
      <Grafico puntos={puntos} />
      <div className="diminuto apagado centro">Ejecuciones completadas, en orden</div>
    </div>
  )
}
