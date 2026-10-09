"""Captura del conocimiento: vídeo, nota de voz y entrevista guiada (expertos, jefes y administración)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.seguridad import Actor, requiere_experto
from cidia.servicios import captura

router = APIRouter(prefix="/api/captura", tags=["captura"])


class InicioEntrevista(BaseModel):
    tarea_id: int | None = None
    tema: str | None = None


class RespuestaEntrevista(BaseModel):
    texto: str | None = None
    saltar: bool = False


class FinEntrevista(BaseModel):
    generar: Literal["ficha", "instruccion"] = "ficha"


class EdicionFicha(BaseModel):
    titulo: str | None = None
    contenido: str | None = None
    etiquetas: list[str] | None = None


def _tarea_id(valor: str | None) -> int | None:
    """El formulario puede mandar la tarea vacía («tarea nueva»)."""
    if valor is None or not str(valor).strip():
        return None
    try:
        return int(valor)
    except ValueError:
        raise HTTPException(400, "La tarea indicada no es válida.") from None


@router.get("")
def mis_capturas(actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    return captura.listar(bd, actor)


@router.post("", include_in_schema=False)  # alias de /video (forma corta del encargo: POST /api/captura)
@router.post("/video")
def subir_video(
    fichero: UploadFile = File(...),
    tarea_id: str | None = Form(None),
    titulo: str | None = Form(None),
    actor: Actor = Depends(requiere_experto),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    cap = captura.crear_video(bd, actor, fichero, _tarea_id(tarea_id), titulo)
    return captura.a_dict(bd, cap)


@router.post("/audio")
def subir_nota_voz(
    fichero: UploadFile = File(...),
    tarea_id: str | None = Form(None),
    titulo: str | None = Form(None),
    actor: Actor = Depends(requiere_experto),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    cap = captura.crear_nota_voz(bd, actor, fichero, _tarea_id(tarea_id), titulo)
    return captura.a_dict(bd, cap)


@router.post("/entrevista")
def iniciar_entrevista(datos: InicioEntrevista, actor: Actor = Depends(requiere_experto),
                       bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cap = captura.iniciar_entrevista(bd, actor, datos.tarea_id, datos.tema)
    return captura.a_dict(bd, cap, detalle=True)


@router.get("/{captura_id}")
def detalle(captura_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return captura.a_dict(bd, captura.obtener(bd, actor, captura_id), detalle=True)


@router.delete("/{captura_id}")
def borrar(captura_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    captura.borrar(bd, actor, captura_id)
    return {"ok": True}


@router.post("/{captura_id}/reintentar")
def reintentar(captura_id: int, actor: Actor = Depends(requiere_experto), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return captura.a_dict(bd, captura.reintentar(bd, actor, captura_id))


@router.post("/{captura_id}/entrevista/responder")
def responder(captura_id: int, datos: RespuestaEntrevista, actor: Actor = Depends(requiere_experto),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cap = captura.responder_entrevista(bd, actor, captura_id, texto=datos.texto, saltar=datos.saltar)
    return captura.a_dict(bd, cap, detalle=True)


@router.post("/{captura_id}/entrevista/responder-audio")
def responder_audio(captura_id: int, fichero: UploadFile = File(...), actor: Actor = Depends(requiere_experto),
                    bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cap = captura.responder_entrevista(bd, actor, captura_id, audio=fichero)
    return captura.a_dict(bd, cap, detalle=True)


@router.post("/{captura_id}/entrevista/finalizar")
def finalizar(captura_id: int, datos: FinEntrevista | None = None, actor: Actor = Depends(requiere_experto),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cap = captura.finalizar_entrevista(bd, actor, captura_id, (datos or FinEntrevista()).generar)
    return captura.a_dict(bd, cap, detalle=True)


@router.put("/{captura_id}/ficha")
def editar_ficha(captura_id: int, datos: EdicionFicha, actor: Actor = Depends(requiere_experto),
                 bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cap = captura.editar_ficha(bd, actor, captura_id, datos.model_dump(exclude_unset=True))
    return captura.a_dict(bd, cap, detalle=True)


@router.post("/{captura_id}/ficha/publicar")
def publicar_ficha(captura_id: int, actor: Actor = Depends(requiere_experto),
                   bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    cap = captura.publicar_ficha(bd, actor, captura_id)
    return captura.a_dict(bd, cap, detalle=True)
