"""Modo planta: elección de tarea y ejecución guiada paso a paso en el portátil del puesto."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from cidia.db import obtener_bd
from cidia.modelos import Instruccion
from cidia.seguridad import Actor, usuario_actual
from cidia.servicios import consulta, planta

log = logging.getLogger("cidia.planta")

router = APIRouter(prefix="/api/planta", tags=["modo planta"])


class NuevaEjecucion(BaseModel):
    tarea_id: int


class Confirmacion(BaseModel):
    critico_confirmado: bool = False


class Revision(BaseModel):
    decision: Literal["aprobada", "rechazada"]
    comentario: str | None = Field(default=None, max_length=planta.MAX_COMENTARIO)


class PreguntaPlanta(BaseModel):
    pregunta: str = Field(max_length=consulta.MAX_PREGUNTA)
    paso_id: int | None = None
    historial: list[dict[str, Any]] | None = Field(default=None, max_length=50)  # [{rol: usuario|asistente, texto}]


@router.get("/tareas")
def tareas(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    """Tareas con instrucción publicada que la persona puede ejecutar, con su nivel ILUO."""
    return planta.tareas(bd, actor)


@router.post("/ejecuciones")
def iniciar(datos: NuevaEjecucion, actor: Actor = Depends(usuario_actual),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ej, reanudada = planta.iniciar(bd, actor, datos.tarea_id)
    bd.commit()
    return {**planta.a_dict(bd, ej, actor), "reanudada": reanudada}


@router.get("/ejecuciones/{ejecucion_id}")
def ver(ejecucion_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return planta.a_dict(bd, planta.obtener_ejecucion(bd, actor, ejecucion_id), actor)


@router.post("/ejecuciones/{ejecucion_id}/pasos/{paso_id}/confirmar")
def confirmar(ejecucion_id: int, paso_id: int, datos: Confirmacion, actor: Actor = Depends(usuario_actual),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ej = planta.obtener_ejecucion(bd, actor, ejecucion_id, escribir=True)
    ep = planta.confirmar_paso(bd, actor, ej, paso_id, datos.critico_confirmado)
    bd.commit()
    hechos = sum(1 for e in ej.pasos if e.confirmado_en is not None)
    return {"paso_id": paso_id, "confirmado": True, "confirmado_en": ep.confirmado_en.isoformat() if ep.confirmado_en else None,
            "critico_confirmado": ep.critico_confirmado, "pasos_confirmados": hechos, "total_pasos": len(ej.pasos)}


def _sse(evento: dict[str, Any]) -> str:
    """Un evento Server-Sent Events: «event: <tipo>» y el diccionario completo como datos JSON."""
    return f"event: {evento.get('tipo', 'message')}\ndata: {json.dumps(evento, ensure_ascii=False, default=str)}\n\n"


@router.post("/ejecuciones/{ejecucion_id}/preguntar")
async def preguntar(ejecucion_id: int, datos: PreguntaPlanta, actor: Actor = Depends(usuario_actual),
                    bd: Session = Depends(obtener_bd)) -> StreamingResponse:
    """Pregunta al copiloto en el contexto del paso (SSE: fuentes, token, fin, error).

    La consulta cuenta en la ejecución, en el paso y en los críticos si lo es: preguntar ya es
    la evidencia que mide la curva de autonomía. Se cuenta y se guarda ANTES de responder, así
    vale aunque el modelo falle o la persona cierre la pantalla a mitad de la respuesta (si se
    contara al final, cortar el streaming dejaría una ejecución «sin consultas en los críticos»).
    `consulta.responder_stream` no toca estos contadores: se cuenta una sola vez.
    """
    texto = datos.pregunta.strip()
    if not texto:
        raise HTTPException(400, "Escribe o di tu pregunta.")

    def contar() -> dict[str, Any]:
        """Permisos, validación del paso y recuento (en un hilo: no bloquea el bucle de eventos)."""
        ej = planta.obtener_ejecucion(bd, actor, ejecucion_id, escribir=True)
        paso = planta.registrar_consulta(bd, ej, datos.paso_id)  # valida el paso y que siga en curso
        bd.commit()
        _ = actor.nivel_orden  # carga el nivel antes de responder: el alcance de la búsqueda lo necesita
        return {"tarea_id": ej.tarea_id, "paso_id": paso.id if paso else None, "ejecucion_id": ej.id}

    contexto = await run_in_threadpool(contar)

    async def emitir() -> AsyncIterator[str]:
        try:
            async for evento in consulta.responder_stream(bd, actor, texto, modo="planta", contexto=contexto,
                                                          historial=datos.historial):
                yield _sse(evento)
        except NotImplementedError:
            yield _sse({"tipo": "error", "mensaje": "El copiloto todavía no está disponible en este servidor."})
        except Exception as e:  # noqa: BLE001
            log.exception("Fallo al responder en el modo planta: %s", e)
            yield _sse({"tipo": "error", "mensaje": "El copiloto no ha podido responder. Inténtalo de nuevo."})

    return StreamingResponse(emitir(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ejecuciones/{ejecucion_id}/foto")
def foto(ejecucion_id: int, imagen: UploadFile = File(...), actor: Actor = Depends(usuario_actual),
         bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Foto del resultado. Si hay modelo con visión se compara con la imagen del experto en segundo
    plano: la respuesta llega enseguida con estado «comparando» y la pantalla consulta la ejecución
    hasta tener el veredicto."""
    ej = planta.obtener_ejecucion(bd, actor, ejecucion_id, escribir=True)
    veredicto = planta.guardar_foto(bd, actor, ej, imagen)
    bd.commit()
    if veredicto.get("estado") == planta.COMPARANDO:
        ins = bd.get(Instruccion, ej.instruccion_id)
        planta.comparar_en_segundo_plano(ej, ins)
        bd.expire_all()  # si ya ha terminado (en las pruebas se compara en el mismo hilo), su veredicto
        ej = planta.obtener_ejecucion(bd, actor, ejecucion_id)
        veredicto = planta.veredicto_dict(ej, bd.get(Instruccion, ej.instruccion_id)) or veredicto
    return veredicto or {}


@router.get("/revisiones")
def revisiones(estado: Literal["pendientes", "revisadas", "todas"] = Query("pendientes"),
               actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Fotos del resultado que el jefe (o la administración) puede revisar: {elementos, pendientes}."""
    return planta.revisiones(bd, actor, estado)


@router.post("/ejecuciones/{ejecucion_id}/revision")
def revisar(ejecucion_id: int, datos: Revision, actor: Actor = Depends(usuario_actual),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """El jefe da por buena la foto del resultado o la rechaza con un comentario."""
    ej = planta.obtener_ejecucion(bd, actor, ejecucion_id, bloquear=True)  # 404 a quien no puede verla
    veredicto = planta.revisar_foto(bd, actor, ej, datos.decision, datos.comentario)
    bd.commit()
    return veredicto


@router.post("/ejecuciones/{ejecucion_id}/finalizar")
def finalizar(ejecucion_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ej = planta.obtener_ejecucion(bd, actor, ejecucion_id, escribir=True)
    resumen = planta.finalizar(bd, actor, ej)
    bd.commit()
    return {"id": ej.id, "estado": ej.estado, "resumen": resumen}


@router.post("/ejecuciones/{ejecucion_id}/abandonar")
def abandonar(ejecucion_id: int, actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    ej = planta.obtener_ejecucion(bd, actor, ejecucion_id, escribir=True, exigir_tarea=False)
    planta.abandonar(bd, actor, ej)
    bd.commit()
    return {"id": ej.id, "estado": ej.estado}
