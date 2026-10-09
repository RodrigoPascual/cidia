"""Aplicación FastAPI de CidIA.

Arranque: uvicorn cidia.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from cidia import __version__, rutas, vida
from cidia.config import ajustes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cidia")


def _arranque() -> None:
    from cidia.arranque import preparar

    preparar()


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    _arranque()
    async with AsyncExitStack() as pila:
        for fabrica in vida.ganchos:
            await pila.enter_async_context(fabrica())
        log.info("CidIA %s listo", __version__)
        yield


def _incluir_rutas(app: FastAPI) -> None:
    for mod in pkgutil.iter_modules(rutas.__path__):
        m = importlib.import_module(f"cidia.rutas.{mod.name}")
        router = getattr(m, "router", None)
        if router is not None:
            app.include_router(router)


def _montar_mcp(app: FastAPI) -> None:
    try:
        from cidia.mcp_servidor import montar
    except ImportError:
        log.warning("Servidor MCP no disponible")
        return
    montar(app)


def _montar_web(app: FastAPI) -> None:
    dir_web = Path(ajustes().dir_web).resolve()

    @app.get("/", include_in_schema=False)
    def raiz() -> RedirectResponse:
        return RedirectResponse("/app/")

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{ruta:path}", include_in_schema=False)
    def web(request: Request, ruta: str = "") -> Response:
        if not (dir_web / "index.html").exists():
            raise HTTPException(404, "La interfaz web no está compilada.")
        destino = (dir_web / ruta).resolve()
        if ruta and destino.is_file() and dir_web in destino.parents:
            cache = "public, max-age=31536000, immutable" if "/assets/" in destino.as_posix() else "no-cache"
            return FileResponse(destino, headers={"Cache-Control": cache})
        # Rutas internas de la SPA: index.html con <base> para que los recursos relativos
        # funcionen en cualquier profundidad y detrás del proxy del plugin (/cidia/gw).
        prefijo = request.headers.get("x-forwarded-prefix", "").rstrip("/")
        if not re.fullmatch(r"(/[\w.\-]+)*", prefijo):
            prefijo = ""
        html = (dir_web / "index.html").read_text(encoding="utf-8")
        html = html.replace("<head>", f'<head>\n    <base href="{prefijo}/app/" />', 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


_MENSAJES_VALIDACION = {
    "missing": "falta este dato",
    "string_type": "debe ser un texto",
    "int_parsing": "debe ser un número entero",
    "int_type": "debe ser un número entero",
    "float_parsing": "debe ser un número",
    "bool_parsing": "debe ser sí o no",
    "dict_type": "debe ser un objeto",
    "list_type": "debe ser una lista",
    "string_too_short": "es demasiado corto",
    "string_too_long": "es demasiado largo",
    "greater_than_equal": "es demasiado pequeño",
    "less_than_equal": "es demasiado grande",
    "json_invalid": "el cuerpo no es un JSON válido",
    "enum": "no es un valor permitido",
    "literal_error": "no es un valor permitido",
}


async def _error_validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Los 422 de pydantic, con un 'detail' en castellano que la interfaz pueda mostrar."""
    partes = []
    for e in exc.errors():
        campo = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query", "path", "form"))
        msg = _MENSAJES_VALIDACION.get(e.get("type", ""), "no es válido")
        partes.append(f"{campo}: {msg}" if campo else msg)
    return JSONResponse(status_code=422, content={"detail": "Datos no válidos. " + "; ".join(partes) + "."})


def crear_app() -> FastAPI:
    app = FastAPI(
        title="CidIA",
        version=__version__,
        lifespan=ciclo_de_vida,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ajustes().cors_origenes,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    app.add_exception_handler(RequestValidationError, _error_validacion)  # type: ignore[arg-type]
    _incluir_rutas(app)
    _montar_mcp(app)
    _montar_web(app)
    return app


app = crear_app()
