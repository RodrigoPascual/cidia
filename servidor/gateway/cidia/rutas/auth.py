"""Inicio de sesión, modo invitado y perfil."""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.identidad import autenticar
from cidia.modelos import Formacion, Sesion, ahora
from cidia.seguridad import Actor, actor_actual, crear_sesion, hash_contrasena, usuario_actual, verificar_contrasena
from cidia.xapi import registrar

router = APIRouter(prefix="/api/auth", tags=["sesión"])

# Límites contra la fuerza bruta y el abuso del modo invitado (el límite de uso de los invitados es
# por sesión: sin este tope, abrir sesiones nuevas lo saltaría).
FALLOS_POR_USUARIO = 8  # intentos fallidos con un mismo usuario desde una misma dirección
FALLOS_POR_IP = 40  # intentos fallidos desde una misma dirección (probar muchos usuarios)
VENTANA_FALLOS = 15 * 60  # segundos
INVITADOS_POR_IP_HORA = 60  # sesiones de invitado nuevas por dirección y hora
_fallos: dict[str, deque[float]] = {}
_cerrojo = threading.Lock()


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _vigentes(clave: str, momento: float) -> deque[float]:
    cola = _fallos.setdefault(clave, deque())
    while cola and momento - cola[0] > VENTANA_FALLOS:
        cola.popleft()
    return cola


def _comprobar_intentos(usuario: str, ip: str) -> None:
    """429 si hay demasiados fallos recientes (antes de verificar: tampoco se gasta argon2)."""
    momento = time.monotonic()
    with _cerrojo:
        if len(_fallos) > 10_000:  # se olvidan las claves sin fallos recientes
            for k in [k for k, v in _fallos.items() if not v or momento - v[-1] > VENTANA_FALLOS]:
                del _fallos[k]
        demasiados = (len(_vigentes(f"u:{usuario}|{ip}", momento)) >= FALLOS_POR_USUARIO
                      or len(_vigentes(f"ip:{ip}", momento)) >= FALLOS_POR_IP)
    if demasiados:
        raise HTTPException(429, "Demasiados intentos fallidos. Espera unos minutos antes de volver a probar.")


def _apuntar_fallo(usuario: str, ip: str) -> None:
    momento = time.monotonic()
    with _cerrojo:
        _vigentes(f"u:{usuario}|{ip}", momento).append(momento)
        _vigentes(f"ip:{ip}", momento).append(momento)


class Credenciales(BaseModel):
    usuario: str = Field(max_length=200)
    contrasena: str = Field(max_length=1000)


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
        # Contraseña inicial o temporal: la interfaz pide cambiarla antes de seguir.
        "debe_cambiar_contrasena": bool(u.debe_cambiar_contrasena and u.origen_identidad == "local"),
        # Con LDAP u OIDC la contraseña es la del directorio de la empresa: «Mi perfil» no ofrece cambiarla.
        "contrasena_gestionable": u.origen_identidad == "local",
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
    clave, ip = datos.usuario.strip().lower(), _ip(request)
    _comprobar_intentos(clave, ip)
    u = autenticar(bd, datos.usuario, datos.contrasena)
    if u is None:
        _apuntar_fallo(clave, ip)
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    with _cerrojo:
        _fallos.pop(f"u:{clave}|{ip}", None)
    u.ultimo_acceso = ahora()
    sesion, token = crear_sesion(bd, u, request)
    actor = Actor(sesion=sesion, usuario=u)
    registrar(bd, actor, "inicio", "sesion", sesion.id, "Inicio de sesión")
    bd.commit()
    return {"token": token, "expira": sesion.expira.isoformat(), "perfil": perfil(bd, actor)}


@router.post("/invitado")
def invitado(request: Request, bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    recientes = bd.scalar(select(func.count(Sesion.id)).where(
        Sesion.tipo == "invitado", Sesion.ip == _ip(request), Sesion.creada >= ahora() - timedelta(hours=1))) or 0
    if recientes >= INVITADOS_POR_IP_HORA:
        raise HTTPException(429, "Se han abierto demasiadas sesiones de invitado desde este equipo. "
                                 "Inicia sesión o inténtalo dentro de un rato.")
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
    if datos.nueva == datos.actual:
        raise HTTPException(400, "La nueva contraseña tiene que ser distinta de la actual.")
    u.hash_contrasena = hash_contrasena(datos.nueva)
    u.debe_cambiar_contrasena = False
    # Las demás sesiones abiertas con la contraseña anterior dejan de valer; esta sigue.
    bd.execute(update(Sesion).where(Sesion.usuario_id == u.id, Sesion.id != actor.sesion.id,
                                    Sesion.revocada.is_(False)).values(revocada=True))
    bd.commit()
    return {"ok": True}
