// Subida de conocimiento: varios ficheros a la vez, con sus etiquetas de permisos y progreso.

import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Eye, Lock, Trash2, Upload } from 'lucide-react'
import { subir, tamano } from '../../api'
import {
  Area, Aviso, BarraProgreso, Boton, Campo, Entrada, Interruptor, Modal, Selector, ZonaSubida, useAvisos,
} from '../../ui'
import { IconoTipo, SelectorNivel } from './comunes'
import { ACEPTA, quienLoEncontrara, tipoDeFichero, type Documento, type Opciones } from './tipos'

interface FicheroEnCola {
  clave: string
  fichero: File
  tipo: string | null
  estado: 'pendiente' | 'subiendo' | 'hecho' | 'error'
  progreso: number
  mensaje?: string
  documento?: Documento
}

export default function PanelSubida({ abierto, opciones, onCerrar, onSubido }: {
  abierto: boolean; opciones: Opciones; onCerrar: () => void; onSubido: () => void
}) {
  const avisar = useAvisos()
  const gestionables = opciones.departamentos.filter((d) => d.gestionable)
  const depInicial = opciones.departamento_propio ?? gestionables[0]?.id ?? null
  const [cola, setCola] = useState<FicheroEnCola[]>([])
  const [titulo, setTitulo] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [departamento, setDepartamento] = useState<number | null>(depInicial)
  const [nivel, setNivel] = useState(opciones.niveles[0]?.orden ?? 1)
  const [formacion, setFormacion] = useState(false)
  const [publico, setPublico] = useState(false)
  const [subiendo, setSubiendo] = useState(false)

  // Cada vez que se abre, empieza de cero.
  useEffect(() => {
    if (!abierto) return
    setCola([]); setTitulo(''); setDescripcion(''); setDepartamento(depInicial)
    setNivel(opciones.niveles[0]?.orden ?? 1); setFormacion(false); setPublico(false); setSubiendo(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto])

  const validos = cola.filter((f) => f.tipo)
  const pendientes = cola.filter((f) => f.tipo && f.estado !== 'hecho')
  const reintentos = pendientes.filter((f) => f.estado === 'error').length
  const terminado = !subiendo && !pendientes.length && cola.some((f) => f.estado === 'hecho')
  const progresoTotal = validos.length
    ? validos.reduce((s, f) => s + (f.estado === 'hecho' ? 100 : f.progreso), 0) / validos.length
    : 0
  const nombreDep = opciones.departamentos.find((d) => d.id === departamento)?.nombre ?? null
  const nivelSel = opciones.niveles.find((n) => n.orden === nivel)
  const quien = useMemo(() => quienLoEncontrara(nombreDep, nivelSel, formacion, publico),
    [nombreDep, nivelSel, formacion, publico])
  const sinDepartamentoNiPublico = departamento === null && !publico

  function anadir(ficheros: File[]) {
    setCola((c) => {
      const existentes = new Set(c.map((f) => `${f.fichero.name}:${f.fichero.size}`))
      const nuevos = ficheros
        .filter((f) => !existentes.has(`${f.name}:${f.size}`))
        .map((f) => {
          const tipo = tipoDeFichero(f.name)
          const vacio = f.size === 0
          return {
            clave: `${f.name}:${f.size}:${Math.random()}`, fichero: f, tipo: vacio ? null : tipo,
            estado: (tipo && !vacio ? 'pendiente' : 'error') as FicheroEnCola['estado'], progreso: 0,
            mensaje: vacio ? 'El fichero está vacío.' : tipo ? undefined
              : 'Formato no admitido. Sube PDF, Word, Excel, PowerPoint, texto, audio o imagen.',
          }
        })
      return [...c, ...nuevos]
    })
  }

  function actualizar(clave: string, cambios: Partial<FicheroEnCola>) {
    setCola((c) => c.map((f) => (f.clave === clave ? { ...f, ...cambios } : f)))
  }

  async function empezar() {
    setSubiendo(true)
    let bien = 0
    let mal = 0
    const unico = validos.length === 1
    for (const f of pendientes) {
      actualizar(f.clave, { estado: 'subiendo', progreso: 0, mensaje: undefined })
      const datos = new FormData()
      datos.append('fichero', f.fichero)
      if (unico && titulo.trim()) datos.append('titulo', titulo.trim())
      if (descripcion.trim()) datos.append('descripcion', descripcion.trim())
      datos.append('departamento_id', departamento === null ? '' : String(departamento))
      datos.append('nivel_minimo', String(nivel))
      datos.append('es_formacion', String(formacion))
      datos.append('es_publico', String(publico))
      try {
        const doc = await subir<Documento>('/api/documentos', datos, (p) => actualizar(f.clave, { progreso: p }))
        actualizar(f.clave, { estado: 'hecho', progreso: 100, documento: doc })
        bien++
      } catch (e) {
        actualizar(f.clave, { estado: 'error', mensaje: e instanceof Error ? e.message : String(e) })
        mal++
      }
    }
    setSubiendo(false)
    if (bien) {
      onSubido()
      avisar(bien === 1 ? 'Documento subido. CidIA lo está indexando.' : `${bien} documentos subidos. CidIA los está indexando.`)
    }
    if (!mal) onCerrar()
  }

  const pie = terminado ? (
    <Boton variante="primario" onClick={onCerrar}>Cerrar</Boton>
  ) : (
    <>
      <Boton onClick={onCerrar} disabled={subiendo}>Cancelar</Boton>
      <Boton
        variante="primario" icono={<Upload />} cargando={subiendo} onClick={empezar}
        disabled={!pendientes.length || sinDepartamentoNiPublico}
      >
        {reintentos && reintentos === pendientes.length ? 'Reintentar'
          : pendientes.length > 1 ? `Subir ${pendientes.length} documentos` : 'Subir documento'}
      </Boton>
    </>
  )

  return (
    <Modal abierto={abierto} titulo="Subir conocimiento" onCerrar={() => !subiendo && onCerrar()} pie={pie} ancho>
      <div className="doc-subida">
        <div>
          <ZonaSubida
            multiple acepta={ACEPTA} onFicheros={anadir}
            texto="Arrastra aquí tus documentos o haz clic para elegirlos"
            detalle="PDF, Word, Excel, PowerPoint, texto, audio o imagen. Puedes elegir varios a la vez."
          />
          {cola.length > 0 && (
            <div className="doc-ficheros" aria-live="polite">
              {cola.map((f) => (
                <div key={f.clave} className={`doc-fichero ${f.estado === 'error' ? 'error' : ''}`}>
                  <IconoTipo tipo={f.tipo ?? 'texto'} nombre={f.fichero.name} />
                  <div className="info">
                    <div className="nombre recortar" title={f.fichero.name}>{f.fichero.name}</div>
                    <div className={`estado ${f.estado === 'error' ? 'error' : f.estado === 'hecho' ? 'ok' : ''}`}>
                      {f.estado === 'pendiente' && tamano(f.fichero.size)}
                      {f.estado === 'subiendo' && (f.progreso < 100 ? `Subiendo… ${f.progreso} %` : 'Guardando en el servidor…')}
                      {f.estado === 'hecho' && (f.documento?.estado === 'error'
                        ? `Subido, pero no se ha podido indexar: ${f.documento.mensaje_estado ?? ''}`
                        : 'Subido. Se está indexando.')}
                      {f.estado === 'error' && f.mensaje}
                    </div>
                    {f.estado === 'subiendo' && <BarraProgreso valor={f.progreso} tono="amarilla" />}
                  </div>
                  {f.estado === 'hecho' && <CheckCircle2 size={18} color="var(--verde)" />}
                  {(f.estado === 'pendiente' || (f.estado === 'error' && !subiendo)) && (
                    <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} aria-label={`Quitar ${f.fichero.name}`}
                      onClick={() => setCola((c) => c.filter((x) => x.clave !== f.clave))} />
                  )}
                </div>
              ))}
            </div>
          )}
          {subiendo && validos.length > 1 && (
            <div className="mt-2">
              <div className="fila entre pequeno apagado mb-1"><span>Progreso total</span><span>{Math.round(progresoTotal)} %</span></div>
              <BarraProgreso valor={progresoTotal} />
            </div>
          )}
          <div className="mt-2">
            {validos.length === 1 ? (
              <Campo etiqueta="Título" ayuda="Si lo dejas vacío, se usa el nombre del fichero.">
                <Entrada value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={300}
                  placeholder={validos[0].fichero.name.replace(/\.[^.]+$/, '')} disabled={subiendo} />
              </Campo>
            ) : validos.length > 1 ? (
              <p className="pequeno apagado">Cada documento tomará como título el nombre de su fichero. Podrás cambiarlo después.</p>
            ) : null}
            <Campo etiqueta="Descripción (opcional)">
              <Area rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} disabled={subiendo}
                placeholder="Para qué sirve, a qué máquina o tarea se refiere…" />
            </Campo>
          </div>
        </div>

        <div>
          <div className="doc-seccion-titulo"><Lock /> Quién podrá encontrarlo</div>
          <Campo etiqueta="Departamento">
            <Selector
              value={departamento ?? ''} disabled={subiendo || (!opciones.es_admin && gestionables.length <= 1)}
              onChange={(e) => setDepartamento(e.target.value ? Number(e.target.value) : null)}
              opciones={[
                ...(opciones.es_admin ? [{ valor: '', texto: 'Ninguno (documento general)' }] : []),
                ...gestionables.map((d) => ({ valor: d.id, texto: d.nombre })),
              ]}
            />
          </Campo>
          <div className="campo">
            <label>Nivel mínimo</label>
            <SelectorNivel niveles={opciones.niveles} valor={nivel} onCambio={setNivel} deshabilitado={subiendo || publico} />
            <div className="ayuda">Las personas del departamento lo encuentran a partir de este nivel.</div>
          </div>
          <div className="doc-interruptores">
            <div>
              <Interruptor activo={formacion} onCambio={setFormacion} deshabilitado={subiendo} etiqueta="Material de formación" />
              <div className="ayuda">También lo encontrarán quienes se estén formando en este departamento.</div>
            </div>
            <div>
              <Interruptor activo={publico} onCambio={setPublico} deshabilitado={subiendo} etiqueta="Público" />
              <div className="ayuda">Para todo el mundo, incluso sin iniciar sesión (bienvenida, PRL…).</div>
            </div>
          </div>
          <div className="doc-quien"><Eye /><span>{quien}</span></div>
          {sinDepartamentoNiPublico && (
            <div className="mt-1"><Aviso tono="amarillo">Elige un departamento o marca el documento como público.</Aviso></div>
          )}
        </div>
      </div>
    </Modal>
  )
}
