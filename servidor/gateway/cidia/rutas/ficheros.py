"""Servicio de ficheros con URL firmada (imágenes de pasos, clips, audios, descargas).

Seguridad: los ficheros se sirven en el mismo origen que la interfaz, así que un HTML o un
SVG subido como documento podría ejecutar código con la sesión del usuario. Por eso:
  * nunca se siguen enlaces simbólicos;
  * los tipos que el navegador puede ejecutar (HTML, SVG, XML, JS) se fuerzan como descarga;
  * todas las respuestas llevan X-Content-Type-Options: nosniff y una CSP de caja de arena
    (salvo los PDF, que el visor del navegador necesita mostrar).
"""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from cidia.config import ajustes
from cidia.ficheros import ruta_absoluta
from cidia.seguridad import comprobar_firma

router = APIRouter(prefix="/api/ficheros", tags=["ficheros"])

TIPOS_ACTIVOS = ("text/html", "image/svg+xml", "application/xml", "text/xml", "application/xhtml+xml",
                 "text/javascript", "application/javascript")
CSP = "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"


def _tiene_enlaces(raiz: Path, rel: str) -> bool:
    """True si algún tramo de la ruta relativa es un enlace simbólico."""
    actual = raiz
    for parte in Path(rel).parts:
        actual = actual / parte
        if actual.is_symlink():
            return True
    return False


@router.get("/{ruta:path}")
def servir(ruta: str, exp: int, firma: str, descargar: bool = False) -> FileResponse:
    if not comprobar_firma(ruta, exp, firma):
        raise HTTPException(403, "Enlace caducado o no válido.")
    p = ruta_absoluta(ruta)
    if not p.is_file() or _tiene_enlaces(ajustes().dir_datos, ruta):
        raise HTTPException(404, "Fichero no encontrado.")
    tipo = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    activo = tipo in TIPOS_ACTIVOS
    cabeceras = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"}
    if tipo != "application/pdf":
        cabeceras["Content-Security-Policy"] = CSP
    return FileResponse(p, filename=p.name if (descargar or activo) else None,
                        media_type="application/octet-stream" if activo else tipo, headers=cabeceras)
