"""Interfaz común de los conectores de identidad."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from cidia.modelos import Usuario


@dataclass
class IdentidadExterna:
    """Lo que devuelve un directorio externo tras autenticar a alguien."""

    id_externo: str
    usuario: str
    nombre: str
    email: str | None = None
    grupos: list[str] = field(default_factory=list)


class ConectorIdentidad(ABC):
    nombre = "base"

    @abstractmethod
    def autenticar(self, bd: Session, usuario: str, contrasena: str) -> Usuario | None:
        """Devuelve el usuario de CidIA si las credenciales son válidas."""

    def vincular(self, bd: Session, ident: IdentidadExterna, origen: str) -> Usuario:
        """Busca o crea el usuario de CidIA que corresponde a una identidad externa.

        Departamento, nivel y rol se siguen gestionando en CidIA; el directorio solo
        confirma quién es la persona.
        """
        u = bd.scalar(select(Usuario).where(Usuario.origen_identidad == origen, Usuario.id_externo == ident.id_externo))
        if u is None:
            u = bd.scalar(select(Usuario).where(Usuario.usuario == ident.usuario))
        if u is None:
            u = Usuario(usuario=ident.usuario, nombre=ident.nombre, email=ident.email, rol="empleado")
            bd.add(u)
        u.origen_identidad = origen
        u.id_externo = ident.id_externo
        u.nombre = ident.nombre or u.nombre
        u.email = ident.email or u.email
        bd.flush()
        return u
