"""Formación: itinerario, micro-lecciones y regeneración por parte de expertos y jefes.

El tutor socrático no tiene ruta propia: la página de la tarea usa /api/consulta con
modo «socratico» y contexto {tarea_id}.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cidia import xapi
from cidia.db import obtener_bd
from cidia.modelos import Tarea
from cidia.seguridad import Actor, requiere_experto, usuario_actual
from cidia.servicios import formacion, planta

router = APIRouter(prefix="/api/formacion", tags=["formación"])


class Respuesta(BaseModel):
    opcion: int


@router.get("/itinerario")
def itinerario(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    tareas = formacion.itinerario(bd, actor)
    con_instruccion = [t for t in tareas if t["tiene_instruccion"]]
    return {
        "tareas": tareas,
        "formaciones": formacion.formaciones_activas(bd, actor, tareas),
        "resumen": {
            "tareas": len(tareas),
            "autonomas": sum(1 for t in tareas if t["nivel"] >= 3),
            "en_curso": sum(1 for t in tareas if 0 < t["nivel"] < 3),
            "reevaluacion": sum(1 for t in tareas if t["requiere_reevaluacion"]),
            "avance_medio": round(sum(t["avance"] for t in con_instruccion) / len(con_instruccion))
            if con_instruccion else 0,
        },
    }


@router.get("/tareas/{tarea_id}")
def tarea(tarea_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return formacion.detalle_tarea(bd, actor, tarea_id)


@router.post("/microlecciones/{microleccion_id}/vista")
def vista(microleccion_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    r = formacion.marcar_vista(bd, actor, microleccion_id)
    bd.commit()
    return r


@router.post("/microlecciones/{microleccion_id}/responder")
def responder(microleccion_id: int, datos: Respuesta, actor: Actor = Depends(usuario_actual),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    r = formacion.responder(bd, actor, microleccion_id, datos.opcion)
    bd.commit()
    return r


@router.post("/tareas/{tarea_id}/generar")
def generar(tarea_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Rehace las micro-lecciones de la instrucción vigente (en segundo plano).

    Lo decide el departamento de la tarea, no el alcance del modo planta: un jefe o experto de ese
    departamento puede regenerarlas aunque la tarea pida un nivel mayor que el suyo."""
    tarea = bd.get(Tarea, tarea_id) if planta.id_valido(tarea_id) else None
    if tarea is None or not tarea.activa:
        raise HTTPException(404, "No encontramos esa tarea.")
    if not formacion.puede_generar(bd, actor, tarea):
        raise HTTPException(403, "Solo los expertos y jefes del departamento de la tarea pueden regenerar sus micro-lecciones.")
    ins = planta.instruccion_vigente(bd, tarea.id)
    if ins is None:
        raise HTTPException(409, "Esta tarea todavía no tiene una instrucción publicada.")
    xapi.auditar(bd, actor, "regenerar_microlecciones", "instruccion", ins.id,
                 {"tarea_id": tarea.id, "codigo": ins.codigo, "version": ins.version})
    bd.commit()
    trabajo_id = formacion.encolar_generacion(ins.id, usuario_id=actor.id)
    return {"trabajo_id": trabajo_id, "instruccion_id": ins.id}
