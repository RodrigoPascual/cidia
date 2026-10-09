"""Conector LDAP / Active Directory (preparado, se activa con CIDIA_IDENTIDAD=ldap).

Usa ldap3 (LGPL-3.0, como biblioteca dinámica sin modificar) solo si la empresa lo pide;
no forma parte de las dependencias por defecto.

Variables: CIDIA_LDAP_URL (ldaps://dc.empresa.local), CIDIA_LDAP_BASE_DN,
CIDIA_LDAP_DOMINIO (para AD: usuario@dominio) y CIDIA_LDAP_ATRIBUTO_USUARIO (sAMAccountName).
"""

import os

from sqlalchemy.orm import Session

from cidia.identidad.base import ConectorIdentidad, IdentidadExterna
from cidia.identidad.local import ConectorLocal
from cidia.modelos import Usuario


class ConectorLdap(ConectorIdentidad):
    nombre = "ldap"

    def autenticar(self, bd: Session, usuario: str, contrasena: str) -> Usuario | None:
        # Las cuentas locales (p. ej. el administrador inicial) siguen funcionando.
        local = ConectorLocal().autenticar(bd, usuario, contrasena)
        if local and local.origen_identidad == "local":
            return local
        try:
            import ldap3  # type: ignore
        except ImportError:  # pragma: no cover
            return None
        url = os.environ["CIDIA_LDAP_URL"]
        base = os.environ["CIDIA_LDAP_BASE_DN"]
        dominio = os.environ.get("CIDIA_LDAP_DOMINIO")
        atributo = os.environ.get("CIDIA_LDAP_ATRIBUTO_USUARIO", "sAMAccountName")
        quien = f"{usuario}@{dominio}" if dominio else usuario
        servidor = ldap3.Server(url, get_info=ldap3.NONE)
        try:
            con = ldap3.Connection(servidor, user=quien, password=contrasena, auto_bind=True)
        except Exception:
            return None
        con.search(base, f"({atributo}={ldap3.utils.conv.escape_filter_chars(usuario)})",
                   attributes=["displayName", "mail", "objectGUID", "memberOf"])
        if not con.entries:
            return None
        e = con.entries[0]
        ident = IdentidadExterna(
            id_externo=str(e.objectGUID) if "objectGUID" in e else usuario,
            usuario=usuario,
            nombre=str(e.displayName) if "displayName" in e else usuario,
            email=str(e.mail) if "mail" in e else None,
            grupos=[str(g) for g in e.memberOf] if "memberOf" in e else [],
        )
        return self.vincular(bd, ident, "ldap")
