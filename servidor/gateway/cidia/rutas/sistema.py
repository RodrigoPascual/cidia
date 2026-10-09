"""Información pública del servidor y estado de los servicios."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from cidia import __version__
from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.db import obtener_bd
from cidia.ia import asr, llm
from cidia.modelos import Documento, Empresa, Trabajo
from cidia.seguridad import Actor, actor_actual, requiere_admin

router = APIRouter(tags=["sistema"])


@router.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@router.get("/api/sistema/info")
def info(bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Datos públicos que la app muestra antes de iniciar sesión."""
    empresa = bd.scalar(select(Empresa))
    return {
        "producto": "CidIA",
        "version": __version__,
        "servidor": ajustes().nombre_servidor,
        "empresa": empresa.nombre if empresa else None,
        "invitado": True,
    }


@router.get("/api/sistema/estado")
def estado(_: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    try:
        bd.execute(text("SELECT 1"))
        bd_ok = {"ok": True}
    except Exception as e:  # noqa: BLE001
        bd_ok = {"ok": False, "error": str(e)}
    try:
        motor_ok = motor().salud()
    except Exception as e:  # noqa: BLE001
        motor_ok = {"ok": False, "error": str(e)}
    docs = dict(bd.execute(select(Documento.estado, func.count()).group_by(Documento.estado)).all())
    ultimos = bd.scalars(select(Trabajo).order_by(Trabajo.id.desc()).limit(15)).all()
    return {
        "version": __version__,
        "motor_conocimiento": ajustes().motor_conocimiento,
        "servicios": {
            "base_datos": bd_ok,
            "modelos": llm.salud(),
            "voz": asr.salud(),
            "conocimiento": motor_ok,
        },
        "documentos": docs,
        "trabajos": [
            {"id": t.id, "tipo": t.tipo, "estado": t.estado, "progreso": t.progreso, "mensaje": t.mensaje,
             "creado": t.creado.isoformat()}
            for t in ultimos
        ],
    }


@router.get("/api/trabajos/{trabajo_id}")
def trabajo(trabajo_id: int, _: Actor = Depends(actor_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    t = bd.get(Trabajo, trabajo_id)
    if t is None:
        return {"id": trabajo_id, "estado": "desconocido"}
    return {"id": t.id, "tipo": t.tipo, "estado": t.estado, "progreso": t.progreso, "mensaje": t.mensaje,
            "resultado": t.resultado}
