"""Progreso: pasaporte de habilidades, matriz ILUO del equipo y de la planta, acciones sobre niveles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.modelos import Tarea, Usuario
from cidia.seguridad import Actor, requiere_admin, requiere_jefe, usuario_actual
from cidia.servicios import iluo, progreso

router = APIRouter(prefix="/api/progreso", tags=["progreso"])


class Ajuste(BaseModel):
    nivel: int
    motivo: str


@router.get("/yo")
def yo(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    datos = progreso.mi_progreso(bd, actor)
    bd.commit()  # el recálculo puede haber aplicado caducidades o evidencias nuevas
    return datos


@router.get("/persona/{usuario_id}")
def persona(usuario_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    datos = progreso.progreso_persona(bd, actor, usuario_id)
    bd.commit()
    return datos


@router.get("/equipo")
def equipo(departamento_id: int | None = None, actor: Actor = Depends(requiere_jefe),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return progreso.equipo(bd, actor, departamento_id)


@router.get("/planta")
def planta(actor: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return progreso.planta(bd, actor)


@router.get("/iluo/{usuario_id}/{tarea_id}")
def detalle(usuario_id: int, tarea_id: int, actor: Actor = Depends(usuario_actual),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    datos = progreso.detalle(bd, actor, usuario_id, tarea_id)
    bd.commit()
    return datos


def _respuesta(bd: Session, actor: Actor, usuario_id: int, tarea_id: int) -> dict[str, Any]:
    datos = progreso.detalle(bd, actor, usuario_id, tarea_id)
    bd.commit()
    return datos


@router.post("/iluo/{usuario_id}/{tarea_id}/formador")
def validar_formador(usuario_id: int, tarea_id: int, actor: Actor = Depends(usuario_actual),
                     bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Un jefe o un experto del departamento de la tarea valida a la persona como formadora (O)."""
    iluo.validar_formador(bd, actor, usuario_id, tarea_id)
    bd.commit()  # la validación queda guardada antes de preparar la respuesta
    return _respuesta(bd, actor, usuario_id, tarea_id)


@router.put("/iluo/{usuario_id}/{tarea_id}")
def ajustar(usuario_id: int, tarea_id: int, datos: Ajuste, actor: Actor = Depends(requiere_jefe),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Ajuste manual del nivel por el jefe del departamento de la tarea, con motivo (queda en auditoría)."""
    iluo.ajustar(bd, actor, usuario_id, tarea_id, datos.nivel, datos.motivo)
    bd.commit()
    usuario, tarea = bd.get(Usuario, usuario_id), bd.get(Tarea, tarea_id)
    assert usuario is not None and tarea is not None
    fila = iluo.fila_de(bd, usuario_id, tarea_id)
    ev = iluo.evaluar(bd, usuario_id, tarea, fila)  # sin recalcular: respeta el nivel que ha puesto el jefe
    datos_tarea = progreso.detalle_tarea(bd, usuario, tarea, fila, ev, con_departamento=True) if fila else {}
    return {"ok": True, "nivel": fila.nivel if fila else 0, "letra": iluo.nivel_letra(fila.nivel if fila else 0),
            "detalle": datos_tarea}
