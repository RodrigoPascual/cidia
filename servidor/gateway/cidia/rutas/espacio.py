"""Espacio de trabajo: la carpeta privada de cada persona en el servidor (ficheros y consola).

Solo para usuarios con sesión (los invitados reciben 401). La carpeta sale siempre de la
sesión: el cliente solo envía rutas relativas, que valida servicios/espacio.py. La descarga
(/api/espacio/descarga/...) va con URL firmada y caducable, como el resto de ficheros.
"""

from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from cidia.db import obtener_bd
from cidia.seguridad import Actor, usuario_actual
from cidia.servicios import espacio

router = APIRouter(prefix="/api/espacio", tags=["espacio de trabajo"])


class Escritura(BaseModel):
    ruta: str
    contenido: str = ""


class Movimiento(BaseModel):
    origen: str
    destino: str


class NuevaCarpeta(BaseModel):
    ruta: str


class Orden(BaseModel):
    orden: str
    tiempo_max: int = Field(60, ge=1, le=espacio.TIEMPO_MAX)


@router.get("")
def arbol(actor: Actor = Depends(usuario_actual)) -> dict[str, Any]:
    """Árbol de la carpeta con tamaños, fechas, uso y cuota."""
    return espacio.listar(actor)


@router.get("/fichero")
def leer(ruta: str, actor: Actor = Depends(usuario_actual)) -> dict[str, Any]:
    return espacio.leer(actor, ruta)


@router.put("/fichero")
def escribir(datos: Escritura, actor: Actor = Depends(usuario_actual),
             bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    res = espacio.escribir(actor, datos.ruta, datos.contenido)
    espacio.registrar(bd, actor, "guardo", res["ruta"], resultado={"tamano": res["tamano"]})
    bd.commit()
    return res


@router.post("/subir")
def subir(fichero: UploadFile = File(...), carpeta: str = Form(""), actor: Actor = Depends(usuario_actual),
          bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    res = espacio.subir(actor, carpeta, fichero)
    espacio.registrar(bd, actor, "subio", res["ruta"], resultado={"tamano": res["tamano"]})
    bd.commit()
    return res


@router.delete("/fichero")
def borrar(ruta: str, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    espacio.borrar(actor, ruta)
    espacio.registrar(bd, actor, "borro", ruta)
    bd.commit()
    return {"ok": True}


@router.post("/mover")
def mover(datos: Movimiento, actor: Actor = Depends(usuario_actual),
          bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    res = espacio.mover(actor, datos.origen, datos.destino)
    espacio.registrar(bd, actor, "movio", res["ruta"], resultado={"origen": datos.origen[:300]})
    bd.commit()
    return res


@router.post("/carpeta")
def carpeta(datos: NuevaCarpeta, actor: Actor = Depends(usuario_actual),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    res = espacio.crear_carpeta(actor, datos.ruta)
    espacio.registrar(bd, actor, "creo", res["ruta"])
    bd.commit()
    return res


@router.get("/descarga/{rel:path}")
def descarga(rel: str, exp: int, firma: str, descargar: bool = False) -> StreamingResponse:
    """Fichero del espacio con URL firmada (para <a>, <img> e <iframe>, que no envían cabeceras).
    Se sirve desde el fichero ya abierto sin seguir enlaces dentro de la carpeta de su dueño
    (una orden no puede cambiarlo por un enlace entre la comprobación y el envío) y nunca deja
    ejecutar código en la página."""
    f, nombre, st = espacio.abrir_descarga(rel, exp, firma)
    v = espacio.vista(nombre)
    cabeceras = {"Content-Length": str(st.st_size), "Cache-Control": "private, max-age=3600",
                 "X-Content-Type-Options": "nosniff"}
    if descargar or v not in ("imagen", "pdf"):
        cabeceras["Content-Disposition"] = espacio.disposicion(nombre)
    if v != "pdf":  # el visor de PDF de los navegadores no funciona en un contexto aislado
        cabeceras["Content-Security-Policy"] = "sandbox"
    return StreamingResponse(espacio.trozos_de(f, st.st_size), headers=cabeceras,
                             media_type=mimetypes.guess_type(nombre)[0] or "application/octet-stream",
                             background=BackgroundTask(f.close))


@router.get("/ejecutor")
def ejecutor(_: Actor = Depends(usuario_actual)) -> dict[str, Any]:
    """¿Está disponible la consola? (servicio ejecutor configurado y respondiendo)."""
    return espacio.estado_ejecutor()


@router.post("/ejecutar")
def ejecutar(datos: Orden, actor: Actor = Depends(usuario_actual),
             bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    res = espacio.ejecutar(actor, datos.orden, datos.tiempo_max)
    espacio.registrar(bd, actor, "ejecuto", None, resultado={
        "codigo": res["codigo"], "duracion": res["duracion"], "tiempo_agotado": res["tiempo_agotado"],
        "orden": datos.orden[:500],
    })
    bd.commit()
    return res
