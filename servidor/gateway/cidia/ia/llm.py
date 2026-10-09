"""Cliente de modelos compatible con OpenAI (Ollama por defecto).

Solo se usan modelos permitidos por la administración (tabla modelos_ia). Si la tabla
está vacía se usan los de la configuración.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.modelos import ModeloIA

log = logging.getLogger("cidia.llm")

_PENSAMIENTO = re.compile(r"<think>.*?</think>\s*", re.S)


class ErrorModelo(RuntimeError):
    """El modelo no está disponible o ha fallado."""


# --------------------------------------------------------------------------- selección de modelo


def modelo_permitido(bd: Session | None, tipo: str = "chat", ref: str | None = None) -> str:
    """Devuelve la referencia del modelo a usar. Lanza ErrorModelo si `ref` no está permitido."""
    a = ajustes()
    por_defecto = {"chat": a.llm_modelo_chat, "embeddings": a.llm_modelo_embeddings, "vision": a.llm_modelo_vision}
    if bd is None:
        return ref or por_defecto.get(tipo, a.llm_modelo_chat)
    filas = bd.scalars(select(ModeloIA).where(ModeloIA.tipo == tipo)).all()
    if not filas:
        if ref and ref != por_defecto.get(tipo):
            raise ErrorModelo(f"El modelo «{ref}» no está permitido en este servidor.")
        return por_defecto.get(tipo) or a.llm_modelo_chat
    permitidos = [m for m in filas if m.permitido and (m.ubicacion == "local" or a.permitir_modelos_nube)]
    if ref:
        for m in permitidos:
            if ref in (m.ref, m.nombre):
                return m.ref
        raise ErrorModelo(f"El modelo «{ref}» no está permitido en este servidor.")
    for m in permitidos:
        if m.predeterminado:
            return m.ref
    if permitidos:
        return permitidos[0].ref
    raise ErrorModelo("No hay ningún modelo permitido. Pide a la administración que habilite uno.")


def modelos_chat_permitidos(bd: Session) -> list[ModeloIA]:
    a = ajustes()
    filas = bd.scalars(
        select(ModeloIA).where(ModeloIA.tipo.in_(["chat", "vision"]), ModeloIA.permitido.is_(True))
    ).all()
    return [m for m in filas if m.ubicacion == "local" or a.permitir_modelos_nube]


def modelo_vision(bd: Session | None) -> str | None:
    """Modelo con visión permitido, o None si no hay ninguno."""
    if bd is not None:
        nube = ajustes().permitir_modelos_nube
        filas = bd.scalars(select(ModeloIA).where(ModeloIA.permitido.is_(True))).all()
        for m in sorted(filas, key=lambda m: not m.predeterminado):
            if m.soporta_vision and m.tipo in ("chat", "vision") and (m.ubicacion == "local" or nube):
                return m.ref
    return ajustes().llm_modelo_vision or None


# --------------------------------------------------------------------------- utilidades


def _cabeceras() -> dict[str, str]:
    return {"Authorization": f"Bearer {ajustes().llm_api_key}"}


def _url(ruta: str) -> str:
    return ajustes().llm_base_url.rstrip("/") + ruta


def limpiar(texto: str) -> str:
    """Quita el razonamiento <think> que emiten algunos modelos."""
    return _PENSAMIENTO.sub("", texto or "").strip()


def _preparar(mensajes: list[dict[str, Any]], modelo: str) -> list[dict[str, Any]]:
    """Punto único para adaptar los mensajes a un modelo concreto (hoy no cambia nada)."""
    return mensajes


def _cuerpo(modelo: str, mensajes: list[dict[str, Any]], temperatura: float, stream: bool,
            max_tokens: int | None = None) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {"model": modelo, "messages": _preparar(mensajes, modelo),
                              "temperature": temperatura, "stream": stream}
    if max_tokens:
        cuerpo["max_tokens"] = max_tokens
    if ajustes().llm_sin_razonamiento:
        cuerpo["reasoning_effort"] = "none"
    return cuerpo


def imagen_a_parte(ruta: str | Path, mime: str = "image/jpeg") -> dict[str, Any]:
    """Parte de mensaje con una imagen en base64 (formato OpenAI)."""
    datos = base64.b64encode(Path(ruta).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{datos}"}}


def extraer_json(texto: str) -> Any:
    """Extrae el primer objeto o lista JSON de una respuesta de modelo."""
    t = limpiar(texto)
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip())
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for abre, cierra in (("{", "}"), ("[", "]")):
        i, j = t.find(abre), t.rfind(cierra)
        if i != -1 and j > i:
            try:
                return json.loads(t[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise ErrorModelo("El modelo no devolvió un JSON válido.")


# --------------------------------------------------------------------------- llamadas


def chat(
    mensajes: list[dict[str, Any]],
    modelo: str | None = None,
    bd: Session | None = None,
    temperatura: float = 0.2,
    max_tokens: int | None = None,
    formato_json: bool = False,
) -> str:
    """Llamada síncrona de chat. Devuelve el texto sin razonamiento."""
    ref = modelo_permitido(bd, "chat", modelo) if modelo is None or bd is not None else modelo
    cuerpo = _cuerpo(ref, mensajes, temperatura, False, max_tokens)
    if formato_json:
        cuerpo["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(_url("/chat/completions"), json=cuerpo, headers=_cabeceras(), timeout=ajustes().llm_timeout)
    except httpx.HTTPError as e:
        raise ErrorModelo(f"No se puede contactar con el modelo: {e}") from e
    if r.status_code != 200:
        raise ErrorModelo(f"El modelo respondió {r.status_code}: {r.text[:300]}")
    return limpiar(r.json()["choices"][0]["message"].get("content") or "")


def chat_json(
    mensajes: list[dict[str, Any]],
    modelo: str | None = None,
    bd: Session | None = None,
    temperatura: float = 0.1,
    intentos: int = 2,
    max_tokens: int | None = None,
) -> Any:
    """Chat que debe devolver JSON; reintenta si no se puede interpretar."""
    ultimo: Exception | None = None
    for _ in range(max(1, intentos)):
        try:
            return extraer_json(chat(mensajes, modelo, bd, temperatura, max_tokens, formato_json=True))
        except ErrorModelo as e:
            ultimo = e
    raise ultimo or ErrorModelo("Sin respuesta")


async def chat_stream(
    mensajes: list[dict[str, Any]],
    modelo: str,
    temperatura: float = 0.2,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Streaming de tokens de texto (sin el bloque <think>)."""
    cuerpo = _cuerpo(modelo, mensajes, temperatura, True, max_tokens)
    dentro_think = False
    async with httpx.AsyncClient(timeout=ajustes().llm_timeout) as cli:
        try:
            async with cli.stream("POST", _url("/chat/completions"), json=cuerpo, headers=_cabeceras()) as r:
                if r.status_code != 200:
                    texto = (await r.aread()).decode(errors="ignore")[:300]
                    raise ErrorModelo(f"El modelo respondió {r.status_code}: {texto}")
                async for linea in r.aiter_lines():
                    if not linea.startswith("data:"):
                        continue
                    dato = linea[5:].strip()
                    if dato == "[DONE]":
                        break
                    try:
                        delta = json.loads(dato)["choices"][0].get("delta", {}).get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if not delta:
                        continue
                    if "<think>" in delta:
                        dentro_think = True
                        delta = delta.split("<think>", 1)[0]
                    if dentro_think:
                        if "</think>" in delta:
                            dentro_think = False
                            delta = delta.split("</think>", 1)[1].lstrip()
                        else:
                            continue
                    if delta:
                        yield delta
        except httpx.HTTPError as e:
            raise ErrorModelo(f"No se puede contactar con el modelo: {e}") from e


def embeddings(textos: list[str], modelo: str | None = None) -> list[list[float]]:
    """Vectores de una lista de textos (en lotes)."""
    if not textos:
        return []
    ref = modelo or ajustes().llm_modelo_embeddings
    salida: list[list[float]] = []
    for i in range(0, len(textos), 32):
        lote = [t[:6000] for t in textos[i : i + 32]]
        try:
            r = httpx.post(_url("/embeddings"), json={"model": ref, "input": lote}, headers=_cabeceras(),
                           timeout=ajustes().llm_timeout)
        except httpx.HTTPError as e:
            raise ErrorModelo(f"No se puede contactar con el modelo de embeddings: {e}") from e
        if r.status_code != 200:
            raise ErrorModelo(f"Embeddings: {r.status_code} {r.text[:200]}")
        datos = sorted(r.json()["data"], key=lambda d: d["index"])
        salida.extend(d["embedding"] for d in datos)
    return salida


def embedding(texto: str) -> list[float]:
    return embeddings([texto])[0]


def embedding_consulta(texto: str) -> list[float]:
    """Vector de una pregunta. Qwen3-Embedding rinde mejor con una instrucción delante."""
    a = ajustes()
    prefijo = a.llm_instruccion_consulta if "qwen3-embedding" in a.llm_modelo_embeddings else ""
    return embeddings([prefijo + texto])[0]


def salud() -> dict[str, Any]:
    try:
        r = httpx.get(_url("/models"), headers=_cabeceras(), timeout=5)
        ok = r.status_code == 200
        modelos = [m["id"] for m in r.json().get("data", [])] if ok else []
        return {"ok": ok, "modelos": modelos}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
