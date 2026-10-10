// Mi perfil: datos de la cuenta, cambio de contraseña y memoria personal del copiloto.

import { useState, type FormEvent, type ReactNode } from 'react'
import {
  BadgeCheck, Brain, Briefcase, Building2, GraduationCap, KeyRound, Layers, MessageSquare, Plus, ShieldCheck,
  Sparkles, Trash2, UserRound,
} from 'lucide-react'
import { del, get, hace, post, put } from '../api'
import { NOMBRE_ROL, useSesion } from '../sesion'
import {
  Aviso, Avatar, Boton, Cabecera, Campo, Entrada, ErrorCarga, Esqueleto, Etiqueta, Interruptor, Tarjeta, Vacio,
  useAvisarError, useAvisos, useConfirmar, useDatos,
} from '../ui'
import './copiloto/perfil.css'

interface Recuerdo { id: number; contenido: string; origen: string | null; creada: string | null }
interface EstadoMemoria { activa: boolean; recuerdos: Recuerdo[]; total: number; maximo: number }

export default function Perfil() {
  const { perfil } = useSesion()
  if (!perfil || perfil.invitado) return null
  return (
    <>
      <Cabecera antetitulo="Tu cuenta" titulo="Mi perfil" subtitulo="Tus datos, tu contraseña y lo que el copiloto recuerda de ti." />
      <div className="perfil-rejilla">
        <div className="columna" style={{ gap: 16 }}>
          <DatosCuenta />
          <CambioContrasena />
        </div>
        <MemoriaPersonal />
      </div>
    </>
  )
}

// ------------------------------------------------------------------ cuenta

function DatosCuenta() {
  const { perfil } = useSesion()
  const { datos: actividad, error: errorActividad } =
    useDatos((s) => get<{ total: number }>('/api/consulta/historial?por_pagina=1', s), [])
  if (!perfil) return null
  const formaciones = perfil.formaciones ?? []
  return (
    <Tarjeta>
      <div className="perfil-identidad">
        <Avatar nombre={perfil.nombre} iniciales={perfil.iniciales} tamano="g" />
        <div className="crece">
          <h2>{perfil.nombre}</h2>
          <div className="fila envolver mt-1" style={{ gap: 6 }}>
            <Etiqueta tono={perfil.rol === 'admin' ? 'oscura' : perfil.rol === 'jefe' ? 'amarilla' : undefined}>
              {NOMBRE_ROL[perfil.rol] ?? perfil.rol}
            </Etiqueta>
            {perfil.es_experto && <Etiqueta tono="verde" icono={<BadgeCheck />}>Experto</Etiqueta>}
          </div>
        </div>
      </div>
      <dl className="perfil-datos">
        <Fila icono={<UserRound />} etiqueta="Usuario"><span className="mono">{perfil.usuario}</span></Fila>
        <Fila icono={<Briefcase />} etiqueta="Puesto">{perfil.puesto ?? <span className="apagado">Sin puesto asignado</span>}</Fila>
        {perfil.departamento && <Fila icono={<Building2 />} etiqueta="Departamento">{perfil.departamento.nombre}</Fila>}
        {perfil.nivel && <Fila icono={<Layers />} etiqueta="Nivel">{perfil.nivel.nombre}</Fila>}
        <Fila icono={<GraduationCap />} etiqueta="Formaciones activas">
          {formaciones.length ? (
            <div className="fila envolver" style={{ gap: 6 }}>
              {formaciones.map((f) => (
                <Etiqueta key={f.id} tono="azul">{f.departamento}{f.puesto ? ` · ${f.puesto}` : ''}</Etiqueta>
              ))}
            </div>
          ) : <span className="apagado">Ninguna ahora mismo</span>}
        </Fila>
        <Fila icono={<MessageSquare />} etiqueta="Preguntas al copiloto">
          {actividad ? actividad.total
            : errorActividad ? <span className="apagado">No disponible ahora</span>
              : <Esqueleto alto={14} ancho={40} />}
        </Fila>
      </dl>
      <div className="diminuto apagado mt-2">
        Si algún dato no es correcto, pídele a tu responsable o a la administración que lo cambie.
      </div>
    </Tarjeta>
  )
}

function Fila({ icono, etiqueta, children }: { icono: ReactNode; etiqueta: string; children: ReactNode }) {
  return (
    <div className="perfil-fila">
      <dt>{icono}{etiqueta}</dt>
      <dd>{children}</dd>
    </div>
  )
}

// ------------------------------------------------------------------ contraseña

function CambioContrasena() {
  const { perfil } = useSesion()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetida, setRepetida] = useState('')
  const [enviando, setEnviando] = useState(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()

  const corta = nueva.length > 0 && nueva.length < 8
  const distinta = repetida.length > 0 && repetida !== nueva
  const igualQueActual = nueva.length > 0 && nueva === actual
  const valido = actual && nueva.length >= 8 && nueva === repetida && !igualQueActual

  const cambiar = async (e: FormEvent) => {
    e.preventDefault()
    if (!valido) return
    setEnviando(true)
    try {
      await post('/api/auth/contrasena', { actual, nueva })
      avisar('Contraseña cambiada. Si tenías la sesión abierta en otros equipos, allí tendrás que volver a entrar.')
      setActual('')
      setNueva('')
      setRepetida('')
    } catch (err) {
      avisarError(err)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Tarjeta titulo="Cambiar la contraseña" icono={<KeyRound size={18} />}>
      <form onSubmit={cambiar} autoComplete="on">
        {/* Para que el gestor de contraseñas sepa de qué cuenta es */}
        <input type="text" name="usuario" autoComplete="username" value={perfil?.usuario ?? ''} hidden readOnly />
        <Campo etiqueta="Contraseña actual">
          <Entrada type="password" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} />
        </Campo>
        <Campo etiqueta="Nueva contraseña"
          ayuda={corta ? <span className="texto-alerta">Tiene que tener al menos 8 caracteres.</span>
            : igualQueActual ? <span className="texto-alerta">Tiene que ser distinta de la actual.</span>
              : 'Al menos 8 caracteres. Mejor una frase fácil de recordar que una palabra rara.'}>
          <Entrada type="password" autoComplete="new-password" value={nueva} onChange={(e) => setNueva(e.target.value)} />
        </Campo>
        <Campo etiqueta="Repite la nueva contraseña"
          ayuda={distinta ? <span className="texto-alerta">Las dos contraseñas no coinciden.</span> : undefined}>
          <Entrada type="password" autoComplete="new-password" value={repetida} onChange={(e) => setRepetida(e.target.value)} />
        </Campo>
        <div className="fila" style={{ justifyContent: 'flex-end' }}>
          <Boton type="submit" variante="primario" icono={<ShieldCheck />} cargando={enviando} disabled={!valido}>
            Cambiar contraseña
          </Boton>
        </div>
      </form>
    </Tarjeta>
  )
}

// ------------------------------------------------------------------ memoria personal

function MemoriaPersonal() {
  const { recargar } = useSesion()
  const { datos, error, cargando, recargar: recargarMemoria, setDatos } = useDatos((s) => get<EstadoMemoria>('/api/memoria', s), [])
  const [cambiando, setCambiando] = useState(false)
  const [nuevo, setNuevo] = useState('')
  const [anadiendo, setAnadiendo] = useState(false)
  const avisar = useAvisos()
  const avisarError = useAvisarError()
  const { confirmar, dialogo } = useConfirmar()

  const activar = async (activa: boolean) => {
    setCambiando(true)
    try {
      setDatos(await put<EstadoMemoria>('/api/memoria', { activa }))
      avisar(activa
        ? 'Memoria activada. El copiloto recordará lo útil de tus conversaciones.'
        : 'Memoria desactivada. Tus recuerdos se conservan hasta que los borres.')
      recargar()
    } catch (e) {
      avisarError(e)
    } finally {
      setCambiando(false)
    }
  }

  const anadir = async (e: FormEvent) => {
    e.preventDefault()
    if (!nuevo.trim()) return
    setAnadiendo(true)
    try {
      await post('/api/memoria', { contenido: nuevo.trim() })
      setNuevo('')
      recargarMemoria()
    } catch (err) {
      avisarError(err)
    } finally {
      setAnadiendo(false)
    }
  }

  const borrarUno = async (r: Recuerdo) => {
    if (!(await confirmar('¿Borrar este recuerdo?', <>«{r.contenido}». El copiloto dejará de tenerlo en cuenta.</>, true))) return
    try {
      await del(`/api/memoria/${r.id}`)
      setDatos((d) => d && { ...d, recuerdos: d.recuerdos.filter((x) => x.id !== r.id), total: d.total - 1 })
      avisar('Recuerdo borrado.')
    } catch (e) {
      avisarError(e)
    }
  }

  const borrarTodo = async () => {
    if (!datos?.total) return
    const ok = await confirmar(
      '¿Borrar toda tu memoria?',
      `Se borrarán ${datos.total === 1 ? 'el recuerdo guardado' : `los ${datos.total} recuerdos guardados`} del servidor. No se puede deshacer.`,
      true,
    )
    if (!ok) return
    try {
      const r = await del<{ borrados: number }>('/api/memoria')
      setDatos((d) => d && { ...d, recuerdos: [], total: 0 })
      avisar(r.borrados === 1 ? 'Se ha borrado 1 recuerdo.' : `Se han borrado ${r.borrados} recuerdos.`)
    } catch (e) {
      avisarError(e)
    }
  }

  const activa = !!datos?.activa
  return (
    <Tarjeta
      titulo="Memoria personal"
      icono={<Brain size={18} />}
      acciones={datos && (
        <Interruptor activo={activa} deshabilitado={cambiando} onCambio={activar} etiqueta={activa ? 'Activada' : 'Desactivada'} />
      )}
      pie={datos && datos.total > 0
        ? <Boton variante="peligro" tamano="pequeno" icono={<Trash2 />} onClick={borrarTodo}>Borrar todo</Boton>
        : undefined}
    >
      <div className="memoria-explicacion">
        <p>
          Si la activas, el copiloto recordará datos útiles sobre ti entre conversaciones (tu turno, las máquinas con
          las que trabajas, lo que estás aprendiendo o cómo prefieres las respuestas) para ayudarte mejor.
        </p>
        <ul>
          <li><strong>Está desactivada por defecto</strong>: solo se activa si tú quieres.</li>
          <li>Se guarda en el servidor de tu empresa y solo se usa en tus conversaciones.</li>
          <li>Puedes ver, borrar uno a uno o borrar todo lo que recuerda cuando quieras.</li>
          <li>No guarda datos sensibles ni sustituye a la documentación de la empresa.</li>
        </ul>
      </div>

      {cargando && !datos ? (
        <div className="columna mt-2">
          <Esqueleto alto={20} ancho="40%" />
          <Esqueleto alto={44} />
          <Esqueleto alto={44} />
        </div>
      ) : error && !datos ? (
        <ErrorCarga error={error} reintentar={recargarMemoria} />
      ) : datos ? (
        <>
          {!activa && datos.total > 0 && (
            <div className="mt-2">
              <Aviso>Mientras la memoria esté desactivada, estos recuerdos no se usan ni se guardan otros nuevos.</Aviso>
            </div>
          )}

          {activa && (
            <form className="memoria-nuevo mt-2" onSubmit={anadir}>
              <Entrada value={nuevo} maxLength={500} placeholder="Añade algo que quieras que recuerde, p. ej. «Trabajo en el turno de noche»"
                onChange={(e) => setNuevo(e.target.value)} aria-label="Nuevo recuerdo" />
              <Boton type="submit" icono={<Plus />} cargando={anadiendo} disabled={!nuevo.trim()}>Añadir</Boton>
            </form>
          )}

          {datos.recuerdos.length === 0 ? (
            <Vacio icono={<Sparkles />} titulo={activa ? 'Todavía no recuerda nada' : 'La memoria está desactivada'}>
              {activa
                ? 'Irá apuntando lo útil cuando le cuentes cosas de tu trabajo en el copiloto. También puedes añadirlo tú.'
                : 'Actívala con el interruptor si quieres que el copiloto te conozca mejor.'}
            </Vacio>
          ) : (
            <>
              <div className="fila entre mt-2 mb-1">
                <span className="etiqueta-campo">Lo que recuerda de ti</span>
                <span className="diminuto apagado">{datos.total} de {datos.maximo} como máximo</span>
              </div>
              <ul className={`recuerdos ${activa ? '' : 'inactivos'}`}>
                {datos.recuerdos.map((r) => (
                  <li key={r.id} className="recuerdo">
                    <span className="recuerdo-icono"><Brain /></span>
                    <div className="crece">
                      <div>{r.contenido}</div>
                      <div className="diminuto apagado">
                        {r.origen === 'manual' ? 'Lo añadiste tú' : 'Lo aprendió el copiloto'}{r.creada ? ` · ${hace(r.creada)}` : ''}
                      </div>
                    </div>
                    <Boton variante="fantasma" tamano="pequeno" icono={<Trash2 />} onClick={() => borrarUno(r)}
                      title="Borrar este recuerdo" aria-label={`Borrar el recuerdo «${r.contenido}»`} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : null}
      {dialogo}
    </Tarjeta>
  )
}
