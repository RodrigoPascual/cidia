"""Protecciones globales de la API: tamaño máximo de las peticiones y datos que PostgreSQL no admite.

Se instala en main.py, dentro de `crear_app()`, con `proteccion.instalar(app)`.

* Tamaño de la petición. FastAPI y Starlette leen el cuerpo entero antes de que la ruta compruebe
  nada (un JSON, en memoria; un formulario con ficheros, en un temporal en disco). Los límites de
  cada ruta (25 MB de una foto, 4.000 caracteres de una pregunta...) llegan tarde: sin un tope
  general, cualquiera con una sesión de invitado, que no cuesta nada, podría enviar cientos de MB
  a /api/consulta o a /v1/chat/completions. Se responde 413 en cuanto se sabe: por la cabecera
  Content-Length o, si el cliente no la manda, al pasarse mientras se lee.
* Datos que PostgreSQL no admite. Un identificador que no cabe en un INTEGER (código 22003) es,
  para quien lo pide, algo que no existe (404), y un texto con el carácter NUL (22021) es una
  petición no válida (400). Sin esto, ambos acaban en un error 500.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MB = 1024 * 1024
POR_DEFECTO = 32 * MB  # notas de voz y fotos (25 MB), imágenes de pasos (15 MB), JSON
# (método, prefijo de la ruta, máximo). Gana el primero que coincide.
LIMITES: tuple[tuple[str, str, int], ...] = (
    ("POST", "/api/captura", 2048 * MB),  # vídeos de captura (ficheros.MAX_SUBIDA)
    ("POST", "/api/documentos", 2048 * MB),  # documentos y audios largos de la consola
    ("POST", "/api/espacio/subir", int(os.environ.get("CIDIA_ESPACIO_MAX_FICHERO_MB", "100")) * MB + MB),
    ("POST", "/v1/", 64 * MB),  # imágenes en base64 para el modelo con visión
)
SIN_CUERPO = {"GET", "HEAD", "OPTIONS", "DELETE"}


def limite_de(metodo: str, ruta: str) -> int:
    for m, prefijo, maximo in LIMITES:
        if metodo == m and ruta.startswith(prefijo):
            return maximo
    return POR_DEFECTO


def _mensaje(maximo: int) -> str:
    return f"La petición es demasiado grande (máximo {maximo // MB} MB)."


class LimiteCuerpo:
    """Middleware ASGI que corta las peticiones más grandes que su límite con un 413."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET") in SIN_CUERPO:
            await self.app(scope, receive, send)
            return
        maximo = limite_de(scope.get("method", ""), scope.get("path", ""))
        longitud = next((v for k, v in scope.get("headers", []) if k == b"content-length"), None)
        if longitud is not None and longitud.strip().isdigit() and int(longitud) > maximo:
            respuesta = JSONResponse({"detail": _mensaje(maximo)}, status_code=413, headers={"Connection": "close"})
            await respuesta(scope, receive, send)
            return
        leidos = 0

        async def recibir() -> Message:
            nonlocal leidos
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                leidos += len(mensaje.get("body", b""))
                if leidos > maximo:  # cuerpo por trozos (sin Content-Length) que se pasa del límite
                    raise HTTPException(413, _mensaje(maximo))
            return mensaje

        await self.app(scope, recibir, send)


def codigo_postgres(exc: BaseException) -> str | None:
    """SQLSTATE del error de PostgreSQL que hay debajo (pg8000 lo da en args[0]['C'])."""
    orig: Any = getattr(exc, "orig", None)
    for candidato in (orig, exc):
        args = getattr(candidato, "args", None) or ()
        if args and isinstance(args[0], dict) and args[0].get("C"):
            return str(args[0]["C"])
        codigo = getattr(candidato, "sqlstate", None) or getattr(candidato, "pgcode", None)
        if codigo:
            return str(codigo)
    return None


async def error_de_datos(request: Request, exc: Exception) -> JSONResponse:
    codigo = codigo_postgres(exc)
    if codigo == "22003":  # numeric_value_out_of_range: un id que no cabe en INTEGER
        return JSONResponse({"detail": "No se encuentra lo que buscas."}, status_code=404)
    if codigo in ("22021", "22P05"):  # carácter NUL o que no existe en UTF-8
        return JSONResponse({"detail": "El texto contiene caracteres no válidos."}, status_code=400)
    raise exc  # lo demás sigue siendo un error del servidor (500), con su traza en el registro


def instalar(app: FastAPI) -> None:
    app.add_middleware(LimiteCuerpo)
    app.add_exception_handler(DBAPIError, error_de_datos)


def instalada(app: FastAPI) -> bool:
    return any(getattr(m, "cls", None) is LimiteCuerpo for m in app.user_middleware)
