"""Datos sintéticos para las pruebas de evaluación, ILUO y progreso.

Cada prueba crea su propia tarea (con código único) para no depender del orden de ejecución:
la base de datos de pruebas se comparte entre todas las pruebas de la misma clave.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from cidia.modelos import (
    Ejecucion,
    Instruccion,
    IntentoEval,
    NivelIluo,
    Observacion,
    Paso,
    PreguntaEval,
    Tarea,
    Usuario,
    ahora,
)
from cidia.seguridad import Actor

PASOS = (
    ("Colocar la brida en el útil", False, None),
    ("Apretar los cuatro tornillos en cruz a 25 N·m", True, "Par de 25 N·m comprobado con la llave dinamométrica"),
    ("Verificar la estanqueidad con la prueba de aire", True, "Sin caída de presión en 30 segundos"),
    ("Etiquetar la pieza y dejarla en el carro", False, "Etiqueta legible con el lote"),
)


def actor(u: Usuario) -> Actor:
    return Actor(sesion=None, usuario=u)  # type: ignore[arg-type]


def nueva_tarea(bd: Session, planta: Any, dep: str = "ot", nombre: str | None = None) -> Tarea:
    codigo = "T-" + uuid.uuid4().hex[:6].upper()
    t = Tarea(puesto_id=planta.puestos[dep].id, codigo=codigo, nombre=nombre or f"Tarea de prueba {codigo}",
              criticidad=3)
    bd.add(t)
    bd.commit()
    return t


def nueva_instruccion(bd: Session, tarea: Tarea, version: int = 1, estado: str = "publicada",
                      pasos: tuple[tuple[str, bool, str | None], ...] = PASOS) -> Instruccion:
    ins = Instruccion(tarea_id=tarea.id, codigo=tarea.codigo, version=version, estado=estado,
                      titulo=f"{tarea.nombre} v{version}", publicada_en=ahora() if estado == "publicada" else None)
    for i, (titulo, critico, criterio) in enumerate(pasos, start=1):
        ins.pasos.append(Paso(orden=i, titulo=titulo, texto=f"Explicación del paso {i}: {titulo.lower()}.",
                              es_critico=critico, criterio_aceptacion=criterio))
    bd.add(ins)
    bd.commit()
    return ins


def pregunta(bd: Session, ins: Instruccion, enunciado: str, opciones: list[str], correcta: int,
             estado: str = "aprobada", paso: Paso | None = None) -> PreguntaEval:
    p = PreguntaEval(instruccion_id=ins.id, paso_id=paso.id if paso else None, enunciado=enunciado,
                     opciones=opciones, correcta=correcta, explicacion=f"Porque es «{opciones[correcta]}».",
                     estado=estado)
    bd.add(p)
    bd.commit()
    return p


def preguntas_basicas(bd: Session, ins: Instruccion) -> list[PreguntaEval]:
    """Dos preguntas aprobadas, una propuesta y una descartada."""
    return [
        pregunta(bd, ins, "¿A qué par se aprietan los tornillos?", ["10 N·m", "25 N·m", "50 N·m"], 1,
                 paso=ins.pasos[1]),
        pregunta(bd, ins, "¿Cuánto dura la prueba de aire?", ["30 segundos", "5 minutos", "1 hora"], 0,
                 paso=ins.pasos[2]),
        pregunta(bd, ins, "Pregunta todavía propuesta", ["a", "b", "c"], 2, estado="propuesta"),
        pregunta(bd, ins, "Pregunta descartada", ["a", "b", "c"], 0, estado="descartada"),
    ]


def ejecucion(bd: Session, usuario: Usuario, tarea: Tarea, ins: Instruccion, estado: str = "completada",
              consultas: int = 0, criticos: int = 0, cuando: datetime | None = None) -> Ejecucion:
    inicio = cuando or ahora() - timedelta(minutes=30)
    e = Ejecucion(usuario_id=usuario.id, tarea_id=tarea.id, instruccion_id=ins.id, estado=estado, inicio=inicio,
                  fin=inicio + timedelta(minutes=20) if estado == "completada" else None,
                  consultas=consultas, consultas_criticos=criticos)
    bd.add(e)
    bd.commit()
    return e


def intento(bd: Session, usuario: Usuario, ins: Instruccion, aprobado: bool = True,
            cuando: datetime | None = None) -> IntentoEval:
    i = IntentoEval(usuario_id=usuario.id, instruccion_id=ins.id, respuestas={}, aciertos=2 if aprobado else 0,
                    total=2, puntuacion=1.0 if aprobado else 0.0, aprobado=aprobado, creado=cuando or ahora())
    bd.add(i)
    bd.commit()
    return i


def observacion(bd: Session, evaluador: Usuario, usuario: Usuario, tarea: Tarea, ins: Instruccion,
                aprobada: bool = True, cuando: datetime | None = None) -> Observacion:
    o = Observacion(evaluador_id=evaluador.id, usuario_id=usuario.id, tarea_id=tarea.id, instruccion_id=ins.id,
                    lista=[{"paso_id": p.id, "texto": p.titulo, "critico": p.es_critico, "ok": True, "nota": None}
                           for p in ins.pasos],
                    aprobada=aprobada, creada=cuando or ahora())
    bd.add(o)
    bd.commit()
    return o


def hasta_l(bd: Session, usuario: Usuario, tarea: Tarea, ins: Instruccion) -> None:
    """Evidencias suficientes para L: cuestionario aprobado y tres ejecuciones completadas."""
    intento(bd, usuario, ins)
    for _ in range(3):
        ejecucion(bd, usuario, tarea, ins)


def nivel_guardado(bd: Session, usuario: Usuario, tarea: Tarea) -> NivelIluo | None:
    from sqlalchemy import select

    bd.expire_all()
    return bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == usuario.id, NivelIluo.tarea_id == tarea.id))
