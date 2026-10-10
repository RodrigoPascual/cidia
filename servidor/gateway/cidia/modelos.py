"""Esquema de datos de CidIA (único fichero de tablas).

Convenciones: claves primarias enteras, fechas con zona horaria (UTC), JSONB para
estructuras flexibles y nombres en castellano.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cidia.db import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_uuid() -> str:
    return str(uuid.uuid4())


Fecha = DateTime(timezone=True)

# --------------------------------------------------------------------------- empresa


class Empresa(Base):
    """Una sola fila: datos y configuración de la empresa que usa este servidor."""

    __tablename__ = "empresa"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), default="Mi empresa")
    sector: Mapped[str | None] = mapped_column(String(200))
    config_iluo: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)


class Nivel(Base):
    """Nivel de responsabilidad (por defecto: operario, técnico, responsable, dirección)."""

    __tablename__ = "niveles"
    id: Mapped[int] = mapped_column(primary_key=True)
    orden: Mapped[int] = mapped_column(Integer, unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text)


class Departamento(Base):
    __tablename__ = "departamentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True)
    codigo: Mapped[str | None] = mapped_column(String(30))
    descripcion: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(20))
    weknora_kb_id: Mapped[str | None] = mapped_column(String(100))
    creado: Mapped[datetime] = mapped_column(Fecha, default=ahora)

    puestos: Mapped[list[Puesto]] = relationship(back_populates="departamento", cascade="all, delete-orphan")


class Puesto(Base):
    __tablename__ = "puestos"
    id: Mapped[int] = mapped_column(primary_key=True)
    departamento_id: Mapped[int] = mapped_column(ForeignKey("departamentos.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[str | None] = mapped_column(Text)

    departamento: Mapped[Departamento] = relationship(back_populates="puestos")
    tareas: Mapped[list[Tarea]] = relationship(back_populates="puesto", cascade="all, delete-orphan")


class Tarea(Base):
    __tablename__ = "tareas"
    id: Mapped[int] = mapped_column(primary_key=True)
    puesto_id: Mapped[int] = mapped_column(ForeignKey("puestos.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str | None] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    criticidad: Mapped[int] = mapped_column(Integer, default=2)  # 1 baja, 2 media, 3 alta
    riesgos_prl: Mapped[str | None] = mapped_column(Text)
    nivel_minimo: Mapped[int] = mapped_column(Integer, default=1)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)

    puesto: Mapped[Puesto] = relationship(back_populates="tareas")


# --------------------------------------------------------------------------- personas


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(200))
    hash_contrasena: Mapped[str | None] = mapped_column(String(300))
    departamento_id: Mapped[int | None] = mapped_column(ForeignKey("departamentos.id", ondelete="SET NULL"), index=True)
    nivel_id: Mapped[int | None] = mapped_column(ForeignKey("niveles.id", ondelete="SET NULL"))
    puesto_id: Mapped[int | None] = mapped_column(ForeignKey("puestos.id", ondelete="SET NULL"))
    rol: Mapped[str] = mapped_column(String(20), default="empleado")  # empleado | jefe | admin
    es_experto: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    memoria_activa: Mapped[bool] = mapped_column(Boolean, default=False)
    # Contraseña inicial o temporal (alta o restablecimiento): hay que cambiarla al entrar.
    debe_cambiar_contrasena: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    origen_identidad: Mapped[str] = mapped_column(String(20), default="local")  # local | ldap | oidc
    id_externo: Mapped[str | None] = mapped_column(String(200))
    creado: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(Fecha)

    departamento: Mapped[Departamento | None] = relationship()
    nivel: Mapped[Nivel | None] = relationship()
    puesto: Mapped[Puesto | None] = relationship()

    @property
    def nivel_orden(self) -> int:
        return self.nivel.orden if self.nivel else 1


class Sesion(Base):
    __tablename__ = "sesiones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_uuid)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="usuario")  # usuario | invitado
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    expira: Mapped[datetime] = mapped_column(Fecha)
    revocada: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    cliente: Mapped[str | None] = mapped_column(String(300))
    uso_ventana: Mapped[datetime | None] = mapped_column(Fecha)
    uso_contador: Mapped[int] = mapped_column(Integer, default=0)


class Formacion(Base):
    """Formación activa de una persona en un departamento (le da acceso a su material de formación)."""

    __tablename__ = "formaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    departamento_id: Mapped[int] = mapped_column(ForeignKey("departamentos.id", ondelete="CASCADE"))
    puesto_id: Mapped[int | None] = mapped_column(ForeignKey("puestos.id", ondelete="SET NULL"))
    estado: Mapped[str] = mapped_column(String(20), default="activa")  # activa | completada | cancelada
    inicio: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    fin_previsto: Mapped[datetime | None] = mapped_column(Fecha)
    asignada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))

    departamento: Mapped[Departamento] = relationship()
    puesto: Mapped[Puesto | None] = relationship()


# --------------------------------------------------------------------------- conocimiento


class Documento(Base):
    """Cualquier pieza de conocimiento buscable: fichero subido, instrucción publicada,
    pregunta frecuente nacida de una aportación o ficha de una nota de voz o entrevista."""

    __tablename__ = "documentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300))
    descripcion: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(20))  # pdf | office | texto | audio | imagen | instruccion | faq | ficha
    departamento_id: Mapped[int | None] = mapped_column(ForeignKey("departamentos.id", ondelete="SET NULL"), index=True)
    nivel_minimo: Mapped[int] = mapped_column(Integer, default=1)
    es_formacion: Mapped[bool] = mapped_column(Boolean, default=False)
    es_publico: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[str] = mapped_column(String(20), default="procesando")  # borrador | procesando | listo | error
    mensaje_estado: Mapped[str | None] = mapped_column(Text)
    ruta_fichero: Mapped[str | None] = mapped_column(String(500))  # relativa a dir_datos
    nombre_fichero: Mapped[str | None] = mapped_column(String(300))
    mime: Mapped[str | None] = mapped_column(String(150))
    tamano: Mapped[int | None] = mapped_column(Integer)
    contenido_texto: Mapped[str | None] = mapped_column(Text)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    validador_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    subido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    origen: Mapped[str] = mapped_column(String(20), default="subida")  # subida | instruccion | aportacion | captura
    origen_id: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    motor_id: Mapped[str | None] = mapped_column(String(100))  # id en el motor externo (WeKnora)
    fragmentos_n: Mapped[int] = mapped_column(Integer, default=0)
    creado: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    actualizado: Mapped[datetime] = mapped_column(Fecha, default=ahora, onupdate=ahora)

    departamento: Mapped[Departamento | None] = relationship()
    autor: Mapped[Usuario | None] = relationship(foreign_keys=[autor_id])
    validador: Mapped[Usuario | None] = relationship(foreign_keys=[validador_id])


class Fragmento(Base):
    """Trozo de documento con su vector y su índice de texto (motor propio)."""

    __tablename__ = "fragmentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    texto: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    metadatos: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('spanish', texto)", persisted=True))

    __table_args__ = (Index("ix_fragmentos_tsv", "tsv", postgresql_using="gin"),)


# --------------------------------------------------------------------------- captura e instrucciones


class Captura(Base):
    __tablename__ = "capturas"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # video | audio | entrevista
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    tarea_id: Mapped[int | None] = mapped_column(ForeignKey("tareas.id", ondelete="SET NULL"))
    titulo: Mapped[str | None] = mapped_column(String(300))
    ruta_original: Mapped[str | None] = mapped_column(String(500))
    nombre_fichero: Mapped[str | None] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(20), default="subida")  # subida | procesando | borrador_listo | error
    progreso: Mapped[int] = mapped_column(Integer, default=0)
    fase: Mapped[str | None] = mapped_column(String(100))
    mensaje: Mapped[str | None] = mapped_column(Text)
    duracion: Mapped[float | None] = mapped_column(Float)
    transcripcion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    escenas: Mapped[list[Any] | None] = mapped_column(JSONB)
    conversacion: Mapped[list[Any] | None] = mapped_column(JSONB)  # entrevista guiada
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    instruccion_id: Mapped[int | None] = mapped_column(Integer)
    documento_id: Mapped[int | None] = mapped_column(Integer)
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    actualizada: Mapped[datetime] = mapped_column(Fecha, default=ahora, onupdate=ahora)


class Instruccion(Base):
    __tablename__ = "instrucciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    tarea_id: Mapped[int] = mapped_column(ForeignKey("tareas.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str | None] = mapped_column(String(30))  # p. ej. IT-023
    version: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(20), default="borrador")  # borrador | en_revision | publicada | obsoleta
    titulo: Mapped[str] = mapped_column(String(300))
    resumen: Mapped[str | None] = mapped_column(Text)
    riesgos: Mapped[str | None] = mapped_column(Text)
    epis: Mapped[str | None] = mapped_column(Text)
    herramientas: Mapped[str | None] = mapped_column(Text)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    revisor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    captura_id: Mapped[int | None] = mapped_column(ForeignKey("capturas.id", ondelete="SET NULL"))
    video_ruta: Mapped[str | None] = mapped_column(String(500))
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id", ondelete="SET NULL"))
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    publicada_en: Mapped[datetime | None] = mapped_column(Fecha)

    tarea: Mapped[Tarea] = relationship()
    autor: Mapped[Usuario | None] = relationship(foreign_keys=[autor_id])
    revisor: Mapped[Usuario | None] = relationship(foreign_keys=[revisor_id])
    pasos: Mapped[list[Paso]] = relationship(
        back_populates="instruccion", cascade="all, delete-orphan", order_by="Paso.orden"
    )

    __table_args__ = (UniqueConstraint("tarea_id", "version", name="uq_instruccion_tarea_version"),)


class Paso(Base):
    __tablename__ = "pasos"
    id: Mapped[int] = mapped_column(primary_key=True)
    instruccion_id: Mapped[int] = mapped_column(ForeignKey("instrucciones.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(300))
    texto: Mapped[str | None] = mapped_column(Text)
    es_critico: Mapped[bool] = mapped_column(Boolean, default=False)
    es_seguridad: Mapped[bool] = mapped_column(Boolean, default=False)
    criterio_aceptacion: Mapped[str | None] = mapped_column(Text)
    imagen_ruta: Mapped[str | None] = mapped_column(String(500))
    clip_ruta: Mapped[str | None] = mapped_column(String(500))
    t_inicio: Mapped[float | None] = mapped_column(Float)
    t_fin: Mapped[float | None] = mapped_column(Float)

    instruccion: Mapped[Instruccion] = relationship(back_populates="pasos")


# --------------------------------------------------------------------------- formación


class Microleccion(Base):
    __tablename__ = "microlecciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    instruccion_id: Mapped[int] = mapped_column(ForeignKey("instrucciones.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(300))
    contenido: Mapped[str] = mapped_column(Text)
    punto_clave: Mapped[str | None] = mapped_column(Text)
    pregunta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {enunciado, opciones, correcta, explicacion}


class MicroleccionVista(Base):
    __tablename__ = "microleccion_vistas"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    microleccion_id: Mapped[int] = mapped_column(ForeignKey("microlecciones.id", ondelete="CASCADE"))
    completada_en: Mapped[datetime] = mapped_column(Fecha, default=ahora)

    __table_args__ = (UniqueConstraint("usuario_id", "microleccion_id", name="uq_microleccion_vista"),)


# --------------------------------------------------------------------------- modo planta


class Ejecucion(Base):
    __tablename__ = "ejecuciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    tarea_id: Mapped[int] = mapped_column(ForeignKey("tareas.id", ondelete="CASCADE"), index=True)
    instruccion_id: Mapped[int] = mapped_column(ForeignKey("instrucciones.id", ondelete="CASCADE"))
    estado: Mapped[str] = mapped_column(String(20), default="en_curso")  # en_curso | completada | abandonada
    inicio: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    fin: Mapped[datetime | None] = mapped_column(Fecha)
    consultas: Mapped[int] = mapped_column(Integer, default=0)
    consultas_criticos: Mapped[int] = mapped_column(Integer, default=0)
    foto_ruta: Mapped[str | None] = mapped_column(String(500))
    foto_veredicto: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    pasos: Mapped[list[EjecucionPaso]] = relationship(cascade="all, delete-orphan")


class EjecucionPaso(Base):
    __tablename__ = "ejecucion_pasos"
    id: Mapped[int] = mapped_column(primary_key=True)
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecuciones.id", ondelete="CASCADE"), index=True)
    paso_id: Mapped[int] = mapped_column(ForeignKey("pasos.id", ondelete="CASCADE"))
    confirmado_en: Mapped[datetime | None] = mapped_column(Fecha)
    critico_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    consultas: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("ejecucion_id", "paso_id", name="uq_ejecucion_paso"),)


# --------------------------------------------------------------------------- consultas, lagunas y aportaciones


class Consulta(Base):
    """Cada pregunta al copiloto: alimenta la curva de autonomía y las lagunas."""

    __tablename__ = "consultas"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    sesion_id: Mapped[str | None] = mapped_column(String(36))
    pregunta: Mapped[str] = mapped_column(Text)
    respuesta: Mapped[str | None] = mapped_column(Text)
    modo: Mapped[str] = mapped_column(String(20), default="normal")  # normal | socratico | planta
    fuentes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    con_respaldo: Mapped[bool] = mapped_column(Boolean, default=True)
    laguna_id: Mapped[int | None] = mapped_column(Integer)
    tarea_id: Mapped[int | None] = mapped_column(Integer, index=True)
    paso_id: Mapped[int | None] = mapped_column(Integer)
    ejecucion_id: Mapped[int | None] = mapped_column(Integer)
    modelo: Mapped[str | None] = mapped_column(String(100))
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    valoracion: Mapped[int | None] = mapped_column(Integer)  # 1 útil, -1 no útil
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora, index=True)


class Laguna(Base):
    """Pregunta que el copiloto no supo responder con respaldo. Se agrupan las parecidas."""

    __tablename__ = "lagunas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pregunta: Mapped[str] = mapped_column(Text)
    departamento_id: Mapped[int | None] = mapped_column(ForeignKey("departamentos.id", ondelete="SET NULL"), index=True)
    tarea_id: Mapped[int | None] = mapped_column(Integer)
    frecuencia: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="abierta")  # abierta | resuelta | descartada
    aportacion_id: Mapped[int | None] = mapped_column(Integer)
    ejemplos: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    primera_vez: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    ultima_vez: Mapped[datetime] = mapped_column(Fecha, default=ahora)


class Aportacion(Base):
    __tablename__ = "aportaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    departamento_id: Mapped[int | None] = mapped_column(ForeignKey("departamentos.id", ondelete="SET NULL"), index=True)
    tarea_id: Mapped[int | None] = mapped_column(ForeignKey("tareas.id", ondelete="SET NULL"))
    laguna_id: Mapped[int | None] = mapped_column(ForeignKey("lagunas.id", ondelete="SET NULL"))
    texto_original: Mapped[str | None] = mapped_column(Text)
    audio_ruta: Mapped[str | None] = mapped_column(String(500))
    duracion_audio: Mapped[float | None] = mapped_column(Float)
    transcripcion: Mapped[str | None] = mapped_column(Text)
    titulo: Mapped[str | None] = mapped_column(String(300))
    problema: Mapped[str | None] = mapped_column(Text)
    causa: Mapped[str | None] = mapped_column(Text)
    solucion: Mapped[str | None] = mapped_column(Text)
    etiquetas: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    nivel_minimo: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(20), default="procesando")  # procesando | pendiente | validada | rechazada
    validador_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    motivo_rechazo: Mapped[str | None] = mapped_column(Text)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id", ondelete="SET NULL"))
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    validada_en: Mapped[datetime | None] = mapped_column(Fecha)

    autor: Mapped[Usuario] = relationship(foreign_keys=[autor_id])
    validador: Mapped[Usuario | None] = relationship(foreign_keys=[validador_id])


# --------------------------------------------------------------------------- evaluación y competencias


class PreguntaEval(Base):
    __tablename__ = "preguntas_eval"
    id: Mapped[int] = mapped_column(primary_key=True)
    instruccion_id: Mapped[int] = mapped_column(ForeignKey("instrucciones.id", ondelete="CASCADE"), index=True)
    paso_id: Mapped[int | None] = mapped_column(ForeignKey("pasos.id", ondelete="SET NULL"))
    enunciado: Mapped[str] = mapped_column(Text)
    opciones: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    correcta: Mapped[int] = mapped_column(Integer, default=0)
    explicacion: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="propuesta")  # propuesta | aprobada | descartada
    aprobada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)


class IntentoEval(Base):
    __tablename__ = "intentos_eval"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    instruccion_id: Mapped[int] = mapped_column(ForeignKey("instrucciones.id", ondelete="CASCADE"))
    respuestas: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {pregunta_id: opcion}
    aciertos: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    puntuacion: Mapped[float] = mapped_column(Float, default=0.0)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado: Mapped[datetime] = mapped_column(Fecha, default=ahora)


class Observacion(Base):
    """Observación en el puesto: el supervisor marca cada paso viendo trabajar a la persona."""

    __tablename__ = "observaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluador_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    tarea_id: Mapped[int] = mapped_column(ForeignKey("tareas.id", ondelete="CASCADE"))
    instruccion_id: Mapped[int | None] = mapped_column(ForeignKey("instrucciones.id", ondelete="SET NULL"))
    lista: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # [{paso_id, texto, critico, ok, nota}]
    aprobada: Mapped[bool] = mapped_column(Boolean, default=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)


class NivelIluo(Base):
    """Nivel ILUO de una persona en una tarea: 0 sin iniciar, 1 I, 2 L, 3 U, 4 O."""

    __tablename__ = "iluo"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    tarea_id: Mapped[int] = mapped_column(ForeignKey("tareas.id", ondelete="CASCADE"), index=True)
    nivel: Mapped[int] = mapped_column(Integer, default=0)
    desde: Mapped[datetime | None] = mapped_column(Fecha)
    caduca: Mapped[datetime | None] = mapped_column(Fecha)
    requiere_reevaluacion: Mapped[bool] = mapped_column(Boolean, default=False)
    formador_validado: Mapped[bool] = mapped_column(Boolean, default=False)
    formador_validado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    evidencias: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actualizado: Mapped[datetime] = mapped_column(Fecha, default=ahora, onupdate=ahora)

    __table_args__ = (UniqueConstraint("usuario_id", "tarea_id", name="uq_iluo_usuario_tarea"),)


# --------------------------------------------------------------------------- trazas


class SentenciaXapi(Base):
    __tablename__ = "xapi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_uuid)
    actor_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor_nombre: Mapped[str | None] = mapped_column(String(150))
    verbo: Mapped[str] = mapped_column(String(50), index=True)
    verbo_iri: Mapped[str] = mapped_column(String(200))
    objeto_tipo: Mapped[str] = mapped_column(String(50))
    objeto_id: Mapped[str | None] = mapped_column(String(100))
    objeto_nombre: Mapped[str | None] = mapped_column(String(300))
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    contexto: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sentencia: Mapped[dict[str, Any]] = mapped_column(JSONB)
    momento: Mapped[datetime] = mapped_column(Fecha, default=ahora, index=True)


class Auditoria(Base):
    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, index=True)
    usuario_nombre: Mapped[str | None] = mapped_column(String(150))
    accion: Mapped[str] = mapped_column(String(100))
    entidad: Mapped[str | None] = mapped_column(String(50))
    entidad_id: Mapped[str | None] = mapped_column(String(100))
    detalle: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    momento: Mapped[datetime] = mapped_column(Fecha, default=ahora, index=True)


# --------------------------------------------------------------------------- modelos, memoria y trabajos


class ModeloIA(Base):
    __tablename__ = "modelos_ia"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))  # nombre visible
    ref: Mapped[str] = mapped_column(String(150))  # nombre en el proveedor (p. ej. ministral-3:8b)
    tipo: Mapped[str] = mapped_column(String(20), default="chat")  # chat | embeddings | vision | asr
    ubicacion: Mapped[str] = mapped_column(String(20), default="local")  # local | nube
    proveedor: Mapped[str] = mapped_column(String(50), default="ollama")
    permitido: Mapped[bool] = mapped_column(Boolean, default=False)
    predeterminado: Mapped[bool] = mapped_column(Boolean, default=False)
    soporta_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(Fecha, default=ahora)

    __table_args__ = (UniqueConstraint("ref", "tipo", name="uq_modelo_ref_tipo"),)


class Memoria(Base):
    """Recuerdo personal (solo si la persona activa la memoria)."""

    __tablename__ = "memorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    contenido: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    origen: Mapped[str | None] = mapped_column(String(50))
    creada: Mapped[datetime] = mapped_column(Fecha, default=ahora)


class Trabajo(Base):
    """Trabajo en segundo plano (indexar, procesar un vídeo, generar preguntas...)."""

    __tablename__ = "trabajos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | en_curso | completado | error
    progreso: Mapped[int] = mapped_column(Integer, default=0)
    mensaje: Mapped[str | None] = mapped_column(Text)
    entidad: Mapped[str | None] = mapped_column(String(50))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    creado: Mapped[datetime] = mapped_column(Fecha, default=ahora)
    actualizado: Mapped[datetime] = mapped_column(Fecha, default=ahora, onupdate=ahora)
