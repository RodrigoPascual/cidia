"""Aportaciones desde la planta: enviar (texto o nota de voz), revisar, validar y rechazar.

Empleados: POST /api/aportaciones, GET /mias, DELETE /{id} (solo las suyas sin revisar).
Jefes (de su departamento) y administración: GET /pendientes, PUT /{id}, POST /{id}/validar,
POST /{id}/rechazar, GET /resumen. La lógica vive en servicios/aportaciones.py.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from sqlalchemy import false, func, select, true
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from cidia.db import obtener_bd
from cidia.modelos import Aportacion, Nivel, Usuario, ahora
from cidia.seguridad import Actor, requiere_jefe, usuario_actual
from cidia.servicios import aportaciones as srv
from cidia.servicios import documentos

router = APIRouter(prefix="/api/aportaciones", tags=["aportaciones"])


class NuevaAportacion(BaseModel):
    texto: str | None = None
    tarea_id: int | None = None
    laguna_id: int | None = None


class Edicion(BaseModel):
    """Cambios del jefe. Solo se aplican los campos enviados (tarea_id: null la quita)."""

    titulo: str | None = None
    problema: str | None = None
    causa: str | None = None
    solucion: str | None = None
    etiquetas: list[str] | None = None
    nivel_minimo: int | None = None
    tarea_id: int | None = None

    def cambios(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.model_fields_set}


class Rechazo(BaseModel):
    motivo: str | None = None


def _entero(valor: Any, nombre: str) -> int | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise HTTPException(400, f"El campo «{nombre}» no es válido.") from None


def _segundos(valor: Any) -> float | None:
    """Duración que mide el navegador: solo se acepta si es razonable (la del servicio de voz manda)."""
    try:
        s = float(valor)
    except (TypeError, ValueError):
        return None
    return s if math.isfinite(s) and 0 < s <= 3600 else None


# --------------------------------------------------------------------------- empleados


@router.post("")
async def crear(request: Request, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Envía una aportación: JSON {texto, tarea_id?, laguna_id?} o multipart con `audio`
    (y opcionalmente texto, tarea_id, laguna_id y duracion en segundos).

    Es `async` solo para poder leer los dos formatos de cuerpo en la misma ruta; el trabajo con
    la base de datos y el disco se hace en el grupo de hilos, como en las rutas síncronas."""
    tipo = request.headers.get("content-type", "").lower()
    if tipo.startswith("multipart/form-data"):
        async with request.form() as formulario:
            audio = formulario.get("audio")
            if not isinstance(audio, UploadFile) or not audio.filename:
                audio = None
            texto = formulario.get("texto")
            datos = {
                "texto": texto if isinstance(texto, str) else None,
                "tarea_id": _entero(formulario.get("tarea_id"), "tarea_id"),
                "laguna_id": _entero(formulario.get("laguna_id"), "laguna_id"),
                "duracion": _segundos(formulario.get("duracion")),
            }
            return await run_in_threadpool(_crear, bd, actor, datos, audio)
    try:
        cuerpo = NuevaAportacion.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(400, "Envía el texto de la aportación (o una nota de voz).") from None
    return await run_in_threadpool(_crear, bd, actor, cuerpo.model_dump(), None)


def _crear(bd: Session, actor: Actor, datos: dict[str, Any], audio: UploadFile | None) -> dict[str, Any]:
    ap = srv.crear(bd, actor, datos.get("texto"), datos.get("tarea_id"), datos.get("laguna_id"),
                   audio=audio, duracion=datos.get("duracion"))
    bd.refresh(ap)  # el procesado pudo terminar ya (en las pruebas es inmediato)
    return srv.a_dict(bd, ap, actor)


@router.get("/mias")
def mias(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Las aportaciones de quien pregunta, con su estado, el motivo si se rechazó y lo publicado."""
    srv.rescatar_atascadas(bd)
    aps = bd.scalars(select(Aportacion).where(Aportacion.autor_id == actor.id)
                     .order_by(Aportacion.creada.desc()).limit(200)).all()
    por_estado = {e: 0 for e in srv.ESTADOS}
    for e, n in bd.execute(select(Aportacion.estado, func.count()).where(Aportacion.autor_id == actor.id)
                           .group_by(Aportacion.estado)).all():
        por_estado[e] = n
    return {"aportaciones": srv.a_dicts(bd, list(aps), actor), "resumen": por_estado}


@router.get("/opciones")
def opciones(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Tareas para el selector (las de su departamento; la administración, todas) y, para quien
    gestiona, los niveles con los que etiquetar."""
    datos: dict[str, Any] = {"tareas": srv.tareas_de(bd, actor.departamento_id, todas=actor.es_admin)}
    if actor.es_jefe:
        datos["niveles"] = [{"orden": n.orden, "nombre": n.nombre}
                            for n in bd.scalars(select(Nivel).order_by(Nivel.orden))]
    return datos


# --------------------------------------------------------------------------- jefes


def _de_mi_departamento(actor: Actor):
    """Condición SQL: aportaciones que el actor puede gestionar."""
    if actor.es_admin:
        return true()
    if actor.departamento_id is None:
        return false()
    return Aportacion.departamento_id == actor.departamento_id


@router.get("/pendientes")
def pendientes(actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Bandeja del jefe: pendientes (y en proceso) de su departamento, las más recientes primero."""
    srv.rescatar_atascadas(bd)
    filtro = _de_mi_departamento(actor)
    aps = bd.scalars(select(Aportacion).where(filtro, Aportacion.estado.in_(srv.ABIERTAS))
                     .order_by(Aportacion.creada.desc())).all()
    hace_30 = ahora() - timedelta(days=30)
    revisadas = dict(bd.execute(
        select(Aportacion.estado, func.count()).where(filtro, Aportacion.estado.in_(("validada", "rechazada")),
                                                      Aportacion.validada_en >= hace_30)
        .group_by(Aportacion.estado)).all())
    return {
        "aportaciones": srv.a_dicts(bd, list(aps), actor),
        "resumen": {
            "pendientes": sum(1 for a in aps if a.estado == "pendiente"),
            "procesando": sum(1 for a in aps if a.estado == "procesando"),
            "validadas_30d": revisadas.get("validada", 0),
            "rechazadas_30d": revisadas.get("rechazada", 0),
        },
    }


@router.get("/resumen")
def resumen(actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Aportaciones validadas por persona de su departamento (evidencia del nivel O)."""
    dep = None if actor.es_admin else actor.departamento_id
    if dep is None and not actor.es_admin:
        return {"personas": []}
    conteo = srv.validadas_por_persona(bd, dep)
    q = select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre)
    if dep is not None:
        q = q.where(Usuario.departamento_id == dep)
    personas = [{"usuario_id": u.id, "nombre": u.nombre, "validadas": conteo.get(u.id, 0)} for u in bd.scalars(q)]
    personas.sort(key=lambda p: -p["validadas"])
    return {"personas": personas}


@router.get("/{aportacion_id}")
def detalle(aportacion_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return srv.a_dict(bd, srv.obtener(bd, actor, aportacion_id), actor)


@router.put("/{aportacion_id}")
def editar(aportacion_id: int, datos: Edicion, actor: Actor = Depends(requiere_jefe),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ap = srv.obtener(bd, actor, aportacion_id, gestionar=True, bloquear=True)
    srv.editar(bd, actor, ap, datos.cambios())
    bd.commit()
    return srv.a_dict(bd, ap, actor)


@router.post("/{aportacion_id}/validar")
def validar(aportacion_id: int, datos: Edicion | None = None, actor: Actor = Depends(requiere_jefe),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Valida y publica como pregunta frecuente. Admite los últimos cambios en el mismo envío."""
    ap = srv.obtener(bd, actor, aportacion_id, gestionar=True, bloquear=True)
    if datos is not None and datos.cambios():
        srv.editar(bd, actor, ap, datos.cambios())
    doc = srv.validar(bd, actor, ap)
    bd.refresh(ap)
    bd.refresh(doc)
    return {"aportacion": srv.a_dict(bd, ap, actor), "documento": documentos.a_dict(bd, doc)}


@router.post("/{aportacion_id}/rechazar")
def rechazar(aportacion_id: int, datos: Rechazo | None = None, actor: Actor = Depends(requiere_jefe),
             bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Rechaza con un motivo obligatorio (sin cuerpo, el mismo aviso en castellano que sin motivo)."""
    ap = srv.obtener(bd, actor, aportacion_id, gestionar=True, bloquear=True)
    srv.rechazar(bd, actor, ap, datos.motivo if datos else None)
    return srv.a_dict(bd, ap, actor)


@router.delete("/{aportacion_id}")
def retirar(aportacion_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    """El autor retira una aportación que aún no se ha revisado (bloqueada, por si su jefe la valida a la vez)."""
    ap = bd.get(Aportacion, aportacion_id, with_for_update=True)
    if ap is None or ap.autor_id != actor.id:
        raise HTTPException(404, "Aportación no encontrada.")
    srv.borrar(bd, actor, ap)
    return {"ok": True}
