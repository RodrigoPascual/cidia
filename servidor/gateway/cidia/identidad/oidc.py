"""Conector OpenID Connect (preparado, se activa con CIDIA_IDENTIDAD=oidc).

Para el MVP usa el flujo de contraseña del propietario del recurso (ROPC), que admiten
Keycloak y la mayoría de proveedores internos. En producción se recomienda el flujo de
código con PKCE desde la app.

Variables: CIDIA_OIDC_TOKEN_URL, CIDIA_OIDC_USERINFO_URL, CIDIA_OIDC_CLIENT_ID,
CIDIA_OIDC_CLIENT_SECRET.
"""

import os

import httpx
from sqlalchemy.orm import Session

from cidia.identidad.base import ConectorIdentidad, IdentidadExterna
from cidia.identidad.local import ConectorLocal
from cidia.modelos import Usuario


class ConectorOidc(ConectorIdentidad):
    nombre = "oidc"

    def autenticar(self, bd: Session, usuario: str, contrasena: str) -> Usuario | None:
        local = ConectorLocal().autenticar(bd, usuario, contrasena)
        if local and local.origen_identidad == "local":
            return local
        datos = {
            "grant_type": "password",
            "username": usuario,
            "password": contrasena,
            "client_id": os.environ.get("CIDIA_OIDC_CLIENT_ID", ""),
            "client_secret": os.environ.get("CIDIA_OIDC_CLIENT_SECRET", ""),
            "scope": "openid profile email",
        }
        try:
            r = httpx.post(os.environ["CIDIA_OIDC_TOKEN_URL"], data=datos, timeout=15)
            if r.status_code != 200:
                return None
            acceso = r.json()["access_token"]
            info = httpx.get(os.environ["CIDIA_OIDC_USERINFO_URL"],
                             headers={"Authorization": f"Bearer {acceso}"}, timeout=15).json()
        except Exception:
            return None
        ident = IdentidadExterna(
            id_externo=info.get("sub", usuario),
            usuario=info.get("preferred_username", usuario),
            nombre=info.get("name", usuario),
            email=info.get("email"),
            grupos=info.get("groups", []),
        )
        return self.vincular(bd, ident, "oidc")
