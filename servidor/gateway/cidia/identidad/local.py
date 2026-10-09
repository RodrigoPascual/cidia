"""Cuentas guardadas en la base de datos de CidIA (conector por defecto)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cidia.identidad.base import ConectorIdentidad
from cidia.modelos import Usuario
from cidia.seguridad import verificar_contrasena


class ConectorLocal(ConectorIdentidad):
    nombre = "local"

    def autenticar(self, bd: Session, usuario: str, contrasena: str) -> Usuario | None:
        u = bd.scalar(select(Usuario).where(func.lower(Usuario.usuario) == usuario.strip().lower()))
        if u and u.activo and verificar_contrasena(u.hash_contrasena, contrasena):
            return u
        return None
