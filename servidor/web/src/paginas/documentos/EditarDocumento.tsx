// Edición del título y de las etiquetas que deciden quién encuentra un documento.

import { useEffect, useMemo, useState } from 'react'
import { Eye, Lock, Save } from 'lucide-react'
import { patch } from '../../api'
import { Area, Aviso, Boton, Campo, Entrada, Interruptor, Modal, Selector, useAvisarError, useAvisos } from '../../ui'
import { SelectorNivel } from './comunes'
import { quienLoEncontrara, type Documento, type Opciones } from './tipos'

export default function EditarDocumento({ documento, opciones, onCerrar, onGuardado }: {
  documento: Documento | null; opciones: Opciones; onCerrar: () => void; onGuardado: (d: Documento) => void
}) {
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const [titulo, setTitulo] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [departamento, setDepartamento] = useState<number | null>(null)
  const [nivel, setNivel] = useState(1)
  const [formacion, setFormacion] = useState(false)
  const [publico, setPublico] = useState(false)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!documento) return
    setTitulo(documento.titulo); setDescripcion(documento.descripcion ?? '')
    setDepartamento(documento.departamento_id); setNivel(documento.nivel_minimo)
    setFormacion(documento.es_formacion); setPublico(documento.es_publico)
  }, [documento])

  const nombreDep = opciones.departamentos.find((d) => d.id === departamento)?.nombre ?? null
  const quien = useMemo(
    () => quienLoEncontrara(nombreDep, opciones.niveles.find((n) => n.orden === nivel), formacion, publico),
    [nombreDep, nivel, formacion, publico, opciones.niveles],
  )
  if (!documento) return null

  const cambiaBase = documento.motor_id && opciones.motor === 'weknora'
    && (departamento !== documento.departamento_id || publico !== documento.es_publico)
  const invalido = !titulo.trim() || (departamento === null && !publico)

  async function guardar() {
    if (!documento) return
    const cambios: Record<string, unknown> = {}
    if (titulo.trim() !== documento.titulo) cambios.titulo = titulo.trim()
    if ((descripcion.trim() || null) !== documento.descripcion) cambios.descripcion = descripcion.trim()
    if (departamento !== documento.departamento_id) cambios.departamento_id = departamento
    if (nivel !== documento.nivel_minimo) cambios.nivel_minimo = nivel
    if (formacion !== documento.es_formacion) cambios.es_formacion = formacion
    if (publico !== documento.es_publico) cambios.es_publico = publico
    if (!Object.keys(cambios).length) return onCerrar()
    setGuardando(true)
    try {
      const d = await patch<Documento>(`/api/documentos/${documento.id}`, cambios)
      avisar(d.estado === 'procesando' ? 'Cambios guardados. El documento se está reindexando.' : 'Cambios guardados.')
      onGuardado(d)
    } catch (e) {
      avisarError(e)
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal
      abierto titulo="Editar documento" onCerrar={() => !guardando && onCerrar()}
      pie={<>
        <Boton onClick={onCerrar} disabled={guardando}>Cancelar</Boton>
        <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={invalido} onClick={guardar}>Guardar cambios</Boton>
      </>}
    >
      <Campo etiqueta="Título">
        <Entrada value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={300} autoFocus />
      </Campo>
      <Campo etiqueta="Descripción">
        <Area rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
      </Campo>
      <div className="separador" />
      <div className="doc-seccion-titulo"><Lock /> Quién puede encontrarlo</div>
      <Campo
        etiqueta="Departamento"
        ayuda={!opciones.es_admin ? 'Solo la administración puede mover un documento a otro departamento.' : undefined}
      >
        <Selector
          value={departamento ?? ''} disabled={!opciones.es_admin}
          onChange={(e) => setDepartamento(e.target.value ? Number(e.target.value) : null)}
          opciones={[
            ...(opciones.es_admin ? [{ valor: '', texto: 'Ninguno (documento general)' }] : []),
            ...opciones.departamentos
              .filter((d) => opciones.es_admin || d.id === documento.departamento_id)
              .map((d) => ({ valor: d.id, texto: d.nombre })),
          ]}
        />
      </Campo>
      <div className="campo">
        <label>Nivel mínimo</label>
        <SelectorNivel niveles={opciones.niveles} valor={nivel} onCambio={setNivel} deshabilitado={publico} />
      </div>
      <div className="doc-interruptores">
        <Interruptor activo={formacion} onCambio={setFormacion} etiqueta="Material de formación" />
        <Interruptor activo={publico} onCambio={setPublico} etiqueta="Público" />
      </div>
      <div className="doc-quien"><Eye /><span>{quien}</span></div>
      {departamento === null && !publico && (
        <div className="mt-1"><Aviso tono="amarillo">Un documento sin departamento tiene que ser público.</Aviso></div>
      )}
      {cambiaBase && (
        <div className="mt-1">
          <Aviso>Con WeKnora, cambiar de departamento o de público obliga a reindexar el documento. Tardará unos segundos.</Aviso>
        </div>
      )}
    </Modal>
  )
}
