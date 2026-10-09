"""Servicio de ficheros con URL firmada (imágenes de pasos, clips, audios, descargas)."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from cidia.ficheros import ruta_absoluta
from cidia.seguridad import comprobar_firma

router = APIRouter(prefix="/api/ficheros", tags=["ficheros"])


@router.get("/{ruta:path}")
def servir(ruta: str, exp: int, firma: str, descargar: bool = False) -> FileResponse:
    if not comprobar_firma(ruta, exp, firma):
        raise HTTPException(403, "Enlace caducado o no válido.")
    p = ruta_absoluta(ruta)
    if not p.is_file():
        raise HTTPException(404, "Fichero no encontrado.")
    return FileResponse(p, filename=p.name if descargar else None,
                        headers={"Cache-Control": "private, max-age=3600"})
