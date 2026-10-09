"""Guardado seguro de ficheros bajo dir_datos (rutas relativas, sin salir del directorio)."""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from cidia.config import ajustes

MAX_SUBIDA = 2 * 1024 * 1024 * 1024  # 2 GB (vídeos)


def nombre_seguro(nombre: str) -> str:
    base = Path(nombre or "fichero").name
    base = re.sub(r"[^\w.\- áéíóúüñÁÉÍÓÚÜÑ]", "_", base).strip(" .") or "fichero"
    return base[:150]


def ruta_absoluta(rel: str) -> Path:
    raiz = ajustes().dir_datos.resolve()
    p = (raiz / rel).resolve()
    if raiz not in p.parents and p != raiz:
        raise HTTPException(400, "Ruta no válida.")
    return p


def relativa(p: Path) -> str:
    return p.resolve().relative_to(ajustes().dir_datos.resolve()).as_posix()


def carpeta_nueva(subdir: str) -> Path:
    """Crea dir_datos/subdir/<uuid>/ y la devuelve."""
    d = ajustes().dir_datos / subdir / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    return d


def guardar_subida(subida: UploadFile, subdir: str) -> tuple[str, str, int]:
    """Guarda un UploadFile en dir_datos/subdir/<uuid>/<nombre>. Devuelve (ruta_rel, nombre, tamaño)."""
    nombre = nombre_seguro(subida.filename or "fichero")
    destino = carpeta_nueva(subdir) / nombre
    tam = 0
    with destino.open("wb") as f:
        while bloque := subida.file.read(1024 * 1024):
            tam += len(bloque)
            if tam > MAX_SUBIDA:
                f.close()
                destino.unlink(missing_ok=True)
                raise HTTPException(413, "El fichero es demasiado grande.")
            f.write(bloque)
    return relativa(destino), nombre, tam


def guardar_bytes(datos: bytes, subdir: str, nombre: str) -> str:
    destino = carpeta_nueva(subdir) / nombre_seguro(nombre)
    destino.write_bytes(datos)
    return relativa(destino)


def copiar(origen: Path, subdir: str, nombre: str | None = None) -> str:
    destino = carpeta_nueva(subdir) / nombre_seguro(nombre or origen.name)
    shutil.copyfile(origen, destino)
    return relativa(destino)
