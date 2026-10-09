"""Contraseñas, sesiones, tokens, dependencias de autorización y URLs firmadas."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.db import obtener_bd
from cidia.modelos import Sesion, Usuario, ahora

_ph = PasswordHasher()


# --------------------------------------------------------------------------- contraseñas


def hash_contrasena(contrasena: str) -> str:
    return _ph.hash(contrasena)


def verificar_contrasena(hash_guardado: str | None, contrasena: str) -> bool:
    if not hash_guardado:
        return False
    try:
        return _ph.verify(hash_guardado, contrasena)
    except (VerifyMismatchError, InvalidHashError):
        return False


# --------------------------------------------------------------------------- sesiones y tokens


def crear_sesion(bd: Session, usuario: Usuario | None, request: Request | None = None) -> tuple[Sesion, str]:
    """Crea una sesión en BD y devuelve (sesion, token)."""
    a = ajustes()
    tipo = "usuario" if usuario else "invitado"
    horas = a.duracion_sesion_horas if usuario else a.duracion_invitado_horas
    s = Sesion(
        usuario_id=usuario.id if usuario else None,
        tipo=tipo,
        expira=ahora() + timedelta(hours=horas),
        ip=(request.client.host if request and request.client else None),
        cliente=(request.headers.get("user-agent", "")[:300] if request else None),
    )
    bd.add(s)
    bd.flush()
    carga = {"sid": s.id, "tipo": tipo, "exp": int(s.expira.timestamp())}
    if usuario:
        carga["sub"] = str(usuario.id)
    token = jwt.encode(carga, a.secreto_jwt, algorithm="HS256")
    return s, token


@dataclass
class Actor:
    """Quién hace la petición: un usuario con sesión o un invitado."""

    sesion: Sesion
    usuario: Usuario | None

    @property
    def es_invitado(self) -> bool:
        return self.usuario is None

    @property
    def id(self) -> int | None:
        return self.usuario.id if self.usuario else None

    @property
    def nombre(self) -> str:
        return self.usuario.nombre if self.usuario else "Invitado"

    @property
    def rol(self) -> str:
        return self.usuario.rol if self.usuario else "invitado"

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def es_jefe(self) -> bool:
        return self.rol in ("jefe", "admin")

    @property
    def es_experto(self) -> bool:
        return bool(self.usuario and (self.usuario.es_experto or self.usuario.rol in ("jefe", "admin")))

    @property
    def departamento_id(self) -> int | None:
        return self.usuario.departamento_id if self.usuario else None

    @property
    def nivel_orden(self) -> int:
        return self.usuario.nivel_orden if self.usuario else 0


def _token_de(request: Request) -> str | None:
    cab = request.headers.get("authorization", "")
    if cab.lower().startswith("bearer "):
        return cab[7:].strip()
    return request.query_params.get("token")


def actor_desde_token(bd: Session, token: str | None) -> Actor:
    """Valida un token y devuelve el actor. Lanza 401 si no es válido."""
    if not token:
        raise HTTPException(401, "Inicia sesión para continuar.")
    try:
        carga = jwt.decode(token, ajustes().secreto_jwt, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Tu sesión ha caducado. Vuelve a iniciar sesión.")
    except jwt.PyJWTError:
        raise HTTPException(401, "Sesión no válida.")
    s = bd.get(Sesion, carga.get("sid"))
    if not s or s.revocada or s.expira < datetime.now(timezone.utc):
        raise HTTPException(401, "Tu sesión ha terminado. Vuelve a iniciar sesión.")
    usuario = None
    if s.usuario_id:
        usuario = bd.get(Usuario, s.usuario_id)
        if not usuario or not usuario.activo:
            raise HTTPException(401, "Tu cuenta no está activa.")
    return Actor(sesion=s, usuario=usuario)


def actor_actual(request: Request, bd: Session = Depends(obtener_bd)) -> Actor:
    """Usuario o invitado con sesión válida."""
    return actor_desde_token(bd, _token_de(request))


def usuario_actual(actor: Actor = Depends(actor_actual)) -> Actor:
    """Exige una sesión de usuario (no invitado)."""
    if actor.es_invitado:
        raise HTTPException(401, "Esta función necesita iniciar sesión.")
    return actor


def requiere_jefe(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not actor.es_jefe:
        raise HTTPException(403, "Solo jefes y administradores pueden hacer esto.")
    return actor


def requiere_admin(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not actor.es_admin:
        raise HTTPException(403, "Solo la administración puede hacer esto.")
    return actor


def requiere_experto(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not actor.es_experto:
        raise HTTPException(403, "Solo expertos, jefes y administradores pueden hacer esto.")
    return actor


def limitar_invitado(bd: Session, actor: Actor) -> None:
    """Aplica el límite de peticiones por hora a los invitados."""
    if not actor.es_invitado:
        return
    s = actor.sesion
    ahora_ = datetime.now(timezone.utc)
    if not s.uso_ventana or ahora_ - s.uso_ventana > timedelta(hours=1):
        s.uso_ventana = ahora_
        s.uso_contador = 0
    s.uso_contador += 1
    bd.commit()
    if s.uso_contador > ajustes().invitado_limite_hora:
        raise HTTPException(429, "Has llegado al límite de consultas sin sesión. Inicia sesión o inténtalo más tarde.")


# --------------------------------------------------------------------------- URLs firmadas


def _firma(ruta: str, exp: int) -> str:
    return hmac.new(ajustes().secreto_jwt.encode(), f"{ruta}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def url_fichero(ruta: str | None, segundos: int = 6 * 3600) -> str | None:
    """URL firmada y caducable para servir un fichero de dir_datos (ruta relativa)."""
    if not ruta:
        return None
    exp = int(time.time()) + segundos
    return f"/api/ficheros/{quote(ruta)}?exp={exp}&firma={_firma(ruta, exp)}"


def comprobar_firma(ruta: str, exp: int, firma: str) -> bool:
    if exp < time.time():
        return False
    return hmac.compare_digest(_firma(ruta, exp), firma)
