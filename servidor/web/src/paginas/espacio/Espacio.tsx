// Espacio de trabajo: la carpeta privada de cada persona en el servidor, donde el agente de CidIA
// deja lo que genera. Explorador con migas de pan, vista previa, subida, carpetas, renombrar,
// borrar, descargar y, si el servidor lo permite, una consola aislada.

import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ChevronRight, Download, FolderOpen, FolderPlus, HardDrive, House, Lock, Pencil, RefreshCw, SquareTerminal, Trash2,
  Upload,
} from 'lucide-react'
import { del, fecha, get, hace, post, subir, tamano, urlServidor } from '../../api'
import {
  Aviso, BarraProgreso, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Modal, Tarjeta, Vacio, ZonaSubida,
  useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../../ui'
import Consola from './Consola'
import VistaPrevia from './VistaPrevia'
import { IconoElemento, buscarCarpeta, buscarElemento, padre, seAbre, unir, type Arbol, type Elemento } from './comun'
import './espacio.css'

interface EstadoEjecutor { disponible: boolean; mensaje?: string | null; tiempo_max?: number }

// Mismo texto que da el servidor cuando falta el servicio espacio-trabajo.
const SIN_CONSOLA = 'La consola para ejecutar órdenes no está disponible en este servidor. Tus ficheros sí: puedes verlos, subirlos y descargarlos.'
interface Subida { nombre: string; pct: number; estado: 'espera' | 'subiendo' | 'hecho' | 'error'; error?: string }

// ------------------------------------------------------------------ migas de pan

function Migas({ ruta, ir }: { ruta: string; ir: (r: string) => void }) {
  const partes = ruta ? ruta.split('/') : []
  return (
    <nav className="espacio-migas" aria-label="Carpeta actual">
      <button className={partes.length ? '' : 'actual'} onClick={() => ir('')}>
        <House size={15} /> Mi carpeta
      </button>
      {partes.map((p, i) => {
        const destino = partes.slice(0, i + 1).join('/')
        const ultima = i === partes.length - 1
        return (
          <span key={destino} className="fila" style={{ gap: 2 }}>
            <ChevronRight size={14} className="apagado" />
            <button className={ultima ? 'actual' : ''} onClick={() => ir(destino)} aria-current={ultima ? 'page' : undefined}>
              {p}
            </button>
          </span>
        )
      })}
    </nav>
  )
}

// ------------------------------------------------------------------ fila del explorador

function Fila({ el, seleccionado, abrir, renombrar, borrar }: {
  el: Elemento; seleccionado: boolean; abrir: () => void; renombrar: () => void; borrar: () => void
}) {
  return (
    <div className={`espacio-fila ${seleccionado ? 'seleccionada' : ''}`}>
      <button className="espacio-nombre" onClick={abrir} disabled={!seAbre(el)}
        title={el.tipo === 'enlace' ? 'Enlace: no se puede abrir' : el.tipo === 'especial' ? 'Elemento especial: no se puede abrir' : el.nombre}>
        <IconoElemento el={el} />
        <span className="recortar">{el.nombre}</span>
      </button>
      <span className="espacio-tamano">{seAbre(el) ? tamano(el.tamano) : el.tipo}</span>
      <span className="espacio-fecha" title={fecha(el.modificado, true)}>{hace(el.modificado)}</span>
      <span className="espacio-acciones">
        {el.url_descarga && (
          <a className="boton fantasma pequeno icono" href={urlServidor(el.url_descarga)} download
            title="Descargar" aria-label={`Descargar ${el.nombre}`}><Download /></a>
        )}
        {seAbre(el) && (
          <Boton variante="fantasma" tamano="pequeno" icono={<Pencil />} onClick={renombrar} title="Renombrar o mover"
            aria-label={`Renombrar ${el.nombre}`} />
        )}
        <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} onClick={borrar} title="Borrar"
          aria-label={`Borrar ${el.nombre}`} className="borrar" />
      </span>
    </div>
  )
}

// ------------------------------------------------------------------ página

export default function Espacio() {
  const [params, setParams] = useSearchParams()
  const carpeta = params.get('carpeta') ?? ''
  const seleccion = params.get('fichero')
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  const { datos: arbol, error, cargando, recargar } = useDatos((s) => get<Arbol>('/api/espacio', s), [])
  const [ejecutor, setEjecutor] = useState<EstadoEjecutor | null>(null)
  useEffect(() => {
    if (!arbol?.ejecutor_configurado || ejecutor) return
    get<EstadoEjecutor>('/api/espacio/ejecutor').then(setEjecutor).catch(() => setEjecutor({ disponible: false }))
  }, [arbol?.ejecutor_configurado, ejecutor])

  const lista = useMemo(() => (arbol ? buscarCarpeta(arbol.elementos, carpeta) : null), [arbol, carpeta])
  const elegido = useMemo(() => {
    const el = arbol && seleccion ? buscarElemento(arbol.elementos, seleccion) : null
    return el && el.tipo === 'fichero' ? el : null
  }, [arbol, seleccion])

  const ir = useCallback((ruta: string, fichero?: string | null) => {
    const p = new URLSearchParams()
    if (ruta) p.set('carpeta', ruta)
    if (fichero) p.set('fichero', fichero)
    setParams(p)
  }, [setParams])

  // Si la carpeta de la URL ya no existe (se borró o se movió), se vuelve a la principal.
  useEffect(() => { if (arbol && carpeta && lista === null) ir('') }, [arbol, carpeta, lista, ir])

  const vista = useRef<HTMLDivElement>(null)
  function abrir(el: Elemento) {
    if (!seAbre(el)) return
    if (el.tipo === 'carpeta') return ir(el.ruta)
    ir(carpeta, el.ruta)
    if (window.matchMedia('(max-width: 1000px)').matches) {
      setTimeout(() => vista.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    }
  }

  // ---------------------------------------------------------------- nueva carpeta y renombrar

  const [dialogoNombre, setDialogoNombre] = useState<{ modo: 'carpeta' | 'renombrar'; el?: Elemento } | null>(null)
  const [nombre, setNombre] = useState('')
  const [guardando, setGuardando] = useState(false)

  function abrirNombre(modo: 'carpeta' | 'renombrar', el?: Elemento) {
    setNombre(el ? el.nombre : '')
    setDialogoNombre({ modo, el })
  }

  async function guardarNombre() {
    const texto = nombre.trim().replace(/^\/+|\/+$/g, '')
    if (!texto || !dialogoNombre) return
    setGuardando(true)
    try {
      if (dialogoNombre.modo === 'carpeta') {
        await post('/api/espacio/carpeta', { ruta: unir(carpeta, texto) })
        avisar(`Carpeta «${texto}» creada`)
      } else if (dialogoNombre.el) {
        const el = dialogoNombre.el
        const destino = texto.includes('/') ? texto : unir(padre(el.ruta), texto)
        if (destino !== el.ruta) {
          const nuevo = await post<Elemento>('/api/espacio/mover', { origen: el.ruta, destino })
          avisar(texto.includes('/') ? `Movido a «${padre(nuevo.ruta) || 'Mi carpeta'}»` : 'Nombre cambiado')
          if (seleccion === el.ruta) ir(carpeta, nuevo.tipo === 'fichero' ? nuevo.ruta : null)
        }
      }
      setDialogoNombre(null)
      recargar()
    } catch (e) {
      avisarError(e)
    } finally {
      setGuardando(false)
    }
  }

  // ---------------------------------------------------------------- borrar

  async function borrar(el: Elemento) {
    const esCarpeta = el.tipo === 'carpeta'
    const ok = await confirmar(
      esCarpeta ? 'Borrar la carpeta' : 'Borrar el fichero',
      <>Se borrará <strong>{el.nombre}</strong>{esCarpeta ? ' con todo lo que contiene' : ''}. No se puede deshacer.</>,
      true,
    )
    if (!ok) return
    try {
      await del(`/api/espacio/fichero?ruta=${encodeURIComponent(el.ruta)}`)
      avisar(esCarpeta ? 'Carpeta borrada' : 'Fichero borrado')
      if (seleccion && (seleccion === el.ruta || seleccion.startsWith(`${el.ruta}/`))) ir(carpeta)
      recargar()
    } catch (e) {
      avisarError(e)
    }
  }

  // ---------------------------------------------------------------- subida

  const [modalSubida, setModalSubida] = useState(false)
  const [subidas, setSubidas] = useState<Subida[]>([])
  const [arrastrando, setArrastrando] = useState(false)
  const subiendo = subidas.some((s) => s.estado === 'subiendo' || s.estado === 'espera')

  async function subirFicheros(ficheros: File[]) {
    if (!ficheros.length || subiendo) return
    setModalSubida(true)
    setSubidas(ficheros.map((f) => ({ nombre: f.name, pct: 0, estado: 'espera' })))
    const cambiar = (i: number, c: Partial<Subida>) => setSubidas((s) => s.map((x, j) => (j === i ? { ...x, ...c } : x)))
    let bien = 0
    for (let i = 0; i < ficheros.length; i++) {
      const f = ficheros[i]
      if (arbol && f.size > arbol.max_fichero) {
        cambiar(i, { estado: 'error', error: `Supera el máximo de ${tamano(arbol.max_fichero)}` })
        continue
      }
      cambiar(i, { estado: 'subiendo' })
      const fd = new FormData()
      fd.append('fichero', f)
      fd.append('carpeta', carpeta)
      try {
        await subir('/api/espacio/subir', fd, (pct) => cambiar(i, { pct }))
        cambiar(i, { estado: 'hecho', pct: 100 })
        bien++
      } catch (e) {
        cambiar(i, { estado: 'error', error: e instanceof Error ? e.message : String(e) })
      }
    }
    recargar()
    if (bien === ficheros.length) {
      avisar(bien === 1 ? 'Fichero subido' : `${bien} ficheros subidos`)
      setModalSubida(false)
      setSubidas([])
    }
  }

  function soltar(e: DragEvent) {
    e.preventDefault()
    setArrastrando(false)
    const f = Array.from(e.dataTransfer.files)
    if (f.length) subirFicheros(f)
  }

  // ---------------------------------------------------------------- render

  const uso = arbol ? Math.min(100, (arbol.uso / Math.max(1, arbol.cuota)) * 100) : 0
  const elementos = lista ?? []

  return (
    <>
      <Cabecera
        antetitulo={<><HardDrive size={14} /> En el servidor de la empresa</>}
        titulo="Espacio de trabajo"
        subtitulo="Aquí deja el agente de CidIA lo que genera para ti (informes, tablas...). Solo tú ves esta carpeta. Vive en el servidor de la empresa."
        acciones={<>
          <Boton icono={<FolderPlus />} onClick={() => abrirNombre('carpeta')} disabled={!arbol}>Nueva carpeta</Boton>
          <Boton variante="primario" icono={<Upload />} onClick={() => { setSubidas([]); setModalSubida(true) }} disabled={!arbol}>
            Subir
          </Boton>
        </>}
      />

      {arbol && (
        <div className="espacio-uso">
          <Lock size={16} className="apagado" />
          <span className="pequeno"><strong>Privada</strong> · solo tú y el agente cuando trabaja para ti</span>
          <span className="crece" />
          <span className="pequeno apagado">{tamano(arbol.uso)} de {tamano(arbol.cuota)}</span>
          <div className="espacio-uso-barra"><BarraProgreso valor={uso} tono={uso > 85 ? 'amarilla' : undefined} /></div>
        </div>
      )}
      {arbol && uso > 90 && (
        <div className="mb-2">
          <Aviso tono="alerta">Tu carpeta está casi llena. Borra lo que ya no necesites para que el agente pueda seguir guardando.</Aviso>
        </div>
      )}

      <div className={`espacio-rejilla ${elegido ? 'con-vista' : ''}`}>
        <Tarjeta className="espacio-explorador" relleno={false}>
          <div className="espacio-barra">
            <Migas ruta={carpeta} ir={(r) => ir(r)} />
            <Boton variante="fantasma" tamano="pequeno" icono={<RefreshCw />} onClick={recargar} cargando={cargando && !!arbol}
              aria-label="Actualizar" title="Actualizar" />
          </div>
          <div
            className={`espacio-lista ${arrastrando ? 'arrastrando' : ''}`}
            onDragOver={(e) => { if (arbol && e.dataTransfer.types.includes('Files')) { e.preventDefault(); setArrastrando(true) } }}
            onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setArrastrando(false) }}
            onDrop={soltar}
          >
            {!arbol && cargando ? (
              <div className="espacio-esqueleto">
                {[70, 55, 80, 45, 60].map((a, i) => (
                  <div key={i} className="fila"><Esqueleto alto={20} ancho={20} /><Esqueleto alto={14} ancho={`${a}%`} /></div>
                ))}
              </div>
            ) : error ? (
              <ErrorCarga error={error} reintentar={recargar} />
            ) : elementos.length === 0 ? (
              carpeta ? (
                <Vacio icono={<FolderOpen />} titulo="Esta carpeta está vacía"
                  accion={<Boton icono={<Upload />} onClick={() => setModalSubida(true)}>Subir aquí</Boton>}>
                  Arrastra ficheros aquí para subirlos a «{carpeta.split('/').pop()}».
                </Vacio>
              ) : (
                <Vacio icono={<FolderOpen />} titulo="Tu carpeta está vacía"
                  accion={<Boton variante="primario" icono={<Upload />} onClick={() => setModalSubida(true)}>Subir un fichero</Boton>}>
                  Cuando pidas al agente un informe, una tabla o un documento, aparecerá aquí para que lo veas y lo descargues.
                  También puedes subir tus propios ficheros para que trabaje con ellos.
                </Vacio>
              )
            ) : (
              <div aria-label="Ficheros">
                <div className="espacio-fila cabeza" aria-hidden="true">
                  <span>Nombre</span><span className="espacio-tamano">Tamaño</span>
                  <span className="espacio-fecha">Modificado</span><span />
                </div>
                {elementos.map((el) => (
                  <Fila key={el.ruta} el={el} seleccionado={seleccion === el.ruta} abrir={() => abrir(el)}
                    renombrar={() => abrirNombre('renombrar', el)} borrar={() => borrar(el)} />
                ))}
              </div>
            )}
            {arrastrando && <div className="espacio-soltar"><Upload /> Suelta para subir a {carpeta ? `«${carpeta.split('/').pop()}»` : 'tu carpeta'}</div>}
          </div>
          {arbol?.incompleto && (
            <div className="tarjeta-pie pequeno apagado" style={{ justifyContent: 'flex-start' }}>
              Hay muchos ficheros: solo se muestran los primeros.
            </div>
          )}
        </Tarjeta>

        <div ref={vista} className="espacio-columna-vista">
          {elegido && (
            <Tarjeta relleno={false} className="espacio-tarjeta-vista">
              <VistaPrevia key={elegido.ruta} elemento={elegido} onCerrar={() => ir(carpeta)} />
            </Tarjeta>
          )}
        </div>
      </div>

      {ejecutor?.disponible ? (
        <div className="mt-3">
          <Consola tiempoMax={ejecutor.tiempo_max ?? 120} alTerminar={recargar} />
        </div>
      ) : arbol && (!arbol.ejecutor_configurado || ejecutor) ? (
        <div className="espacio-sin-consola" role="note">
          <SquareTerminal size={16} />
          <span>{ejecutor?.mensaje || SIN_CONSOLA}</span>
        </div>
      ) : null}

      {/* Subida */}
      <Modal abierto={modalSubida} titulo={carpeta ? `Subir a «${carpeta.split('/').pop()}»` : 'Subir a tu carpeta'}
        onCerrar={() => { if (!subiendo) { setModalSubida(false); setSubidas([]) } }}
        pie={<Boton onClick={() => { setModalSubida(false); setSubidas([]) }} disabled={subiendo}>Cerrar</Boton>}>
        {subidas.length === 0 ? (
          <ZonaSubida multiple onFicheros={subirFicheros}
            texto="Arrastra aquí tus ficheros o haz clic para elegirlos"
            detalle={arbol ? `Máximo ${tamano(arbol.max_fichero)} por fichero. Si ya existe uno con el mismo nombre, se guarda como copia.` : undefined} />
        ) : (
          <div className="columna">
            {subidas.map((s, i) => (
              <div key={i} className="espacio-subida">
                <div className="fila entre">
                  <span className="recortar pequeno negrita">{s.nombre}</span>
                  <span className={`diminuto ${s.estado === 'error' ? 'texto-alerta' : 'apagado'}`}>
                    {s.estado === 'hecho' ? 'Subido' : s.estado === 'error' ? 'No se ha subido' : s.estado === 'espera' ? 'En espera' : `${s.pct} %`}
                  </span>
                </div>
                {s.estado === 'error' ? <div className="diminuto texto-alerta">{s.error}</div>
                  : <BarraProgreso valor={s.pct} />}
              </div>
            ))}
          </div>
        )}
      </Modal>

      {/* Nueva carpeta y renombrar */}
      <Modal abierto={!!dialogoNombre}
        titulo={dialogoNombre?.modo === 'carpeta' ? 'Nueva carpeta' : `Renombrar «${dialogoNombre?.el?.nombre ?? ''}»`}
        onCerrar={() => setDialogoNombre(null)}
        pie={<>
          <Boton onClick={() => setDialogoNombre(null)}>Cancelar</Boton>
          <Boton variante="primario" cargando={guardando} disabled={!nombre.trim()} onClick={guardarNombre}>
            {dialogoNombre?.modo === 'carpeta' ? 'Crear' : 'Guardar'}
          </Boton>
        </>}>
        <form onSubmit={(e) => { e.preventDefault(); guardarNombre() }}>
          <Campo etiqueta={dialogoNombre?.modo === 'carpeta' ? 'Nombre de la carpeta' : 'Nuevo nombre'}
            ayuda={dialogoNombre?.modo === 'carpeta'
              ? `Se creará en ${carpeta ? `«${carpeta}»` : 'tu carpeta principal'}.`
              : 'Para moverlo a otra carpeta, escribe la ruta completa, por ejemplo: informes/marzo/resumen.md'}>
            <Entrada autoFocus value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={300}
              onFocus={(e) => {
                const punto = e.target.value.lastIndexOf('.')
                if (dialogoNombre?.modo === 'renombrar' && punto > 0) e.target.setSelectionRange(0, punto)
              }} />
          </Campo>
        </form>
      </Modal>

      {dialogo}
    </>
  )
}
