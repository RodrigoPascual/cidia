// Modo planta: elección de la tarea que se va a hacer en el puesto.

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, Briefcase, GraduationCap, ListChecks, Play, RefreshCw, RotateCcw, Search, Wrench,
} from 'lucide-react'
import { get, hace, post, urlServidor } from '../../api'
import {
  Boton, Cabecera, ErrorCarga, Esqueleto, Etiqueta, Iluo, NOMBRE_ILUO, Tarjeta, Vacio, useAvisarError, useDatos,
} from '../../ui'
import type { EjecucionDatos, TareaPlanta } from './tipos'
import './planta.css'

function TarjetaTarea({ t, empezando, onEmpezar }: { t: TareaPlanta; empezando: boolean; onEmpezar: () => void }) {
  const curso = t.ejecucion_en_curso
  const continuar = curso && curso.misma_version
  const portada = urlServidor(t.instruccion.portada_url)
  return (
    <article className={`pt-tarjeta ${continuar ? 'en-curso' : ''}`}>
      <div className={`pt-portada ${portada ? '' : 'sin-imagen'}`} style={portada ? { backgroundImage: `url("${portada}")` } : undefined}>
        {!portada && <Wrench className="pt-icono-fondo" size={34} />}
        <span className="pt-codigo">{t.codigo ?? t.instruccion.codigo ?? 'Tarea'}</span>
        {continuar && <Etiqueta tono="amarilla">En curso</Etiqueta>}
      </div>
      <div className="pt-cuerpo">
        <div>
          <div className="pt-nombre">{t.nombre}</div>
          <div className="pt-sub">
            {t.instruccion.codigo ?? 'Instrucción'} · versión {t.instruccion.version}
            {t.origen === 'formacion' && t.departamento ? ` · ${t.departamento}` : ''}
          </div>
        </div>
        <div className="pt-datos">
          <span className="pt-dato"><ListChecks /> {t.instruccion.pasos} {t.instruccion.pasos === 1 ? 'paso' : 'pasos'}</span>
          {t.instruccion.pasos_criticos > 0 && (
            <span className="pt-dato critico">
              <AlertTriangle /> {t.instruccion.pasos_criticos} {t.instruccion.pasos_criticos === 1 ? 'crítico' : 'críticos'}
            </span>
          )}
        </div>
        <div className="pt-nivel">
          <Iluo nivel={t.nivel} tamano={34} caducado={t.caducado} />
          <div className="crece">
            <div className="letra">{t.nivel ? `Nivel ${t.nivel_letra}` : 'Sin nivel todavía'}</div>
            <div className="texto">{NOMBRE_ILUO[t.nivel] ?? ''}{t.caducado ? ' · caducado' : ''}</div>
          </div>
          {t.requiere_reevaluacion && <Etiqueta tono="naranja" icono={<RefreshCw />} title="Hay una versión nueva de la instrucción">Reevaluar</Etiqueta>}
        </div>
      </div>
      <div className="pt-pie">
        <Boton variante={continuar ? 'primario' : 'oscuro'} tamano="grande" bloque cargando={empezando}
          icono={continuar ? <RotateCcw /> : <Play />} onClick={onEmpezar}>
          {continuar ? `Continuar · paso ${Math.min(curso.pasos_confirmados + 1, t.instruccion.pasos)} de ${t.instruccion.pasos}` : 'Empezar'}
        </Boton>
        <div className="detalle">
          {curso && !curso.misma_version ? 'Hay una versión nueva de la instrucción: la ejecución que dejaste a medias se cierra y empiezas con la nueva.' : t.ejecuciones_completadas
            ? `${t.ejecuciones_completadas} ${t.ejecuciones_completadas === 1 ? 'ejecución completada' : 'ejecuciones completadas'}`
              + (t.ultima_ejecucion ? `, la última ${hace(t.ultima_ejecucion)}` : '')
            : 'Todavía no la has hecho en el modo planta'}
        </div>
      </div>
    </article>
  )
}

function EsqueletoTareas() {
  return (
    <div className="pt-rejilla">
      {[0, 1, 2].map((i) => (
        <div key={i} className="pt-tarjeta">
          <Esqueleto alto={132} className="" />
          <div className="pt-cuerpo">
            <Esqueleto alto={22} ancho="75%" />
            <Esqueleto alto={14} ancho="45%" />
            <Esqueleto alto={54} />
          </div>
          <div className="pt-pie"><Esqueleto alto={52} /></div>
        </div>
      ))}
    </div>
  )
}

export default function Tareas() {
  const navegar = useNavigate()
  const avisarError = useAvisarError()
  const { datos, error, cargando, recargar } = useDatos((s) => get<TareaPlanta[]>('/api/planta/tareas', s))
  const [filtro, setFiltro] = useState('')
  const [empezando, setEmpezando] = useState<number | null>(null)

  const grupos = useMemo(() => {
    const q = filtro.trim().toLowerCase()
    const lista = (datos ?? []).filter((t) =>
      !q || [t.nombre, t.codigo, t.instruccion.codigo, t.departamento].some((v) => v?.toLowerCase().includes(q)))
    return {
      propias: lista.filter((t) => t.origen !== 'formacion'),
      formacion: lista.filter((t) => t.origen === 'formacion'),
    }
  }, [datos, filtro])

  async function empezar(t: TareaPlanta) {
    setEmpezando(t.id)
    try {
      const ej = await post<EjecucionDatos>('/api/planta/ejecuciones', { tarea_id: t.id })
      navegar(`/planta/ejecucion/${ej.id}`)
    } catch (e) {
      avisarError(e)
      setEmpezando(null)
    }
  }

  const total = datos?.length ?? 0
  const rejilla = (lista: TareaPlanta[]) => (
    <div className="pt-rejilla">
      {lista.map((t) => <TarjetaTarea key={t.id} t={t} empezando={empezando === t.id} onEmpezar={() => empezar(t)} />)}
    </div>
  )

  return (
    <>
      <Cabecera
        antetitulo={<><Wrench size={14} /> Modo planta</>}
        titulo="¿Qué tarea vas a hacer?"
        subtitulo="Elige la tarea y CidIA te guía paso a paso. Puedes preguntar por voz en cualquier momento sin soltar la herramienta."
        acciones={total > 6 && (
          <div className="entrada-icono pt-buscador">
            <Search />
            <input className="entrada" placeholder="Buscar por nombre o código" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
          </div>
        )}
      />

      {cargando && !datos ? <EsqueletoTareas /> : error ? (
        <Tarjeta><ErrorCarga error={error} reintentar={recargar} /></Tarjeta>
      ) : total === 0 ? (
        <Tarjeta>
          <Vacio icono={<Wrench />} titulo="Aún no hay tareas para el modo planta"
            accion={<Boton icono={<GraduationCap />} onClick={() => navegar('/formacion')}>Ver mi formación</Boton>}>
            Aquí aparecen las tareas de tu puesto y de tus formaciones que ya tienen una instrucción publicada.
            Cuando un experto publique la primera, podrás empezar a practicar.
          </Vacio>
        </Tarjeta>
      ) : grupos.propias.length + grupos.formacion.length === 0 ? (
        <Tarjeta><Vacio icono={<Search />} titulo="Ninguna tarea coincide con la búsqueda">Prueba con otro nombre o código.</Vacio></Tarjeta>
      ) : grupos.formacion.length && grupos.propias.length ? (
        <>
          <section className="pt-seccion">
            <div className="pt-seccion-titulo"><Briefcase /> Tu puesto</div>
            {rejilla(grupos.propias)}
          </section>
          <section className="pt-seccion">
            <div className="pt-seccion-titulo"><GraduationCap /> Tus formaciones</div>
            {rejilla(grupos.formacion)}
          </section>
        </>
      ) : (
        rejilla(grupos.propias.length ? grupos.propias : grupos.formacion)
      )}
    </>
  )
}
