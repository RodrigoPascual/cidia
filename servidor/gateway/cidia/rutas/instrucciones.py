"""Instrucciones de trabajo versionadas (expertos, jefes y administración de cada departamento)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.seguridad import Actor, requiere_experto
from cidia.servicios import instrucciones

router = APIRouter(prefix="/api/instrucciones", tags=["instrucciones"])


class PasoEntrada(BaseModel):
    id: int | None = None
    titulo: str = ""
    texto: str | None = None
    es_critico: bool = False
    es_seguridad: bool = False
    criterio_aceptacion: str | None = None


class NuevaInstruccion(BaseModel):
    tarea_id: int
    titulo: str | None = None
    resumen: str | None = None
    riesgos: str | None = None
    epis: str | None = None
    herramientas: str | None = None
    pasos: list[PasoEntrada] = Field(default_factory=list)


class EdicionInstruccion(BaseModel):
    titulo: str | None = None
    codigo: str | None = None
    resumen: str | None = None
    riesgos: str | None = None
    epis: str | None = None
    herramientas: str | None = None
    pasos: list[PasoEntrada] | None = None


@router.get("")
def listar(tarea_id: int | None = None, departamento_id: int | None = None, estado: str | None = None,
           q: str | None = None, actor: Actor = Depends(requiere_experto),
           bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    return instrucciones.listar(bd, actor, tarea_id=tarea_id, departamento_id=departamento_id, estado=estado, texto=q)


@router.get("/tareas")
def tareas(actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    """Tareas que la persona puede capturar o documentar (selectores de tarea)."""
    return instrucciones.tareas_gestionables(bd, actor)


@router.post("")
def crear(datos: NuevaInstruccion, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ins = instrucciones.crear_manual(bd, actor, datos.model_dump())
    return instrucciones.detalle(bd, actor, ins.id)


@router.get("/{instruccion_id}")
def detalle(instruccion_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return instrucciones.detalle(bd, actor, instruccion_id)


@router.put("/{instruccion_id}")
def editar(instruccion_id: int, datos: EdicionInstruccion, actor: Actor = Depends(requiere_experto),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cambios = datos.model_dump(exclude_unset=True)
    if datos.pasos is not None:
        cambios["pasos"] = [p.model_dump() for p in datos.pasos]
    instrucciones.editar(bd, actor, instruccion_id, cambios)
    return instrucciones.detalle(bd, actor, instruccion_id)


@router.delete("/{instruccion_id}")
def borrar(instruccion_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    instrucciones.borrar_borrador(bd, actor, instruccion_id)
    return {"ok": True}


@router.post("/{instruccion_id}/publicar")
def publicar(instruccion_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ins, reevaluaciones = instrucciones.publicar_con_detalle(bd, actor, instruccion_id)
    return {**instrucciones.detalle(bd, actor, ins.id), "reevaluaciones": reevaluaciones}


@router.post("/{instruccion_id}/nueva-version")
def nueva_version(instruccion_id: int, actor: Actor = Depends(requiere_experto),
                  bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ins, ya_existia = instrucciones.nueva_version(bd, actor, instruccion_id)
    return {**instrucciones.detalle(bd, actor, ins.id), "ya_existia": ya_existia}


@router.get("/{instruccion_id}/versiones")
def versiones(instruccion_id: int, actor: Actor = Depends(requiere_experto),
              bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    return instrucciones.versiones(bd, actor, instruccion_id)


@router.get("/{instruccion_id}/diferencias")
def diferencias(instruccion_id: int, con: int | None = None, actor: Actor = Depends(requiere_experto),
                bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return instrucciones.diferencias(bd, actor, instruccion_id, con)


@router.post("/{instruccion_id}/pasos/{paso_id}/imagen")
def cambiar_imagen(instruccion_id: int, paso_id: int, fichero: UploadFile = File(...),
                   actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    instrucciones.cambiar_imagen(bd, actor, instruccion_id, paso_id, fichero)
    return instrucciones.detalle(bd, actor, instruccion_id)
