"""Ganchos del ciclo de vida de la aplicación.

Un módulo que necesite algo vivo mientras corre el servidor (p. ej. el gestor de sesiones
de MCP) registra aquí una fábrica de context manager asíncrono:

    from cidia.vida import al_arrancar
    al_arrancar(lambda: mcp.session_manager.run())
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

ganchos: list[Callable[[], AbstractAsyncContextManager[Any]]] = []


def al_arrancar(fabrica: Callable[[], AbstractAsyncContextManager[Any]]) -> None:
    ganchos.append(fabrica)
