"""API compatible con OpenAI para la app de escritorio (el agente): /v1/models y /v1/chat/completions.

El gateway es el único proveedor de modelos de la app: autentica con el mismo token que /api,
solo deja usar los modelos permitidos por la administración y reenvía la petición al servidor
de modelos (Ollama) con el streaming SSE intacto. Las herramientas (tools) y las imágenes
viajan tal cual; se quita `tool_choice` porque Ollama no lo admite.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from cidia.config import ajustes
from cidia.db import obtener_bd
from cidia.ia import llm
from cidia.modelos import ModeloIA
from cidia.seguridad import Actor, actor_actual, limitar_invitado
from cidia.xapi import registrar

log = logging.getLogger("cidia.openai")

router = APIRouter(prefix="/v1", tags=["compatible con OpenAI"])

MAX_TOKENS_INVITADO = 1024
# Nombres genéricos que algunos clientes envían: se usa el modelo predeterminado.
ALIAS_PREDETERMINADO = {"", "cidia", "auto", "default", "predeterminado"}


def _error(estado: int, mensaje: str, tipo: str = "invalid_request_error", codigo: str | None = None) -> JSONResponse:
    """Error con la forma de OpenAI ({"error": {...}}) y también `detail`, como el resto de la API."""
    return JSONResponse(
        {"error": {"message": mensaje, "type": tipo, "code": codigo}, "detail": mensaje}, status_code=estado
    )


def _cliente_http() -> httpx.AsyncClient:
    """Cliente hacia el servidor de modelos (las pruebas lo sustituyen por un transporte falso)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(ajustes().llm_timeout, connect=10.0))


# --------------------------------------------------------------------------- modelos


def _filas_permitidas(bd: Session) -> list[ModeloIA]:
    return llm.modelos_chat_permitidos(bd)


@router.get("/models")
def modelos(actor: Actor = Depends(actor_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Modelos de chat permitidos, con id = referencia en el proveedor."""
    filas = _filas_permitidas(bd)
    creado = int(time.time())
    if not filas and not bd.scalar(select(ModeloIA.id).where(ModeloIA.tipo.in_(["chat", "vision"])).limit(1)):
        # Tabla de modelos vacía: el de la configuración.
        ref = ajustes().llm_modelo_chat
        return {"object": "list", "data": [{"id": ref, "object": "model", "created": creado, "owned_by": "cidia",
                                            "name": ref, "vision": False, "default": True}]}
    try:
        predeterminado = llm.modelo_permitido(bd, "chat")
    except llm.ErrorModelo:
        predeterminado = None
    vistos: set[str] = set()
    datos = []
    for m in sorted(filas, key=lambda m: (not m.predeterminado, m.nombre.lower())):
        if m.ref in vistos:
            continue
        vistos.add(m.ref)
        datos.append({"id": m.ref, "object": "model", "created": int(m.creado.timestamp()) if m.creado else creado,
                      "owned_by": "cidia", "name": m.nombre, "vision": bool(m.soporta_vision or m.tipo == "vision"),
                      "default": m.ref == predeterminado})
    return {"object": "list", "data": datos}


def resolver_modelo(bd: Session, pedido: str | None) -> tuple[str, ModeloIA | None]:
    """Referencia del modelo a usar (por ref o por nombre visible). Lanza llm.ErrorModelo si no está permitido."""
    pedido = (pedido or "").strip()
    filas = _filas_permitidas(bd)
    if pedido.lower() in ALIAS_PREDETERMINADO:
        ref = llm.modelo_permitido(bd, "chat")
    else:
        for m in filas:
            if pedido in (m.ref, m.nombre):
                return m.ref, m
        ref = llm.modelo_permitido(bd, "chat", pedido)  # tabla vacía: solo el de la configuración
    return ref, next((m for m in filas if m.ref == ref), None)


def _tiene_imagenes(mensajes: Any) -> bool:
    if not isinstance(mensajes, list):
        return False
    for m in mensajes:
        contenido = m.get("content") if isinstance(m, dict) else None
        if isinstance(contenido, list) and any(isinstance(p, dict) and p.get("type") in ("image_url", "input_image")
                                               for p in contenido):
            return True
    return False


def _acotar(cuerpo: dict[str, Any], clave: str, maximo: int, obligatorio: bool = False) -> None:
    """Deja `clave` entre 1 y `maximo`. Un valor que no sea un entero positivo se cambia por el máximo
    (y si falta, solo se añade cuando es obligatorio)."""
    valor = cuerpo.get(clave)
    if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0:
        cuerpo[clave] = min(valor, maximo)
    elif obligatorio or clave in cuerpo:
        cuerpo[clave] = maximo


def _preparar(bd: Session, actor: Actor, cuerpo: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Valida y adapta la petición. Devuelve (cuerpo para el proveedor, modelo). Lanza llm.ErrorModelo."""
    limitar_invitado(bd, actor)
    ref, fila = resolver_modelo(bd, cuerpo.get("model"))
    salida = dict(cuerpo)
    # Con imágenes y un modelo sin visión se usa el modelo con visión permitido, si lo hay. Tiene que
    # estar entre los permitidos de este servidor: nunca uno en la nube bloqueado por la política.
    if _tiene_imagenes(salida.get("messages")) and fila is not None and not (fila.soporta_vision or fila.tipo == "vision"):
        vision = llm.modelo_vision(bd)
        if vision and vision in {m.ref for m in _filas_permitidas(bd)}:
            ref = vision
    salida["model"] = ref
    salida.pop("tool_choice", None)  # Ollama no lo admite
    if ajustes().llm_sin_razonamiento:
        salida["reasoning_effort"] = "none"
    if actor.es_invitado:
        _acotar(salida, "max_tokens", MAX_TOKENS_INVITADO, obligatorio=True)
        _acotar(salida, "max_completion_tokens", MAX_TOKENS_INVITADO)
        if "n" in salida:
            salida["n"] = 1  # varias respuestas a la vez multiplicarían el tope de tokens
    return salida, ref


def _registrar_uso(bd: Session, actor: Actor, ref: str, cuerpo: dict[str, Any], uso: dict[str, Any] | None) -> None:
    """Registro ligero de uso (quién, qué modelo, cuánto), sin guardar el contenido de los mensajes."""
    resultado: dict[str, Any] = {
        "stream": bool(cuerpo.get("stream")),
        "mensajes": len(cuerpo.get("messages") or []),
        "herramientas": len(cuerpo.get("tools") or []),
        "imagenes": _tiene_imagenes(cuerpo.get("messages")),
    }
    if uso:
        resultado["tokens"] = {k: uso.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens") if k in uso}
    registrar(bd, actor, "uso_modelo", "modelo", ref, ref, resultado=resultado, contexto={"api": "openai"})
    bd.commit()


# --------------------------------------------------------------------------- chat


@router.post("/chat/completions")
async def chat_completions(request: Request, actor: Actor = Depends(actor_actual),
                           bd: Session = Depends(obtener_bd)) -> Response:
    try:
        cuerpo = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "El cuerpo de la petición no es un JSON válido.")
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("messages"), list) or not cuerpo["messages"]:
        return _error(400, "Falta la lista de mensajes (messages).")
    if cuerpo.get("model") is not None and not isinstance(cuerpo["model"], str):
        return _error(400, "El modelo (model) tiene que ser un texto.")
    try:
        salida, ref = await run_in_threadpool(_preparar, bd, actor, cuerpo)
    except llm.ErrorModelo as e:
        return _error(403, str(e), codigo="modelo_no_permitido")
    except HTTPException as e:  # límite de uso de invitados
        tipo = "rate_limit_error" if e.status_code == 429 else "invalid_request_error"
        return _error(e.status_code, str(e.detail), tipo)

    url = ajustes().llm_base_url.rstrip("/") + "/chat/completions"
    cabeceras = {"Authorization": f"Bearer {ajustes().llm_api_key}", "Content-Type": "application/json"}
    cliente = _cliente_http()

    if not salida.get("stream"):
        try:
            r = await cliente.post(url, json=salida, headers=cabeceras)
        except httpx.HTTPError as e:
            log.warning("Servidor de modelos inaccesible: %s", e)
            return _error(502, "El servidor de modelos no responde ahora mismo.", "api_error", "modelo_no_disponible")
        finally:
            await cliente.aclose()
        try:
            datos = r.json()
        except ValueError:
            return _error(502, "El servidor de modelos devolvió una respuesta no válida.", "api_error")
        if r.status_code == 200:
            uso = datos.get("usage") if isinstance(datos, dict) else None
            await run_in_threadpool(_registrar_uso, bd, actor, ref, salida, uso)
        return JSONResponse(datos, status_code=r.status_code)

    # Streaming: se abre la conexión antes de responder para poder devolver el error tal cual.
    try:
        peticion = cliente.build_request("POST", url, json=salida, headers=cabeceras)
        r = await cliente.send(peticion, stream=True)
    except httpx.HTTPError as e:
        await cliente.aclose()
        log.warning("Servidor de modelos inaccesible: %s", e)
        return _error(502, "El servidor de modelos no responde ahora mismo.", "api_error", "modelo_no_disponible")
    if r.status_code != 200:
        contenido = await r.aread()
        await r.aclose()
        await cliente.aclose()
        try:
            return JSONResponse(json.loads(contenido), status_code=r.status_code)
        except ValueError:
            return _error(r.status_code, contenido.decode(errors="ignore")[:500] or "Error del servidor de modelos.",
                          "api_error")
    await run_in_threadpool(_registrar_uso, bd, actor, ref, salida, None)

    async def reenviar() -> AsyncIterator[bytes]:
        try:
            async for trozo in r.aiter_bytes():
                yield trozo
        except httpx.HTTPError as e:
            log.warning("Streaming del modelo interrumpido: %s", e)
            aviso = {"error": {"message": "Se ha cortado la conexión con el servidor de modelos.", "type": "api_error"}}
            yield f"data: {json.dumps(aviso, ensure_ascii=False)}\n\n".encode()
        finally:
            await r.aclose()
            await cliente.aclose()

    return StreamingResponse(reenviar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
