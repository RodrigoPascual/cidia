"""Copiloto: preguntas con citas (en streaming SSE o en JSON), valoración e historial propio."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from cidia.db import obtener_bd
from cidia.modelos import Consulta
from cidia.permisos import alcance_de
from cidia.seguridad import Actor, actor_actual, usuario_actual
from cidia.servicios import consulta
from cidia.xapi import registrar

router = APIRouter(prefix="/api/consulta", tags=["copiloto"])


class ContextoConsulta(BaseModel):
    tarea_id: int | None = None
    paso_id: int | None = None
    ejecucion_id: int | None = None


class Turno(BaseModel):
    """Un turno anterior de la conversación: {rol, texto} o, como en la API de OpenAI, {role, content}."""

    rol: Literal["usuario", "asistente"]
    texto: str = Field(max_length=20000)

    @model_validator(mode="before")
    @classmethod
    def _formato_openai(cls, valor: Any) -> Any:
        if isinstance(valor, dict) and "rol" not in valor and "role" in valor:
            rol = {"user": "usuario", "assistant": "asistente"}.get(valor.get("role"), valor.get("role"))
            contenido = valor.get("content")
            return {"rol": rol, "texto": contenido if isinstance(contenido, str) else ""}
        return valor


class PeticionConsulta(BaseModel):
    pregunta: str = Field(min_length=1, max_length=consulta.MAX_PREGUNTA)
    modo: Literal["normal", "socratico", "planta"] = "normal"
    contexto: ContextoConsulta | None = None
    historial: list[Turno] = Field(default_factory=list, max_length=50)


class PeticionValoracion(BaseModel):
    valor: Literal[1, -1]


def _argumentos(datos: PeticionConsulta) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    ctx = datos.contexto.model_dump() if datos.contexto else None
    return ctx, [t.model_dump() for t in datos.historial]


def _sse(evento: dict[str, Any]) -> str:
    datos = dict(evento)
    tipo = datos.pop("tipo")
    return f"event: {tipo}\ndata: {json.dumps(datos, ensure_ascii=False)}\n\n"


@router.post("")
async def consultar(datos: PeticionConsulta, actor: Actor = Depends(actor_actual),
                    bd: Session = Depends(obtener_bd)) -> StreamingResponse:
    """Respuesta en streaming (Server-Sent Events): `fuentes`, `token`…, `fin` o `error`."""
    ctx, hist = _argumentos(datos)
    # La preparación (permisos, búsqueda, contexto) va antes del streaming: si algo no está
    # permitido se responde con su código HTTP y no con un flujo a medias. Si el cliente pregunta
    # aquí con un ejecucion_id, la consulta se suma a esa ejecución (el modo planta usa su propia ruta).
    prep = await run_in_threadpool(consulta.preparar, bd, actor, datos.pregunta, datos.modo, ctx, hist, True)

    async def eventos() -> AsyncIterator[str]:
        async for ev in consulta.emitir(bd, actor, prep):
            yield _sse(ev)

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/simple")
def consultar_simple(datos: PeticionConsulta, actor: Actor = Depends(actor_actual),
                     bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """La misma consulta sin streaming: {respuesta, fuentes, con_respaldo, consulta_id, laguna_id}."""
    ctx, hist = _argumentos(datos)
    return consulta.responder(bd, actor, datos.pregunta, datos.modo, ctx, hist, contar_ejecucion=True)


def _propia(actor: Actor, c: Consulta | None) -> bool:
    if c is None:
        return False
    if actor.id is not None:
        return c.usuario_id == actor.id
    return c.usuario_id is None and c.sesion_id == actor.sesion.id


@router.post("/{consulta_id}/valoracion")
def valorar(datos: PeticionValoracion, consulta_id: int = Path(ge=1, le=consulta.MAX_ID),
            actor: Actor = Depends(actor_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Útil (1) o no útil (-1). Solo sobre consultas propias."""
    c = bd.get(Consulta, consulta_id)
    if not _propia(actor, c):
        raise HTTPException(404, "No se encuentra esa consulta.")
    assert c is not None
    c.valoracion = datos.valor
    registrar(bd, actor, "valoro", "consulta", c.id, consulta._recortar(c.pregunta, 200),
              resultado={"valor": datos.valor, "util": datos.valor == 1})
    bd.commit()
    return {"ok": True, "consulta_id": c.id, "valoracion": c.valoracion}


@router.get("/historial")
def historial(
    pagina: int = Query(1, ge=1, le=100_000),  # con tope: un número enorme desbordaría el OFFSET
    por_pagina: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    actor: Actor = Depends(usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Mis consultas, de la más reciente a la más antigua."""
    condiciones = [Consulta.usuario_id == actor.id]
    if q and q.strip():
        # autoescape: «%» y «_» se buscan tal cual, no como comodines.
        condiciones.append(Consulta.pregunta.icontains(q.strip(), autoescape=True))
    total = bd.scalar(select(func.count(Consulta.id)).where(*condiciones)) or 0
    filas = bd.scalars(
        select(Consulta).where(*condiciones).order_by(Consulta.creada.desc(), Consulta.id.desc())
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).all()
    alcance = alcance_de(bd, actor)
    return {
        "elementos": [consulta.a_dict(bd, c, alcance) for c in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, -(-total // por_pagina)),
    }
