"""Módulo de identidad intercambiable.

El resto de CidIA solo usa `autenticar()`. Para conectar el directorio de una empresa
basta con cambiar CIDIA_IDENTIDAD (local | ldap | oidc) y configurar su conector.
"""

import os

from sqlalchemy.orm import Session

from cidia.identidad.base import ConectorIdentidad, IdentidadExterna
from cidia.identidad.local import ConectorLocal
from cidia.modelos import Usuario


def conector() -> ConectorIdentidad:
    tipo = os.environ.get("CIDIA_IDENTIDAD", "local").lower()
    if tipo == "ldap":
        from cidia.identidad.ldap import ConectorLdap

        return ConectorLdap()
    if tipo == "oidc":
        from cidia.identidad.oidc import ConectorOidc

        return ConectorOidc()
    return ConectorLocal()


def autenticar(bd: Session, usuario: str, contrasena: str) -> Usuario | None:
    return conector().autenticar(bd, usuario, contrasena)


__all__ = ["ConectorIdentidad", "IdentidadExterna", "autenticar", "conector"]
