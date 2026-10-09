"""Evaluación: pendientes, revisión de preguntas, cuestionario y observación en el puesto."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.seguridad import Actor, requiere_experto, requiere_jefe, usuario_actual
from cidia.servicios import evaluacion

router = APIRouter(prefix="/api/evaluacion", tags=["evaluación"])


class PreguntaNueva(BaseModel):
    instruccion_id: int
    enunciado: str
    opciones: list[str]
    correcta: int
    explicacion: str | None = None
    paso_id: int | None = None


class PreguntaCambio(BaseModel):
    enunciado: str | None = None
    opciones: list[str] | None = None
    correcta: int | None = None
    explicacion: str | None = None
    paso_id: int | None = None
    estado: str | None = None


class Generacion(BaseModel):
    n: int = 6


class Respuestas(BaseModel):
    instruccion_id: int | None = None
    # {pregunta_id: clave de la opción elegida}; por compatibilidad también vale su índice original.
    respuestas: dict[int, int | str]


class MarcaPaso(BaseModel):
    paso_id: int
    ok: bool | None = None
    nota: str | None = None


class ObservacionNueva(BaseModel):
    usuario_id: int
    tarea_id: int
    instruccion_id: int | None = None
    lista: list[MarcaPaso]
    aprobada: bool
    comentario: str | None = None


# --------------------------------------------------------------------------- pendientes


@router.get("/pendientes")
def pendientes(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Cuestionarios disponibles; además, preguntas por revisar (expertos) y observaciones sugeridas (jefes)."""
    return evaluacion.pendientes(bd, actor)


# --------------------------------------------------------------------------- preguntas (expertos)


@router.get("/preguntas")
def preguntas(instruccion_id: int, actor: Actor = Depends(requiere_experto),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return evaluacion.listar_preguntas(bd, actor, instruccion_id)


@router.post("/preguntas")
def crear_pregunta(datos: PreguntaNueva, actor: Actor = Depends(requiere_experto),
                   bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    p = evaluacion.crear_pregunta(bd, actor, datos.instruccion_id, datos.enunciado, datos.opciones, datos.correcta,
                                  datos.explicacion, datos.paso_id)
    bd.commit()
    return evaluacion.pregunta_a_dict(bd, p)


@router.put("/preguntas/{pregunta_id}")
def cambiar_pregunta(pregunta_id: int, datos: PreguntaCambio, actor: Actor = Depends(requiere_experto),
                     bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cambios = {k: getattr(datos, k) for k in datos.model_fields_set}
    p = evaluacion.cambiar_pregunta(bd, actor, pregunta_id, cambios)
    bd.commit()
    return evaluacion.pregunta_a_dict(bd, p)


@router.delete("/preguntas/{pregunta_id}")
def borrar_pregunta(pregunta_id: int, actor: Actor = Depends(requiere_experto),
                    bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    evaluacion.borrar_pregunta(bd, actor, pregunta_id)
    bd.commit()
    return {"ok": True}


@router.post("/instrucciones/{instruccion_id}/generar-preguntas")
def generar_preguntas(instruccion_id: int, datos: Generacion | None = None, actor: Actor = Depends(requiere_experto),
                      bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ins = evaluacion.instruccion_para_revisar(bd, actor, instruccion_id)
    if ins.estado == "obsoleta":
        raise HTTPException(400, "Esta versión de la instrucción está obsoleta: genera las preguntas en la vigente.")
    if not ins.pasos:
        raise HTTPException(400, "La instrucción no tiene pasos de los que sacar preguntas.")
    if evaluacion.generando(bd, ins.id):
        raise HTTPException(409, "Ya se están generando preguntas para esta instrucción. Espera a que terminen.")
    n = max(1, min(12, (datos.n if datos else 6)))
    bd.commit()  # libera la sesión antes de lanzar el trabajo
    trabajo_id = evaluacion.encolar_generacion(ins.id, n, usuario_id=actor.id)
    return {"trabajo_id": trabajo_id, "mensaje": f"Generando {n} preguntas nuevas. Aparecerán como propuestas."}


# --------------------------------------------------------------------------- cuestionario (empleados)


@router.get("/cuestionario/{tarea_id}")
def cuestionario(tarea_id: int, actor: Actor = Depends(usuario_actual),
                 bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Preguntas aprobadas de la versión vigente, en orden aleatorio y sin la respuesta correcta."""
    return evaluacion.cuestionario(bd, actor, tarea_id)


@router.post("/cuestionario/{tarea_id}/responder")
def responder(tarea_id: int, datos: Respuestas, actor: Actor = Depends(usuario_actual),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    resultado = evaluacion.responder(bd, actor, tarea_id, datos.respuestas, datos.instruccion_id)
    bd.commit()
    return resultado


# --------------------------------------------------------------------------- observación (jefes)


@router.get("/observacion/plantilla")
def plantilla(usuario_id: int, tarea_id: int, actor: Actor = Depends(requiere_jefe),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return evaluacion.plantilla_observacion(bd, actor, usuario_id, tarea_id)


@router.post("/observaciones")
def observar(datos: ObservacionNueva, actor: Actor = Depends(requiere_jefe),
             bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    resultado = evaluacion.registrar_observacion(
        bd, actor, datos.usuario_id, datos.tarea_id, [m.model_dump() for m in datos.lista], datos.aprobada,
        datos.comentario, datos.instruccion_id)
    bd.commit()
    return resultado
