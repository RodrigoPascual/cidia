"""Cola sencilla de trabajos en segundo plano (hilos) con su estado en la base de datos.

Uso:
    def procesar(bd, progreso, captura_id):
        progreso(10, "Extrayendo audio")
        ...
        return {"instruccion_id": 3}

    encolar("captura_video", procesar, captura_id, entidad="captura", entidad_id=captura_id)

La función recibe una sesión de BD propia (se hace commit al terminar) y un callback
`progreso(porcentaje, mensaje)`.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import update

from cidia.db import sesion_bd
from cidia.modelos import Trabajo

log = logging.getLogger("cidia.trabajos")

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cidia-trabajo")
_sincrono = False  # en las pruebas se ejecuta en el mismo hilo


def modo_sincrono(activar: bool = True) -> None:
    global _sincrono
    _sincrono = activar


def encolar(
    tipo: str,
    funcion: Callable[..., Any],
    *args: Any,
    entidad: str | None = None,
    entidad_id: int | None = None,
    usuario_id: int | None = None,
) -> int:
    with sesion_bd() as bd:
        t = Trabajo(tipo=tipo, entidad=entidad, entidad_id=entidad_id, usuario_id=usuario_id)
        bd.add(t)
        bd.flush()
        tid = t.id
    if _sincrono:
        _ejecutar(tid, funcion, args)
    else:
        _pool.submit(_ejecutar, tid, funcion, args)
    return tid


def _actualizar(tid: int, **campos: Any) -> None:
    with sesion_bd() as bd:
        bd.execute(update(Trabajo).where(Trabajo.id == tid).values(**campos))


def _ejecutar(tid: int, funcion: Callable[..., Any], args: tuple[Any, ...]) -> None:
    _actualizar(tid, estado="en_curso", progreso=1)

    def progreso(pct: int, mensaje: str | None = None) -> None:
        _actualizar(tid, progreso=max(0, min(99, int(pct))), mensaje=mensaje)

    try:
        with sesion_bd() as bd:
            resultado = funcion(bd, progreso, *args)
        _actualizar(tid, estado="completado", progreso=100, resultado=resultado if isinstance(resultado, dict) else None)
    except Exception as e:  # noqa: BLE001
        log.error("Trabajo %s falló: %s\n%s", tid, e, traceback.format_exc())
        _actualizar(tid, estado="error", mensaje=str(e)[:2000])


def marcar_interrumpidos() -> None:
    """Al arrancar: los trabajos que quedaron a medias se marcan como error."""
    with sesion_bd() as bd:
        bd.execute(
            update(Trabajo)
            .where(Trabajo.estado.in_(["pendiente", "en_curso"]))
            .values(estado="error", mensaje="Interrumpido al reiniciar el servidor")
        )
