"""Inicio de sesión, modo invitado y perfil."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.identidad import autenticar
from cidia.modelos import Formacion, ahora
from cidia.seguridad import Actor, actor_actual, crear_sesion, hash_contrasena, usuario_actual, verificar_contrasena
from cidia.xapi import registrar

router = APIRouter(prefix="/api/auth", tags=["sesión"])


class Credenciales(BaseModel):
    usuario: str
    contrasena: str


class CambioContrasena(BaseModel):
    actual: str
    nueva: str


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split() if p]
    return ("".join(p[0] for p in partes[:2]) or "?").upper()


def servicios(actor: Actor) -> list[str]:
    """Servicios (pantallas) que la interfaz debe mostrar a cada persona."""
    if actor.es_invitado:
        return ["chat"]
    s = ["chat", "consultar", "planta", "formacion", "evaluacion", "aportaciones", "progreso", "espacio", "perfil"]
    if actor.es_experto:
        s += ["captura", "instrucciones", "revisar_preguntas"]
    if actor.es_jefe:
        s += ["validar", "documentos", "equipo", "lagunas", "observar"]
    if actor.es_admin:
        s += ["admin", "organizacion", "empleados", "modelos", "registro", "sistema"]
    return s


def perfil(bd: Session, actor: Actor) -> dict[str, Any]:
    if actor.es_invitado:
        return {"invitado": True, "nombre": "Invitado", "iniciales": "IN", "rol": "invitado", "servicios": servicios(actor)}
    u = actor.usuario
    assert u is not None
    datos: dict[str, Any] = {
        "invitado": False,
        "id": u.id,
        "usuario": u.usuario,
        "nombre": u.nombre,
        "iniciales": iniciales(u.nombre),
        "rol": u.rol,
        "es_experto": u.es_experto,
        "memoria_activa": u.memoria_activa,
        "servicios": servicios(actor),
        "puesto": u.puesto.nombre if u.puesto else None,
    }
    # Departamento y nivel viven en el servidor; solo se muestran a quien gestiona.
    if actor.es_jefe:
        datos["departamento"] = {"id": u.departamento_id, "nombre": u.departamento.nombre} if u.departamento else None
        datos["nivel"] = {"orden": u.nivel.orden, "nombre": u.nivel.nombre} if u.nivel else None
    formaciones = bd.scalars(select(Formacion).where(Formacion.usuario_id == u.id, Formacion.estado == "activa")).all()
    datos["formaciones"] = [{"id": f.id, "departamento": f.departamento.nombre,
                             "puesto": f.puesto.nombre if f.puesto else None} for f in formaciones]
    return datos


@router.post("/login")
def login(datos: Credenciales, request: Request, bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    u = autenticar(bd, datos.usuario, datos.contrasena)
    if u is None:
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    u.ultimo_acceso = ahora()
    sesion, token = crear_sesion(bd, u, request)
    actor = Actor(sesion=sesion, usuario=u)
    registrar(bd, actor, "inicio", "sesion", sesion.id, "Inicio de sesión")
    bd.commit()
    return {"token": token, "expira": sesion.expira.isoformat(), "perfil": perfil(bd, actor)}


@router.post("/invitado")
def invitado(request: Request, bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    sesion, token = crear_sesion(bd, None, request)
    bd.commit()
    actor = Actor(sesion=sesion, usuario=None)
    return {"token": token, "expira": sesion.expira.isoformat(), "perfil": perfil(bd, actor)}


@router.get("/yo")
def yo(actor: Actor = Depends(actor_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return perfil(bd, actor)


@router.post("/salir")
def salir(actor: Actor = Depends(actor_actual), bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    s = bd.merge(actor.sesion)
    s.revocada = True
    bd.commit()
    return {"ok": True}


@router.post("/contrasena")
def cambiar_contrasena(datos: CambioContrasena, actor: Actor = Depends(usuario_actual),
                       bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    u = bd.merge(actor.usuario)
    if u.origen_identidad != "local":
        raise HTTPException(400, "Tu contraseña se gestiona en el directorio de la empresa.")
    if not verificar_contrasena(u.hash_contrasena, datos.actual):
        raise HTTPException(400, "La contraseña actual no es correcta.")
    if len(datos.nueva) < 8:
        raise HTTPException(400, "La nueva contraseña debe tener al menos 8 caracteres.")
    u.hash_contrasena = hash_contrasena(datos.nueva)
    bd.commit()
    return {"ok": True}
