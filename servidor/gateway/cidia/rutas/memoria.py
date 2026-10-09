"""Memoria personal: estado, recuerdos y borrado (cada persona solo ve y toca los suyos)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.modelos import Usuario
from cidia.seguridad import Actor, usuario_actual
from cidia.servicios import memoria
from cidia.xapi import registrar

router = APIRouter(prefix="/api/memoria", tags=["memoria"])


class EstadoMemoria(BaseModel):
    activa: bool


class NuevoRecuerdo(BaseModel):
    contenido: str = Field(min_length=1, max_length=memoria.MAX_LONGITUD)


def _estado(bd: Session, usuario: Usuario) -> dict[str, Any]:
    recuerdos = memoria.listar(bd, usuario.id)
    return {
        "activa": usuario.memoria_activa,
        "recuerdos": [memoria.a_dict(m) for m in recuerdos],
        "total": len(recuerdos),
        "maximo": memoria.MAX_RECUERDOS,
    }


def _usuario(bd: Session, actor: Actor) -> Usuario:
    u = bd.get(Usuario, actor.id)
    if u is None:
        raise HTTPException(401, "Tu cuenta no está activa.")
    return u


@router.get("")
def ver(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return _estado(bd, _usuario(bd, actor))


@router.put("")
def cambiar(datos: EstadoMemoria, actor: Actor = Depends(usuario_actual),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Activa o desactiva la memoria. Desactivarla no borra los recuerdos: deja de usarlos."""
    u = _usuario(bd, actor)
    if u.memoria_activa != datos.activa:
        memoria.activar(bd, u, datos.activa)
        registrar(bd, actor, "configuro", "memoria", u.id, "Memoria personal", resultado={"activa": datos.activa})
        bd.commit()
    return _estado(bd, u)


@router.post("")
def anadir(datos: NuevoRecuerdo, actor: Actor = Depends(usuario_actual),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Añade un recuerdo a mano (p. ej. «Trabajo en el turno de noche»)."""
    u = _usuario(bd, actor)
    if not u.memoria_activa:
        raise HTTPException(400, "Activa la memoria personal para guardar recuerdos.")
    try:
        m = memoria.anadir(bd, u.id, datos.contenido, origen="manual")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    bd.commit()
    return memoria.a_dict(m)


@router.delete("/{memoria_id}")
def borrar_uno(memoria_id: int = Path(ge=1, le=2**31 - 1), actor: Actor = Depends(usuario_actual),
               bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    if not memoria.borrar(bd, actor.id, memoria_id):
        raise HTTPException(404, "No se encuentra ese recuerdo.")
    registrar(bd, actor, "borro", "memoria", actor.id, "Memoria personal", resultado={"borrados": 1})
    bd.commit()
    return {"ok": True}


@router.delete("")
def borrar_todo(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    n = memoria.borrar_todo(bd, actor.id)
    # Solo se apunta cuántos: el contenido de los recuerdos no se copia al registro.
    registrar(bd, actor, "borro", "memoria", actor.id, "Memoria personal", resultado={"borrados": n})
    bd.commit()
    return {"ok": True, "borrados": n}
